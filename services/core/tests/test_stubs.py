from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

import tasks
from app.auth import role_for_key
from app.config import get_settings
from app.main import app
from app.schemas.api import ENDPOINT_MODELS
from app.schemas.roles import ENDPOINT_PERMISSIONS, Role


NOW = "2026-03-24T09:30:00+05:30"
client = TestClient(app)


TRANSACTION = {
    "txn_id": "DM0000001",
    "merchant_id": "MID_DEMO_SAHANA",
    "ts": "2026-03-21T19:47:00+05:30",
    "direction": "CR",
    "amount": 4200,
    "channel": "UPI_POS",
    "counterparty_id": "P123",
    "counterparty_handle": "payer@upi",
    "counterparty_name": "DEMO CUSTOMER",
    "terminal_id": "POS01",
    "pos_bill_id": "BDM0000001",
    "utr": "608119000001",
    "orig_txn_id": None,
    "note": "",
}

DEBIT_TRANSACTION = {
    **TRANSACTION,
    "txn_id": "DM0000005",
    "direction": "DR",
    "channel": "UPI_OUT",
    "counterparty_id": "P-SUPPLIER",
    "counterparty_handle": "supplier@upi",
    "counterparty_name": "DEMO SUPPLIER",
    "terminal_id": None,
    "pos_bill_id": None,
    "utr": "608119000005",
    "note": "stock",
}


