"""Compute evidence tiers relative to an optional case boundary."""

from alembic import op


revision = "0003_tiers"
down_revision = "0002_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP FUNCTION ledger.current_view(text, timestamptz)")
    op.execute("""
        CREATE FUNCTION ledger.current_view(
            p_merchant text, p_as_of timestamptz, p_opened_at timestamptz DEFAULT NULL
        )
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
                   a.kind AS claim_kind, p.sim_at AS proposed_at, a.sim_at AS claim_at,
                   bl.sim_at AS bill_linked_at,
                   d.seq IS NOT NULL AS disputed,
                   array_remove(ARRAY[o.seq, bl.seq, p.seq, a.seq, d.seq], NULL) AS entry_refs
            FROM rails.credits c CROSS JOIN shop LEFT JOIN billed b USING (txn_id)
            LEFT JOIN LATERAL (
                SELECT seq, payload, sim_at FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'label.proposed' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
                SELECT seq, kind, payload, sim_at FROM ledger.entries e
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
                SELECT seq, sim_at FROM ledger.entries e
                WHERE e.merchant_id = p_merchant AND e.txn_id = c.txn_id
                  AND e.kind = 'bill.linked' AND e.sim_at <= p_as_of
                ORDER BY e.chain_index DESC LIMIT 1
            ) bl ON true
            WHERE c.merchant_id = p_merchant AND c.ts <= p_as_of
        ), resolved AS (
            SELECT *, coalesce(claim_label, machine_label) AS effective_label,
                   coalesce(p_opened_at, 'infinity'::timestamptz) AS boundary
            FROM history
        )
        SELECT txn_id, machine_label, claim_label, effective_label,
               disputed OR (bill_label IS NOT NULL AND
                   effective_label IS DISTINCT FROM bill_label AND effective_label IS NOT NULL),
               entry_refs,
               CASE
                   WHEN claim_kind = 'claim.annotated' OR greatest(
                       CASE WHEN machine_label = effective_label THEN proposed_at END,
                       CASE WHEN claim_label = effective_label THEN claim_at END,
                       CASE WHEN bill_label = effective_label THEN bill_linked_at END
                   ) >= boundary THEN 4
                   WHEN bill_linked_at < boundary AND effective_label = bill_label THEN 1
                   WHEN claim_kind = 'claim.answered' AND claim_at < boundary THEN 3
                   WHEN proposed_at < boundary AND claim_kind IS NULL THEN 2
                   ELSE NULL
               END
        FROM resolved
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION ledger.current_view(text, timestamptz, timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ledger.current_view(text, timestamptz, timestamptz) TO hisaab_app")


def downgrade():
    raise RuntimeError("No destructive downgrade: restore a snapshot or create a new database.")
