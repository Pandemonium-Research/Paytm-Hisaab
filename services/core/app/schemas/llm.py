"""LLM output schemas (task 1.4, owned by B).

Every Sarvam call in IMPLEMENTATION_PLAN.md §8 returns one of these shapes. Core validates the
model's JSON against them before anything reaches the ledger; n8n's Structured Output Parser
nodes use the JSON Schema exported from here, so the workflow and core agree by construction.

Ownership: this file is B's, inside A's `services/core/` tree (LANES.md §1). B does not edit
anything else under `services/core/`.

Rules carried over from §8:
- **Numbers never pass through the LLM.** Free-text fields hold `{placeholder}` slots; core
  formats amounts in the Indian style per locale. The one exception is notice extraction, where
  the number is read *off the document* and the extraction guard requires every number to appear
  verbatim in the OCR text.
- Agent confidence is capped at 0.85 by `POST /ledger/proposals` (§7). The cap is enforced in
  core, not here, so a model that returns 0.99 is recorded as over-confident rather than silently
  clipped at parse time.
- On a guard failure the caller retries once with the violation fed back, then falls back to
  template-only text (§8).
"""

from __future__ import annotations

from datetime import date as Date  # aliased: NoticeExtraction has a field named `date`
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Reject unknown keys, so a drifting prompt fails loudly instead of losing a field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------------------
# Shared enums
# --------------------------------------------------------------------------------------


class Label(str, Enum):
    """The seven ledger labels, mirroring `sim.catalog.LABELS` exactly.

    Kept in lockstep with the simulator on purpose: `eval/score.py` scores predictions against
    these, so any divergence would silently tank the measured accuracy.
    """

    TAXABLE_SUPPLY = "taxable_supply"
    EXEMPT_SUPPLY = "exempt_supply"
    PERSONAL_TRANSFER = "personal_transfer"
    INTER_ACCOUNT = "inter_account"
    NON_BUSINESS = "non_business"
    REFUND_REVERSAL = "refund_reversal"
    DUPLICATE = "duplicate"


class PredictedLabel(str, Enum):
    """`Label` plus `unclassified`, which is an allowed *answer* but never a ground truth.

    Mirrors `sim.catalog.PREDICTION_LABELS`. A model that is unsure must say so here rather than
    guess: an unclassified credit becomes a question candidate, and a wrong confident label does
    not.
    """

    TAXABLE_SUPPLY = "taxable_supply"
    EXEMPT_SUPPLY = "exempt_supply"
    PERSONAL_TRANSFER = "personal_transfer"
    INTER_ACCOUNT = "inter_account"
    NON_BUSINESS = "non_business"
    REFUND_REVERSAL = "refund_reversal"
    DUPLICATE = "duplicate"
    UNCLASSIFIED = "unclassified"


class MerchantAnswer(str, Enum):
    """What a merchant may tap on M2, or reply with a digit on WhatsApp.

    Mirrors the keys of `sim.catalog.ANSWER_CHOICES`. The enum keeps all 7; each channel shows a
    subset (WhatsApp numbers 4, the M2 chips show 5, voice and free text reach all 7). The decision
    and the measurements behind it are under Decisions in `n8n/README.md`.

    TODO(1.4): A's `AnswerChoice` is the same enum. Once A's schemas land, import it here and
    delete this class, so there is one definition (agreed with A, 18 Sep).
    """

    SALE = "sale"
    FAMILY = "family"
    OWN_MONEY = "own_money"
    LOAN_OR_GIFT = "loan_or_gift"
    REFUND = "refund"
    DOUBLE_PAYMENT = "double_payment"
    NOT_SURE = "not_sure"


class EvidenceKind(str, Enum):
    """Where a piece of reasoning came from, for `evidence_used`.

    `memory_recall` is called out separately because §9's guardrail forbids recalled memory from
    counting toward tiers 1 or 2 — core needs to see it named to apply that.
    """

    RULES_OUTPUT = "rules_output"
    PAYER_HISTORY = "payer_history"
    BILL = "bill"
    DEVICE_GEO = "device_geo"
    MEMORY_RECALL = "memory_recall"
    CREDIT_FIELDS = "credit_fields"


# --------------------------------------------------------------------------------------
# 1. Hard-case labelling  ·  sarvam-105b  ·  WF10
# --------------------------------------------------------------------------------------


class HardCaseLabel(_Strict):
    """§8 row 1: `{label, confidence, reason_en, evidence_used[]}`.

    Produced for credits that `classify_rules` returned `null` for. Feeds `POST /ledger/proposals`,
    which caps confidence at 0.85 and appends `label.proposed`.
    """

    label: PredictedLabel = Field(
        description="Best label, or 'unclassified' when the evidence does not support one."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Model's own confidence. Core caps this at 0.85 for agent proposals; values above "
            "the cap are recorded as over-confident, not silently clipped."
        ),
    )
    reason_en: str = Field(
        min_length=1,
        max_length=400,
        description=(
            "One or two sentences in English explaining the call, for the ledger and the officer "
            "view. English regardless of the merchant's language: the merchant-facing wording is "
            "generated separately from templates."
        ),
    )
    evidence_used: list[EvidenceKind] = Field(
        default_factory=list,
        description=(
            "What the model actually leaned on. Anything containing 'memory_recall' is logged in "
            "memory_refs and barred from tiers 1-2 (§9)."
        ),
    )