REQUEST_SAMPLES: dict[str, dict[str, Any]] = {
    "RailsCreditsRequest": {"transactions": [TRANSACTION], "sim_at": NOW},
    "RailsDebitsRequest": {"transactions": [DEBIT_TRANSACTION], "sim_at": NOW},
    "RailsBillsRequest": {"lines": [{"pos_bill_id": "BDM0000001", "txn_id": "DM0000001", "merchant_id": "MID_DEMO_SAHANA", "line_no": 1, "item": "Onions", "hsn": "0703", "qty": "2", "unit": "kg", "rate": "50", "line_amount": 100}], "sim_at": NOW},
    "RailsEventsRequest": {"events": [{"event_id": "EVENT-1", "merchant_id": "MID_DEMO_SAHANA", "ts": NOW, "type": "lien_marked", "freeze_type": "lien", "scope": "amount", "authority": {"unit": "Cyber Crime", "state": "Karnataka", "city": "Bengaluru"}, "ncrp_ack": "ACK1", "case_ref": "REF1", "disputed_amount": 4200, "disputed_date": "2026-03-21", "disputed_utr": "608119000001", "intimation": "Specimen"}], "sim_at": NOW},
    "ClassifyRulesRequest": {"merchant_id": "MID_DEMO_SAHANA", "as_of": NOW, "credits": [{"txn_id": "DM0000001", "amount": 4200, "channel": "UPI_POS", "counterparty_id": "P123", "counterparty_name": "DEMO CUSTOMER", "note": "", "has_bill": True, "prior_credit_count": 4, "merchant_has_paid_them": False, "own_account_cue": False, "surname_cue": False, "payer_fact": None}]},
    "LedgerProposalRequest": {"merchant_id": "MID_DEMO_SAHANA", "txn_id": "DM0000001", "proposal": {"label": "taxable_supply", "source": "rule", "rule_id": "bill-v1", "confidence": 1.0, "reason": "A POS bill is linked.", "evidence_refs": ["BDM0000001"], "memory_refs": []}, "sim_at": NOW},
    "SelectQuestionsRequest": {"merchant_id": "MID_DEMO_SAHANA", "as_of": NOW, "candidates": [{"txn_id": "DM0000002", "payer_id": "P124", "amount": 3000, "label": None, "confidence": 0.5, "strictly_prior_credit_count": 0, "has_bill": False, "payer_fact_known": False, "proposed_at": NOW}], "projected_turnover": 3900000, "threshold": 4000000, "already_asked_today": 0},
    "LedgerQuestionRequest": {"merchant_id": "MID_DEMO_SAHANA", "txn_id": "DM0000002", "question": {"question_id": "Q1", "text": "What was this payment for?", "language": "en", "expires_at": "2026-03-31T09:30:00+05:30"}, "sim_at": NOW},
    "LedgerClaimRequest": {"merchant_id": "MID_DEMO_SAHANA", "txn_id": "DM0000002", "action": "answered", "claim": {"question_id": "Q1", "answer": "family", "raw_text": "It was from family.", "language": "en"}, "sim_at": NOW},
    "TurnoverRequest": {"merchant_id": "MID_DEMO_SAHANA", "period_from": "2025-04-01", "period_to": "2026-03-31", "as_of": NOW},
    "ThresholdRequest": {"merchant_id": "MID_DEMO_SAHANA", "period_from": "2025-04-01", "period_to": "2026-03-31", "as_of": NOW, "supply_kind": "goods", "gst_status": "unregistered", "aggregate_turnover": 4100000, "exclusively_exempt": False},
    "IsolateRequest": {"merchant_id": "MID_DEMO_SAHANA", "case_id": "CASE-FREEZE-1", "disputed_utr": "608119000001", "disputed_amount": 4200, "disputed_date": "2026-03-21", "date_window_days": 1, "as_of": NOW},
    "TiersRequest": {"merchant_id": "MID_DEMO_SAHANA", "period_from": "2025-04-01", "period_to": "2026-03-31", "as_of": NOW, "case_id": "CASE-FREEZE-1", "opened_at": NOW},
    "EscalationCheckRequest": {"case_id": "CASE-FREEZE-1", "disputed_amount": 4200, "disputed_tier": 1, "effective_label": "taxable_supply", "claim_conflicts_with_bill": False, "merchant_disputed_label": False, "tier_3_4_share": 0.0, "prior_freeze_days_ago": None},
    "CreateCaseRequest": {"merchant_id": "MID_DEMO_SAHANA", "case_type": "freeze", "trigger_ref": "EVENT-1", "sim_at": NOW},
    "BuildPackRequest": {"merchant_id": "MID_DEMO_SAHANA", "case_id": "CASE-FREEZE-1", "pack_type": "freeze", "sim_at": NOW},
    "GuardRequest": {"text": "The disputed amount is Rs 4,200.", "context": {"disputed_amount": 4200}},
    "ApprovePackRequest": {"officer_ref": "OFFICER01", "note": "Evidence checked.", "sim_at": NOW},
    "RejectPackRequest": {"officer_ref": "OFFICER01", "reason": "Wrong attachment.", "sim_at": NOW},
    "SendPackRequest": {"destination": "simulated-outbox", "sim_at": NOW},
    "SimClockRequest": {"sim_at": NOW},
    "SimReplayRequest": {"split": "demo", "until": NOW},
    "SimResetRequest": {"split": "demo"},
    "SimTamperRequest": {"merchant_id": "MID_DEMO_SAHANA", "chain_index": 1, "replacement_label": "personal_transfer"},
    "RunAnchorRequest": {"sim_at": NOW, "simulated": True},
    "AssistantInboundRequest": {"merchant_id": "MID_DEMO_SAHANA", "message_id": "M1", "content_type": "text", "text": "Show my case", "sim_at": NOW},
    "AssistantOutboundRequest": {"merchant_id": "MID_DEMO_SAHANA", "conversation_id": "CONV1", "text": "Your pack is ready.", "language": "en", "in_reply_to": "M1", "sim_at": NOW},
    "PushSubscribeRequest": {"app": "merchant", "merchant_id": "MID_DEMO_SAHANA", "endpoint": "https://push.invalid/subscription", "expiration_time": None, "keys": {"p256dh": "fixture", "auth": "fixture"}},
    "AppProfileRequest": {"language": "kn-IN", "consent_at": NOW, "consent_text_version": "m0-v1-kn-IN"},
}


@pytest.fixture(autouse=True)
def stable_role_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for role in Role:
        monkeypatch.setenv(f"KEY_{role.value.upper()}", f"dev-{role.value}")


