"""Real Postgres checks, always on the isolated database prepared by tasks.py test --postgres."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.db import sqlalchemy_url
from app.ledger.chain import append
from app.ledger.verify import verify
from app.schemas.ledger import EntryKind
from app.schemas.roles import ROLE_ENTRY_KINDS, Role
from test_contracts import PAYLOAD_EXAMPLES


pytestmark = pytest.mark.postgres
SIM_AT = datetime(2025, 4, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def engines():
    urls = [os.getenv("TEST_DATABASE_URL"), os.getenv("TEST_DATABASE_OWNER_URL")]
    if not all(urls):
        pytest.skip("run python tasks.py test --postgres for real database checks")
    for url in urls:
        if make_url(url).database != "hisaab_ledger_test":
            pytest.fail("ledger tests require the separate hisaab_ledger_test database")
    pair = [create_engine(sqlalchemy_url(url)) for url in urls]
    yield pair
    for engine in pair:
        engine.dispose()


@pytest.fixture
def runtime(engines):
    with engines[0].connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def owner(engines):
    with engines[1].connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def add(connection, merchant=None, kind=EntryKind.CREDIT_OBSERVED, role=Role.RAILS):
    return append(
        connection, merchant_id=merchant or f"test-{uuid4().hex}", txn_id="T",
        kind=kind, payload=PAYLOAD_EXAMPLES[kind], actor_role=role, actor_ref="test-replayer", sim_at=SIM_AT,
    ).root


def test_migrations_create_all_foundation_tables_and_separate_roles(runtime):
    assert runtime.execute(text("SELECT current_user")).scalar_one() == "hisaab_app"
    assert runtime.execute(text("SELECT rolname FROM pg_roles WHERE rolname=current_user AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb")).scalar_one() == "hisaab_app"
    expected = {
        "rails": {"merchants", "terminals", "counterparties", "credits", "debits", "bills", "bill_lines", "events"},
        "ledger": {"entries", "chain_heads", "anchors"},
        "ops": {"cases", "packs", "approvals", "outbox", "questions", "conversations", "media", "payer_facts", "escalations", "metrics", "alembic_version"},
    }
    actual = runtime.execute(text("SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('rails', 'ledger', 'ops')")).all()
    for schema, tables in expected.items():
        assert tables <= {table for namespace, table in actual if namespace == schema}
    assert runtime.execute(text("SELECT has_table_privilege(current_user, 'ledger.entries', 'SELECT, INSERT')")).scalar_one()
    for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
        assert not runtime.execute(text("SELECT has_table_privilege(current_user, 'ledger.entries', :privilege)"), {"privilege": privilege}).scalar_one()
    assert not runtime.execute(text("SELECT has_schema_privilege(current_user, 'ledger', 'CREATE')")).scalar_one()
    assert not runtime.execute(text("SELECT has_table_privilege(current_user, 'ops.alembic_version', 'UPDATE')")).scalar_one()


@pytest.mark.parametrize("kind", list(EntryKind))
def test_every_typed_entry_round_trips_and_verifies_on_postgres(runtime, kind):
    role = next(role for role, kinds in ROLE_ENTRY_KINDS.items() if kind in kinds)
    before = runtime.execute(text("SELECT clock_timestamp()")).scalar_one()
    entry = add(runtime, kind=kind, role=role)
    after = runtime.execute(text("SELECT clock_timestamp()")).scalar_one()
    assert before <= entry.recorded_at <= after
    assert entry.recorded_at > entry.sim_at
    assert entry.chain_index == 0
    assert len(entry.hash) == len(entry.prev_hash) == 32
    assert verify(runtime, entry.merchant_id).ok


@pytest.mark.parametrize("statement", [
    "UPDATE ledger.entries SET actor_ref = 'edited' WHERE merchant_id = :merchant",
    "DELETE FROM ledger.entries WHERE merchant_id = :merchant",
    "TRUNCATE ledger.entries",
])
def test_runtime_grants_refuse_mutation(runtime, statement):
    entry = add(runtime)
    with pytest.raises(DBAPIError) as error:
        with runtime.begin_nested():
            runtime.execute(text(statement), {"merchant": entry.merchant_id})
    assert error.value.orig.sqlstate == "42501"
    assert verify(runtime, entry.merchant_id).ok


@pytest.mark.parametrize("statement", [
    "UPDATE ledger.entries SET actor_ref = 'edited' WHERE merchant_id = :merchant",
    "DELETE FROM ledger.entries WHERE merchant_id = :merchant",
    "TRUNCATE ledger.entries",
])
def test_owner_is_also_stopped_by_each_trigger(owner, statement):
    entry = add(owner)
    with pytest.raises(DBAPIError) as error:
        with owner.begin_nested():
            owner.execute(text(statement), {"merchant": entry.merchant_id})
    assert error.value.orig.sqlstate == "55000"
    assert "append-only" in str(error.value.orig)
    assert verify(owner, entry.merchant_id).ok


def test_one_byte_edit_reports_exact_index_and_restores_trigger(owner):
    merchant = f"test-{uuid4().hex}"
    add(owner, merchant)
    add(owner, merchant)
    add(owner, merchant)
    assert verify(owner, merchant).ok
    # Deliberate owner tamper; the whole test transaction is rolled back, including DDL.
    owner.execute(text("ALTER TABLE ledger.entries DISABLE TRIGGER entries_no_update_delete"))
    owner.execute(text("UPDATE ledger.entries SET payload = jsonb_set(payload, '{amount}', '4201'::jsonb) WHERE merchant_id = :merchant AND chain_index = 1"), {"merchant": merchant})
    owner.execute(text("ALTER TABLE ledger.entries ENABLE TRIGGER entries_no_update_delete"))
    result = verify(owner, merchant)
    assert not result.ok and result.broken_at == 1


def test_database_timezone_does_not_break_a_chain(runtime):
    entry = add(runtime)
    runtime.execute(text("SET LOCAL TIME ZONE 'Asia/Kolkata'"))
    assert verify(runtime, entry.merchant_id).ok
    add(runtime, entry.merchant_id)
    runtime.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    assert verify(runtime, entry.merchant_id).ok


def test_permission_denial_cannot_create_a_head(runtime):
    merchant = f"test-{uuid4().hex}"
    with pytest.raises(HTTPException) as error:
        add(runtime, merchant, role=Role.APP)
    assert error.value.status_code == 403
    assert runtime.execute(text("SELECT count(*) FROM ledger.chain_heads WHERE merchant_id = :merchant"), {"merchant": merchant}).scalar_one() == 0


def test_rollback_discards_entry_and_head_together(engines):
    merchant = f"test-{uuid4().hex}"
    with engines[0].connect() as connection:
        with connection.begin():
            savepoint = connection.begin_nested()
            add(connection, merchant)
            savepoint.rollback()
            assert connection.execute(text("SELECT count(*) FROM ledger.entries WHERE merchant_id = :merchant"), {"merchant": merchant}).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM ledger.chain_heads WHERE merchant_id = :merchant"), {"merchant": merchant}).scalar_one() == 0


def test_head_corruption_and_missing_head_are_detected(owner):
    entry = add(owner)
    owner.execute(text("UPDATE ledger.chain_heads SET hash = :hash WHERE merchant_id = :merchant"), {"hash": bytes(32), "merchant": entry.merchant_id})
    assert verify(owner, entry.merchant_id).broken_at == 1
    owner.execute(text("DELETE FROM ledger.chain_heads WHERE merchant_id = :merchant"), {"merchant": entry.merchant_id})
    assert verify(owner, entry.merchant_id).broken_at == 0


def test_concurrent_appends_keep_independent_merchant_chains(engines):
    merchants = [f"test-{uuid4().hex}" for _ in range(2)]
    def write(index):
        with engines[0].begin() as connection:
            return add(connection, merchants[index % 2])
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            entries = list(pool.map(write, range(24)))
        with engines[0].begin() as connection:
            for merchant in merchants:
                assert sorted(entry.chain_index for entry in entries if entry.merchant_id == merchant) == list(range(12))
                assert verify(connection, merchant).ok
    finally:
        # Only committed test merchants are cleaned, on the isolated test database.
        with engines[1].begin() as connection:
            connection.execute(text("ALTER TABLE ledger.entries DISABLE TRIGGER entries_no_update_delete"))
            connection.execute(text("DELETE FROM ledger.entries WHERE merchant_id IN (:first, :second)"), {"first": merchants[0], "second": merchants[1]})
            connection.execute(text("ALTER TABLE ledger.entries ENABLE TRIGGER entries_no_update_delete"))
            connection.execute(text("DELETE FROM ledger.chain_heads WHERE merchant_id IN (:first, :second)"), {"first": merchants[0], "second": merchants[1]})