# --------------------------------------------------------------------------------------
# 2. Intent of a merchant message  ·  sarvam-105b-conversations  ·  WF31
# --------------------------------------------------------------------------------------


class Intent(str, Enum):
    """§8 row 2. Button taps and numbered replies skip the LLM and route directly."""

    ANSWER_QUESTION = "answer_question"
    ASK_STATUS = "ask_status"
    REPORT_FREEZE = "report_freeze"
    SEND_NOTICE = "send_notice"
    CORRECT_LABEL = "correct_label"
    DISPUTE_LABEL = "dispute_label"
    HIDE_INCOME = "hide_income"
    HELP = "help"
    OTHER = "other"


class IntentSlots(_Strict):
    """Slots the intent may carry. All optional: an intent with no slots is valid.

    Note there is no free-text amount slot. If the merchant says an amount, the workflow resolves
    it against the pending question's credit rather than trusting a parsed number (§8: numbers
    never pass through the LLM).
    """

    txn_id: str | None = Field(
        default=None,
        description="Credit the message is about, when the merchant names one or replies to a question.",
    )
    answer: MerchantAnswer | None = Field(
        default=None,
        description="Only for answer_question / correct_label. Must be one of the tap choices.",
    )
    payer_hint: str | None = Field(
        default=None,
        max_length=120,
        description="Free-text relationship the merchant offered, e.g. 'my wife'. Written to payer_facts by core, never used as a number.",
    )
    case_id: str | None = Field(default=None, description="Only for ask_status about a known case.")


class MessageIntent(_Strict):
    """What WF31 routes on."""

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    slots: IntentSlots = Field(default_factory=IntentSlots)
    language: str = Field(
        min_length=2,
        max_length=8,
        description="BCP-47-ish tag detected for the message (kn, hi, ta, te, mr, bn, en). Drives the reply language.",
    )


# --------------------------------------------------------------------------------------
# 3. Notice extraction  ·  Sarvam Vision -> sarvam-105b  ·  WF40
# --------------------------------------------------------------------------------------


class NoticeExtraction(_Strict):
    """§8 row 6: `{authority, reference, date, period, claimed_turnover, allegation, due_date}`.

    The one schema where a number is allowed to come from the model, because it is read off the
    document. `POST /guards/extraction` then requires every number here to appear verbatim in the
    OCR text; a number the guard cannot find blocks the pack.
    """

    authority: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=120, description="Notice reference number as printed.")
    date: Date = Field(description="Date on the notice.")
    period_from: Date
    period_to: Date
    claimed_turnover_paise: int = Field(
        ge=0,
        description=(
            "Turnover the notice claims, in paise as an integer. Paise because every amount in "
            "core is an integer; a float here would round-trip badly against the OCR text."
        ),
    )
    claimed_turnover_as_printed: str = Field(
        min_length=1,
        max_length=60,
        description=(
            "The turnover string exactly as it appears on the document, e.g. '53,16,632'. The "
            "extraction guard matches on this, not on the parsed integer."
        ),
    )
    allegation: str = Field(min_length=1, max_length=600, description="What the notice alleges, in its own words.")
    due_date: Date | None = Field(default=None, description="Reply-by date, when the notice states one.")


# --------------------------------------------------------------------------------------
# 4-6. Generated prose  ·  sarvam-105b
# --------------------------------------------------------------------------------------


class GeneratedProse(_Strict):
    """Base for the three text generators (§8 rows 7-9).

    All three carry `placeholders_used` so the numbers guard can verify the model filled only
    slots it was given, and invented none. The template supplies structure and citations; the
    model supplies only the connecting prose.
    """

    text: str = Field(min_length=1)
    placeholders_used: list[str] = Field(
        default_factory=list,
        description="Every {slot} the text references. Core checks this against the slots it supplied.",
    )
    language: str = Field(min_length=2, max_length=8)


class GrievanceFacts(GeneratedProse):
    """§8 row 7: the facts paragraph inside the grievance template.

    Guards applied after generation: `numbers`, `citations`, `no-innocence`. The no-innocence
    guard is the important one — this text must never assert the merchant is innocent, only what
    the evidence shows.
    """

    text: str = Field(min_length=1, max_length=1500)


class Explainer(GeneratedProse):
    """§8 row 8: CA explainer (English) and merchant explainer (their language).

    Two audiences, one schema; `audience` picks the register. Numbers guard applies.
    """

    audience: Literal["ca", "merchant"]
    text: str = Field(min_length=1, max_length=2000)


class HandoffSummary(GeneratedProse):
    """§8 row 9: short summary for the officer queue, produced by WF50. Numbers guard applies."""

    text: str = Field(min_length=1, max_length=800)
    escalation_reasons: list[str] = Field(
        default_factory=list,
        description="Reason codes from skills/escalation, echoed so O1 can show them without a second call.",
    )


__all__ = [
    "Label",
    "PredictedLabel",
    "MerchantAnswer",
    "EvidenceKind",
    "HardCaseLabel",
    "Intent",
    "IntentSlots",
    "MessageIntent",
    "NoticeExtraction",
    "GeneratedProse",
    "GrievanceFacts",
    "Explainer",
    "HandoffSummary",
]
