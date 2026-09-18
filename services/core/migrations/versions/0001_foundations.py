"""2A.3/2A.4: rails, ledger and operational state; separate runtime grants."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_foundations"
down_revision = None
branch_labels = None
depends_on = None


def _id(name):
    return sa.Column(name, sa.Text, primary_key=True)


def _json(name="data"):
    return sa.Column(name, JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))


def _time(name, default=False):
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False,
        server_default=sa.text("clock_timestamp()") if default else None,
    )


def upgrade():
    op.create_table("merchants", _id("merchant_id"), _json("profile"), schema="rails")
    op.create_table(
        "terminals", _id("terminal_id"), sa.Column("merchant_id", sa.Text, nullable=False),
        _time("installed_at"), _json(), schema="rails",
    )
    op.create_table(
        "counterparties", sa.Column("merchant_id", sa.Text, primary_key=True),
        sa.Column("counterparty_id", sa.Text, primary_key=True), _json(), schema="rails",
    )
    for table in ("credits", "debits"):
        op.create_table(
            table, _id("txn_id"), sa.Column("merchant_id", sa.Text, nullable=False),
            _time("ts"), sa.Column("amount", sa.BigInteger, nullable=False),
            sa.Column("channel", sa.Text, nullable=False),
            sa.Column("counterparty_id", sa.Text, nullable=False),
            sa.Column("counterparty_handle", sa.Text, nullable=False),
            sa.Column("counterparty_name", sa.Text, nullable=False),
            sa.Column("terminal_id", sa.Text), sa.Column("pos_bill_id", sa.Text),
            sa.Column("utr", sa.Text, nullable=False), sa.Column("orig_txn_id", sa.Text),
            sa.Column("note", sa.Text, nullable=False, server_default=""),
            sa.CheckConstraint("amount >= 0", name=f"{table}_nonnegative_amount"), schema="rails",
        )
        op.create_index(f"{table}_merchant_ts", table, ["merchant_id", "ts"], schema="rails")
        op.create_index(f"{table}_utr", table, ["utr"], schema="rails")
        op.create_index(f"{table}_payer_ts", table, ["merchant_id", "counterparty_id", "ts"], schema="rails")
    op.create_table(
        "bills", _id("pos_bill_id"), sa.Column("merchant_id", sa.Text, nullable=False),
        sa.Column("txn_id", sa.Text, nullable=False), _time("sim_at"), schema="rails",
    )
    op.create_table(
        "bill_lines", sa.Column("pos_bill_id", sa.Text, primary_key=True),
        sa.Column("line_no", sa.Integer, primary_key=True),
        sa.Column("txn_id", sa.Text, nullable=False), sa.Column("merchant_id", sa.Text, nullable=False),
        sa.Column("item", sa.Text, nullable=False), sa.Column("hsn", sa.Text, nullable=False),
        sa.Column("qty", sa.Text, nullable=False), sa.Column("unit", sa.Text, nullable=False),
        sa.Column("rate", sa.Text, nullable=False), sa.Column("line_amount", sa.BigInteger, nullable=False),
        sa.CheckConstraint("line_no >= 1 AND line_amount >= 0", name="bill_line_values"), schema="rails",
    )
    op.create_table(
        "events", _id("event_id"), sa.Column("merchant_id", sa.Text, nullable=False),
        _time("ts"), sa.Column("type", sa.Text, nullable=False), _json(), schema="rails",
    )
    op.create_index("events_merchant_ts", "events", ["merchant_id", "ts"], schema="rails")

    op.create_table(
        "entries", sa.Column("seq", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("merchant_id", sa.Text, nullable=False),
        sa.Column("chain_index", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False), sa.Column("txn_id", sa.Text),
        _json("payload"), sa.Column("actor_role", sa.Text, nullable=False),
        sa.Column("actor_ref", sa.Text, nullable=False), _time("sim_at"), _time("recorded_at", True),
        sa.Column("prev_hash", sa.LargeBinary, nullable=False),
        sa.Column("hash", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("merchant_id", "chain_index", name="entries_merchant_index"),
        sa.CheckConstraint("chain_index >= 0", name="entries_nonnegative_index"),
        sa.CheckConstraint("octet_length(prev_hash) = 32 AND octet_length(hash) = 32", name="entries_hash_lengths"),
        schema="ledger",
    )
    op.create_index("entries_merchant_txn", "entries", ["merchant_id", "txn_id", "chain_index"], schema="ledger")
    op.create_table(
        "chain_heads", _id("merchant_id"),
        sa.Column("chain_index", sa.Integer, nullable=False, server_default="-1"),
        sa.Column("hash", sa.LargeBinary, nullable=False),
        sa.CheckConstraint("chain_index >= -1 AND octet_length(hash) = 32", name="head_values"), schema="ledger",
    )
    op.create_table(
        "anchors", _id("anchor_id"), sa.Column("digest_sha256", sa.Text, nullable=False),
        sa.Column("simulated", sa.Boolean, nullable=False), _time("created_at", True),
        sa.Column("ots_receipt", sa.Text), sa.Column("git_commit_url", sa.Text),
        _json("heads"), schema="ledger",
    )
    op.execute("""
        CREATE FUNCTION ledger.refuse_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ledger.entries is append-only: % is forbidden', TG_OP
                USING ERRCODE = '55000';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER entries_no_update_delete BEFORE UPDATE OR DELETE ON ledger.entries
        FOR EACH ROW EXECUTE FUNCTION ledger.refuse_mutation()
    """)
    op.execute("""
        CREATE TRIGGER entries_no_truncate BEFORE TRUNCATE ON ledger.entries
        FOR EACH STATEMENT EXECUTE FUNCTION ledger.refuse_mutation()
    """)

    op.create_table(
        "cases", _id("case_id"), sa.Column("merchant_id", sa.Text, nullable=False),
        sa.Column("case_type", sa.Text, nullable=False), sa.Column("trigger_ref", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"), _time("opened_at"), _json(), schema="ops",
    )
    op.create_table(
        "packs", _id("pack_id"), sa.Column("case_id", sa.Text, nullable=False),
        sa.Column("merchant_id", sa.Text, nullable=False), sa.Column("pack_type", sa.Text, nullable=False),
        sa.Column("pdf_sha256", sa.Text, nullable=False), _time("built_at"), _json(), schema="ops",
    )
    op.create_table(
        "approvals", _id("approval_id"), sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False), sa.Column("officer_ref", sa.Text),
        sa.Column("resume_url", sa.Text), _time("created_at", True), _json(), schema="ops",
    )
    op.create_table(
        "outbox", _id("delivery_id"), sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("destination", sa.Text, nullable=False), sa.Column("simulated", sa.Boolean, nullable=False),
        _time("sent_at", True), _json(), schema="ops",
    )
    op.create_table(
        "questions", _id("question_id"), sa.Column("merchant_id", sa.Text, nullable=False),
        sa.Column("txn_id", sa.Text, nullable=False), sa.Column("entry_ref", sa.BigInteger, nullable=False),
        _time("asked_at"), _time("expires_at"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"), _json(), schema="ops",
    )
    op.create_index("questions_merchant_asked", "questions", ["merchant_id", "asked_at"], schema="ops")
    for table, key in (("conversations", "conversation_id"), ("media", "media_id"),
                       ("escalations", "escalation_id"), ("metrics", "metric_id")):
        op.create_table(
            table, _id(key), sa.Column("merchant_id", sa.Text, nullable=False),
            _time("created_at", True), _json(), schema="ops",
        )
    op.create_table(
        "payer_facts", sa.Column("merchant_id", sa.Text, primary_key=True),
        sa.Column("counterparty_id", sa.Text, primary_key=True), sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False), sa.Column("entry_ref", sa.BigInteger, nullable=False),
        _time("sim_at"), schema="ops",
    )

    op.execute("GRANT USAGE ON SCHEMA rails, ledger, ops TO hisaab_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rails TO hisaab_app")
    for table in ("cases", "packs", "approvals", "outbox", "questions", "conversations",
                  "media", "payer_facts", "escalations", "metrics"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ops.{table} TO hisaab_app")
    op.execute("GRANT SELECT, INSERT ON ledger.entries, ledger.anchors TO hisaab_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON ledger.chain_heads TO hisaab_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rails, ledger, ops TO hisaab_app")
    op.execute("REVOKE ALL ON FUNCTION ledger.refuse_mutation() FROM PUBLIC")


def downgrade():
    # Dropping a provenance ledger must be a deliberate owner operation.
    raise RuntimeError("No destructive downgrade: restore a snapshot or create a new database.")
