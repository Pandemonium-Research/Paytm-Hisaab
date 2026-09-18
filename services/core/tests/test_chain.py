from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.auth import check_entry_kind
from app.ledger.chain import GENESIS_HASH, canonical_json, entry_hash
from app.ledger.verify import broken_index
from app.schemas.ledger import EntryKind
from app.schemas.roles import ROLE_ENTRY_KINDS, Role


NOW = datetime(2026, 3, 24, 4, 0, tzinfo=timezone.utc)


def row(index=0, previous=GENESIS_HASH):
    value = {
        "merchant_id": "M", "chain_index": index, "kind": "credit.observed", "txn_id": "T",
        "payload": {"counterparty_id": "P", "channel": "UPI_QR", "amount": 4200},
        "actor_role": "rails", "actor_ref": "replayer", "sim_at": NOW, "recorded_at": NOW,
        "prev_hash": previous,
    }
    value["hash"] = entry_hash(value, previous)
    return value


def test_hash_uses_frozen_fields_and_raw_previous_bytes():
    expected = (
        '{"actor_role":"rails","chain_index":0,"kind":"credit.observed","merchant_id":"M",'
        '"payload":{"amount":4200,"channel":"UPI_QR","counterparty_id":"P"},'
        '"recorded_at":"2026-03-24T04:00:00.000000+00:00","sim_at":"2026-03-24T04:00:00.000000+00:00",'
        '"txn_id":"T"}'
    ).encode()
    assert row()["hash"] == hashlib.sha256(expected + bytes(32)).digest()
    assert entry_hash(dict(reversed(list(row().items()))), GENESIS_HASH) == row()["hash"]


def test_canonical_json_preserves_kannada_array_order_and_equivalent_instants():
    assert canonical_json({"b": [2, 1], "a": "ಧನ್ಯವಾದಗಳು"}) == '{"a":"ಧನ್ಯವಾದಗಳು","b":[2,1]}'.encode()
    assert canonical_json(NOW) == canonical_json(NOW.astimezone(timezone(timedelta(hours=5, minutes=30))))
    assert canonical_json([1, 2]) != canonical_json([2, 1])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), datetime(2026, 3, 24)])
def test_canonical_json_rejects_ambiguous_values(invalid):
    with pytest.raises(ValueError):
        canonical_json(invalid)


def test_verification_reports_first_edit_gap_and_changed_link():
    first = row()
    second = row(1, first["hash"])
    third = row(2, second["hash"])
    assert broken_index([first, second, third]) is None
    assert broken_index([first, third]) == 1
    assert broken_index([first, {**second, "prev_hash": bytes(32)}, third]) == 1
    second["payload"]["amount"] = 4201
    assert broken_index([first, second, third]) == 1


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("kind", list(EntryKind))
def test_every_role_and_entry_kind_pair_enforces_the_frozen_policy(role, kind):
    if kind in ROLE_ENTRY_KINDS[role]:
        check_entry_kind(role, kind)
    else:
        with pytest.raises(HTTPException) as error:
            check_entry_kind(role, kind)
        assert error.value.status_code == 403
        assert role.value in error.value.detail
        assert kind.value in error.value.detail