def concrete_path(contract_path: str) -> str:
    values = {"id": "CASE-FREEZE-1", "txn": "DM0000001", "utr": "608119000001", "cp": "P123", "m": "MID_DEMO_SAHANA", "pack": "PACK-1", "name": "hard-case-label"}
    return re.sub(r"\{([^}]+)\}", lambda match: values[match.group(1)], contract_path)


def key_for(endpoint: str) -> str:
    role = sorted(ENDPOINT_PERMISSIONS[endpoint], key=lambda item: item.value)[0]
    return f"dev-{role.value}"


@pytest.mark.parametrize("endpoint", ENDPOINT_MODELS)
def test_every_contract_route_is_reachable_and_its_fixture_validates(endpoint: str) -> None:
    method, contract_path = endpoint.split(" ", 1)
    request_model, response_model = ENDPOINT_MODELS[endpoint]
    body = None
    if request_model is not None:
        body = request_model.model_validate(REQUEST_SAMPLES[request_model.__name__]).model_dump(mode="json")

    response = client.request(
        method,
        concrete_path(contract_path),
        headers={"X-Hisaab-Key": key_for(endpoint)},
        json=body,
    )

    assert response.status_code == 200, (endpoint, response.text)
    response_model.model_validate(response.json())


def test_missing_key_explains_the_required_role() -> None:
    response = client.post("/rails/credits", json=REQUEST_SAMPLES["RailsCreditsRequest"])
    assert response.status_code == 403
    assert "X-Hisaab-Key" in response.json()["detail"]
    assert "rails" in response.json()["detail"]


def test_wrong_role_key_explains_the_required_role() -> None:
    response = client.post(
        "/rails/credits",
        headers={"X-Hisaab-Key": "dev-conversation"},
        json=REQUEST_SAMPLES["RailsCreditsRequest"],
    )
    assert response.status_code == 403
    assert "conversation" in response.json()["detail"]
    assert "rails" in response.json()["detail"]


def test_credit_and_debit_ingest_reject_the_other_direction() -> None:
    credit_response = client.post(
        "/rails/credits",
        headers={"X-Hisaab-Key": "dev-rails"},
        json={"transactions": [DEBIT_TRANSACTION], "sim_at": NOW},
    )
    debit_response = client.post(
        "/rails/debits",
        headers={"X-Hisaab-Key": "dev-rails"},
        json={"transactions": [TRANSACTION], "sim_at": NOW},
    )
    assert credit_response.status_code == 422
    assert debit_response.status_code == 422


@pytest.mark.parametrize("extra", [{"label": "refund_reversal"}, {"pos_bill_id": "BDM5"}])
def test_debit_ingest_rejects_labels_and_bill_links(extra: dict[str, str]) -> None:
    transaction = {**DEBIT_TRANSACTION, **extra}
    response = client.post(
        "/rails/debits",
        headers={"X-Hisaab-Key": "dev-rails"},
        json={"transactions": [transaction], "sim_at": NOW},
    )
    assert response.status_code == 422


def test_app_key_is_refused_by_a_ledger_appending_endpoint_with_a_reason() -> None:
    response = client.post(
        "/ledger/claims",
        headers={"X-Hisaab-Key": "dev-app"},
        json=REQUEST_SAMPLES["LedgerClaimRequest"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Role 'app' is not permitted; this endpoint needs role conversation."
    )


def test_app_key_is_loaded_by_settings_and_auth() -> None:
    assert get_settings().role_keys[Role.APP] == "dev-app"
    assert role_for_key("dev-app") is Role.APP


def test_openapi_contains_every_contracted_operation() -> None:
    document = app.openapi()
    operations = {
        (method.upper(), path)
        for path, methods in document["paths"].items()
        for method in methods
        if method in {"get", "post", "put"}
    }
    expected = {
        (method, path)
        for endpoint in ENDPOINT_MODELS
        for method, path in [endpoint.split(" ", 1)]
    }
    assert expected <= operations


def test_live_setting_and_paid_publish_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HISAAB_LIVE", "0")
    assert get_settings().hisaab_live is False
    with pytest.raises(RuntimeError, match="HISAAB_LIVE must be 1"):
        tasks._publish_n8n("https://example.trycloudflare.com", "", {"HISAAB_LIVE": "0"})
