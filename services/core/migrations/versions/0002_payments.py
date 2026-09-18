"""Phase 4 persistent clock, shared terminal IDs, catalog and payment projection."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_payments"
down_revision = "0001_foundations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "settings", sa.Column("key", sa.Text, primary_key=True),
        sa.Column("data", JSONB, nullable=False), schema="ops",
    )
    op.create_table(
        "hsn_catalog", sa.Column("item", sa.Text, primary_key=True),
        sa.Column("hsn", sa.Text, primary_key=True), sa.Column("exempt", sa.Boolean, nullable=False),
        schema="rails",
    )
    op.drop_constraint("terminals_pkey", "terminals", schema="rails", type_="primary")
    op.create_primary_key("terminals_pkey", "terminals", ["merchant_id", "terminal_id"], schema="rails")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ops.settings, rails.hsn_catalog TO hisaab_app")
    op.execute("""
        CREATE FUNCTION ledger.current_view(p_merchant text, p_as_of timestamptz)
        RETURNS TABLE (txn_id text, machine_label text, claim_label text, effective_label text,
                       conflict boolean, entry_refs bigint[], tier integer)
        LANGUAGE sql STABLE AS $$
        WITH billed AS (
            SELECT b.txn_id,
                   sum(l.line_amount) FILTER (WHERE h.exempt) AS exempt_amount,
                   sum(l.line_amount) AS total
            FROM rails.bills b JOIN rails.bill_lines l USING (pos_bill_id)
            LEFT JOIN rails.hsn_catalog h USING (item, hsn)
            WHERE b.merchant_id = p_merchant AND b.sim_at <= p_as_of
            GROUP BY b.txn_id
        ), shop AS (
            SELECT coalesce(sum(exempt_amount), 0) * 2 > coalesce(sum(total), 0) AS exempt
            FROM billed
        ), history AS (
            SELECT c.txn_id, p.payload->>'label' AS machine_label,
                   CASE WHEN b.txn_id IS NOT NULL THEN
                       CASE WHEN coalesce(b.exempt_amount, 0) * 2 > b.total
                            THEN 'exempt_supply' ELSE 'taxable_supply' END
                   END AS bill_label,
                   CASE WHEN a.kind = 'claim.annotated' THEN a.payload->>'label'
                        WHEN a.payload->>'answer' = 'sale' THEN
                            CASE WHEN b.txn_id IS NOT NULL THEN
                                CASE WHEN coalesce(b.exempt_amount, 0) * 2 > b.total
                                     THEN 'exempt_supply' ELSE 'taxable_supply' END
                            WHEN p.payload->>'label' IN ('taxable_supply', 'exempt_supply')
                                THEN p.payload->>'label'
                            WHEN shop.exempt THEN 'exempt_supply' ELSE 'taxable_supply' END
                        WHEN a.payload->>'answer' = 'family' THEN 'personal_transfer'
                        WHEN a.payload->>'answer' = 'own_money' THEN 'inter_account'
                        WHEN a.payload->>'answer' = 'loan_or_gift' THEN 'non_business'
                        WHEN a.payload->>'answer' = 'refund' THEN 'refund_reversal'
                        WHEN a.payload->>'answer' = 'double_payment' THEN 'duplicate'
                   END AS claim_label,
                   d.seq IS NOT NULL AS disputed,
                   array_remove(ARRAY[o.seq, bl.seq, p.seq, a.seq, d.seq], NULL) AS entry_refs
            FROM rails.credits c CROSS JOIN shop LEFT JOIN billed b USING (txn_id)
            LEFT JOIN LATERAL (
                SELECT seq, payload FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'label.proposed' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
                SELECT seq, kind, payload FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind IN ('claim.answered', 'claim.annotated') AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) a ON true
            LEFT JOIN LATERAL (
                SELECT seq FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'label.disputed' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) d ON true
            LEFT JOIN LATERAL (
                SELECT seq FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'credit.observed' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) o ON true
            LEFT JOIN LATERAL (
                SELECT seq FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'bill.linked' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) bl ON true
            WHERE c.merchant_id = p_merchant AND c.ts <= p_as_of
        )
        SELECT txn_id, machine_label, claim_label, coalesce(claim_label, machine_label),
               disputed OR (bill_label IS NOT NULL AND
                   coalesce(claim_label, machine_label) IS DISTINCT FROM bill_label
                   AND coalesce(claim_label, machine_label) IS NOT NULL),
               entry_refs, NULL::integer
        FROM history
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION ledger.current_view(text, timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ledger.current_view(text, timestamptz) TO hisaab_app")


def downgrade():
    raise RuntimeError("No destructive downgrade: restore a snapshot or create a new database.")
