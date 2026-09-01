"""An expense-claims project, built to be measured: every figure the measure page draws.

One pipeline reads an expense claim, extracts what it says, checks it against the expense
policy, decides, has the decision audited, and either books it, refuses it, or hands it to
finance. Finance is a step that decides for itself: it can look the vendor up in the supplier
registry (which costs money per call) and can ask a person. A claim finance cannot settle is
parked, which is the answer the evaluation scores as an absence.

The shape exists so the page has a labelled step in the middle (``extract``), a labelled
decision (``decide``), a bounded revision loop, a step that decides for itself, a paid tool,
a written resource, and rungs to cut at ``extract`` and ``policy_check``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from simple_agents import (
    AgentNode,
    Budget,
    DeclaredCost,
    Deterministic,
    Join,
    LLMNode,
    Loop,
    Maybe,
    Pipeline,
    Unknown,
    pipeline_factory,
)
from simple_agents.builtins import consult
from simple_agents.tools import SideEffectClass, tool

# -- the policy ---------------------------------------------------------------------------

LIMITS = {"meals": 75.0, "travel": 400.0, "equipment": 500.0, "software": 200.0, "other": 100.0}
RECEIPT_REQUIRED_OVER = 25.0
MAX_AGE_DAYS = 90
PO_REQUIRED = {"software"}

APPROVED_SUPPLIERS = (
    "Northwind Stationery", "Brightline Rail", "Kestrel Software", "Harbour Hotels",
    "Ashgrove Audio", "Meridian Cabs",
)

POLICY_TEXT = (
    "The expense policy. A receipt is required for any claim over £25; a bank or card "
    "statement is not a receipt, and a mileage log is the receipt for mileage. A claim for "
    "an expense more than 90 days old is refused. Each category has a limit per claim: meals "
    "£75, travel £400, equipment £500, software £200, other £100; a claim over its limit goes "
    "to finance. Software always needs a PO number, whatever the amount; without one it goes "
    "to finance. Refusal comes first: a claim that fails the receipt or age rule is refused "
    "even where it would also have gone to finance. Everything else is approved."
)


def canonical_vendor(name: Any) -> str:
    """A vendor name with case, punctuation and a company suffix taken off, for matching."""
    if not isinstance(name, str):
        return ""
    words = "".join(ch if ch.isalnum() or ch == " " else " " for ch in name.lower()).split()
    return " ".join(w for w in words if w not in {"ltd", "limited", "plc", "the", "inc"})


# -- schemas ---------------------------------------------------------------------------------


class Claim(BaseModel):
    """What one expense claim says, read off the text the claimant sent."""

    vendor: Maybe[str] = Field(
        description='Who was paid: the shop, hotel, rail company or supplier as named. Send '
        '{"type": "unknown", "reason": "..."} where the claim names no vendor, such as a cash '
        'purchase from a market stall or a mileage claim.'
    )
    total: Maybe[float] = Field(
        description="The amount claimed in pounds, as one number. Where the claim lists "
        "lines, service or VAT, the total is the sum actually paid. Where two receipts are "
        'claimed together it is their sum. Send {"type": "unknown", "reason": "..."} where '
        "no amount can be read."
    )
    category: Literal["meals", "travel", "equipment", "software", "other"] = Field(
        description="meals: food and drink. travel: transport, hotels, parking, mileage. "
        "equipment: physical things for work. software: licences, seats, subscriptions and "
        "credits for software services. other: anything else, such as tickets, printing, "
        "memberships or stock images."
    )
    po_number: Maybe[str] = Field(
        description='The purchase order number exactly as written (for example "PO-80115"). '
        'Send {"type": "unknown", "reason": "..."} where the claim states none.'
    )
    receipt: Literal["receipt", "statement", "none"] = Field(
        description="What proof is attached: a receipt, invoice, e-ticket or mileage log is "
        "'receipt'; a bank or card statement is 'statement'; nothing is 'none'."
    )
    expense_date: Maybe[str] = Field(
        description='The date the expense was incurred, as YYYY-MM-DD. Dates in the claim '
        "are written day first (03/08/2026 is 3 August 2026). Send "
        '{"type": "unknown", "reason": "..."} where the claim gives no date.'
    )
    submitted_on: str = Field(
        description="The submission date given with the claim, copied as YYYY-MM-DD."
    )


class Decision(BaseModel):
    decision: Literal["approve", "reject", "escalate"]
    reason: Maybe[str] = Field(description="One sentence naming the rule the decision rests on.")


class Audit(BaseModel):
    agrees: bool = Field(description="Whether the decision follows the policy as stated.")
    decision: Literal["approve", "reject", "escalate"] = Field(
        description="The decision the policy gives. The same as the one audited where it agrees."
    )
    why: Maybe[str] = Field(description="Where it disagrees, which rule was misapplied.")


class FinanceDecision(BaseModel):
    decision: Literal["approve", "reject", "park"] = Field(
        description="approve where the vendor is an approved supplier; park where no one can "
        "settle it now; reject only where the claim breaks a rule outright."
    )
    reason: Maybe[str]


# -- tools -----------------------------------------------------------------------------------


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="policy")
def policy_lookup(category: str) -> dict:
    """The expense policy for one category: its limit and whether a PO number is required."""
    return {
        "category": category,
        "limit": LIMITS.get(category, LIMITS["other"]),
        "po_required": category in PO_REQUIRED,
        "receipt_required_over": RECEIPT_REQUIRED_OVER,
        "max_age_days": MAX_AGE_DAYS,
    }


@tool(
    side_effect_class=SideEffectClass.SPENDS_MONEY,
    declared_cost=DeclaredCost(currency="USD", per_call=0.002),
    touches="supplier_registry",
)
def vendor_registry(vendor: str) -> dict:
    """Look a vendor up in the approved-supplier registry. Charged per lookup."""
    wanted = canonical_vendor(vendor)
    for name in APPROVED_SUPPLIERS:
        if canonical_vendor(name) == wanted:
            return {"vendor": name, "approved_supplier": True}
    return {"vendor": vendor, "approved_supplier": False}


@tool(side_effect_class=SideEffectClass.WRITES, touches="ledger")
def post_ledger(vendor: str, total: float, category: str) -> dict:
    """Post one approved claim to the ledger. Returns the entry it made."""
    return {"entry": f"LEDGER-{abs(hash((vendor, total, category))) % 100000:05d}"}


def ask_finance(question, options=None, about=None):
    """Stand in for the person in finance, on a live run outside an evaluation."""
    return options[0] if options else "park it"


# -- the steps -------------------------------------------------------------------------------


def intake(inputs: dict, ctx) -> dict:
    """Take one claim off the claims inbox, which this step reaches in its own code."""
    claim = inputs["claim"]
    ctx.record_access(
        "claims_inbox", "read",
        inputs={"status": "submitted"},
        outputs={"waiting": 57, "taken": 1, "characters": len(claim)},
    )
    return {"claim": claim, "submitted_on": inputs.get("submitted_on", "2026-08-20")}


def extract(inputs: dict, ctx) -> str:
    return (
        "Read this expense claim and fill every field. Claims arrive as app entries, emails "
        "or scanned receipts, so the text can be terse or noisy. Do not decide anything; "
        f"only read what it says.\n\nSubmitted on: {inputs['submitted_on']}\n\n"
        f"Claim:\n{inputs['claim']}"
    )


def _field(held: Any, name: str) -> Any:
    return held.get(name) if isinstance(held, dict) else getattr(held, name)


def _absent(value: Any) -> bool:
    return isinstance(value, Unknown) or (isinstance(value, dict) and value.get("type") == "unknown")


def policy_check(inputs: Any, ctx) -> dict:
    """Apply the parts of the policy that are arithmetic, and hand the rest to `decide`."""
    fields = {name: _field(inputs, name) for name in
              ("vendor", "total", "category", "po_number", "receipt", "expense_date",
               "submitted_on")}
    policy = ctx.call_tool("policy_lookup", category=str(fields["category"]))
    total = fields["total"] if isinstance(fields["total"], (int, float)) else None
    age_days = None
    if isinstance(fields["expense_date"], str):
        try:
            age_days = (date.fromisoformat(str(fields["submitted_on"]))
                        - date.fromisoformat(fields["expense_date"])).days
        except ValueError:
            age_days = None
    flags = {
        "receipt_missing": fields["receipt"] != "receipt" and (total is None or total > policy["receipt_required_over"]),
        "stale": age_days is not None and age_days > policy["max_age_days"],
        "over_limit": total is not None and total > policy["limit"],
        "po_missing": policy["po_required"] and _absent(fields["po_number"]),
        "total_unreadable": total is None,
    }
    return {**fields, "age_days": age_days, "limit": policy["limit"],
            "po_required": policy["po_required"], "flags": flags}


def _facts(facts: dict) -> str:
    return (
        f"Vendor: {facts['vendor']}\nTotal: {facts['total']}\nCategory: {facts['category']} "
        f"(limit £{facts['limit']:.0f}, PO required: {facts['po_required']})\n"
        f"PO number: {facts['po_number']}\nProof attached: {facts['receipt']}\n"
        f"Expense date: {facts['expense_date']} ({facts['age_days']} days before submission)\n"
        f"Checks: {facts['flags']}"
    )


def _facts_and_note(inputs: Any) -> tuple[dict, str]:
    """What decide reads: the facts alone (one in-edge), or with the audit's note (a Join)."""
    if isinstance(inputs, Join):
        note = "" if "audit" in inputs.absent else (
            f"\n\nThe audit sent the last decision back: {inputs['audit'].why}"
        )
        return inputs["policy_check"], note
    return inputs, ""


def decide(inputs: Any, ctx) -> str:
    facts, sent_back = _facts_and_note(inputs)
    return (
        f"{POLICY_TEXT}\n\nDecide this claim: approve, reject, or escalate to finance. The "
        f"checks were computed from the claim and may be wrong where a field was misread; "
        f"the facts above them are what to decide on.\n\n{_facts(facts)}{sent_back}"
    )


def decide_v1(inputs: Any, ctx) -> str:
    """The prompt as first written, kept so an earlier evaluation measures a different behaviour."""
    facts, _ = _facts_and_note(inputs)
    return (
        "Decide this expense claim under the usual policy: receipts over £25, nothing older "
        "than 90 days, category limits (meals 75, travel 400, equipment 500, software 200, "
        "other 100), software needs a PO. Answer approve, reject, or escalate to finance.\n\n"
        f"{_facts(facts)}"
    )


def audit(inputs: Join, ctx) -> str:
    facts = inputs["policy_check"]
    decision = inputs["decide"]
    return (
        f"{POLICY_TEXT}\n\nA colleague decided this claim: {decision.decision} "
        f"({decision.reason}). Check the decision against the policy and the facts. Say "
        f"whether it follows the policy, and what the policy gives.\n\n{_facts(facts)}"
    )


def audit_route(output: Audit, ctx) -> str:
    return "dispatch" if output.agrees else "decide"


def dispatch(inputs: Join, ctx) -> dict:
    """Send the audited decision where it goes, carrying the facts with it."""
    facts = dict(inputs["policy_check"])
    verdict = inputs["audit"]
    if verdict.agrees:
        return {**facts, "decision": verdict.decision, "reason": None}
    return {**facts, "decision": "escalate",
            "reason": "the decision and its audit could not agree, so finance has it"}


def dispatch_route(output: dict, ctx) -> list:
    if output["decision"] == "approve":
        return ["book", "notify"]
    if output["decision"] == "escalate":
        return ["finance", "notify"]
    return ["notify"]


def finance_prompt(inputs: dict, ctx) -> str:
    return (
        "A claim has been escalated to finance. Rule: a claim from an approved supplier is "
        "approved; look the vendor up in the registry to find out. Where the vendor is not "
        "an approved supplier, or no vendor is named, ask the finance lead whether to approve "
        "it, and park the claim if no answer comes. Reject only where the claim breaks a rule "
        f"outright.\n\n{_facts(inputs)}"
    )


def finance_route(output: FinanceDecision, ctx) -> str:
    return "book" if output.decision == "approve" else "notify"


def book(inputs: Any, ctx) -> dict:
    facts = inputs if isinstance(inputs, dict) and "vendor" in inputs else None
    if facts is None:
        # Reached from finance, whose output is its decision alone.
        return {"posted": True, "entry": None}
    total = facts["total"] if isinstance(facts["total"], (int, float)) else 0.0
    vendor = facts["vendor"] if isinstance(facts["vendor"], str) else "unnamed"
    entry = ctx.call_tool("post_ledger", vendor=vendor, total=total, category=str(facts["category"]))
    return {"posted": True, "entry": entry["entry"]}


def notify(inputs: Join, ctx) -> dict:
    """Tell the claimant, and produce the record the evaluation scores."""
    facts = inputs["dispatch"]
    if "finance" not in inputs.absent:
        settled = inputs["finance"]
        decision = settled.decision
        reason = settled.reason if isinstance(settled.reason, str) else None
    else:
        decision = facts["decision"]
        reason = facts.get("reason")
    posted = "book" not in inputs.absent and bool(inputs["book"].get("posted"))
    (ctx.workspace / "notice.txt").write_text(
        f"{decision}: {reason or 'per policy'}", encoding="utf-8"
    )
    ctx.record_access(
        "outbox", "write",
        inputs={"decision": decision},
        outputs={"sent": True},
    )
    return {
        "decision": decision,
        "vendor": facts["vendor"],
        "total": facts["total"],
        "category": facts["category"],
        "po_number": facts["po_number"],
        "reason": reason,
        "posted": posted,
    }


# -- the pipeline ----------------------------------------------------------------------------


@pipeline_factory("claims")
def claims() -> Pipeline:
    return build()


def build(*, prompt_version: int = 2, registry: bool = True, revisions: int = 2) -> Pipeline:
    """The claims graph, with the knobs a variant or an earlier evaluation turns.

    ``prompt_version=1`` is the decide prompt as first written, ``registry=False`` takes the
    supplier registry away from finance, and ``revisions=1`` stops the audit sending a
    decision back: a disagreement goes straight to finance.
    """
    finance_tools = [policy_lookup, consult(ask_finance, answered_by="end_user")]
    if registry:
        finance_tools.insert(0, vendor_registry)
    nodes = [
        Deterministic(intake, node_id="intake", successors=["extract"], touches="claims_inbox"),
        LLMNode(extract, output_schema=Claim, node_id="extract",
                successors=["policy_check"], max_output_tokens=600),
        Deterministic(
            policy_check, node_id="policy_check", tools=[policy_lookup],
            successors=["decide", "audit", "dispatch"],
            route=lambda output, ctx: ["decide", "audit", "dispatch"],
        ),
        LLMNode(decide if prompt_version == 2 else decide_v1, output_schema=Decision,
                node_id="decide", successors=["audit"], max_output_tokens=300),
        LLMNode(audit, output_schema=Audit, node_id="audit",
                successors=["decide", "dispatch"], route=audit_route,
                loop=Loop(max_iterations=revisions, then="dispatch"), max_output_tokens=300),
        Deterministic(dispatch, node_id="dispatch",
                      successors=["book", "finance", "notify"], route=dispatch_route),
        AgentNode(
            finance_prompt, output_schema=FinanceDecision, node_id="finance",
            tools=finance_tools,
            budget=Budget(max_steps=4, max_tokens=8_000, max_cost=0.02, max_wall_clock_ms=None),
            successors=["book", "notify"], route=finance_route, max_output_tokens=400,
        ),
        Deterministic(book, node_id="book", successors=["notify"], tools=[post_ledger]),
        Deterministic(notify, node_id="notify", successors=[], touches="outbox"),
    ]
    return Pipeline(
        nodes,
        budget=Budget(max_steps=12, max_tokens=40_000, max_cost=0.05, max_wall_clock_ms=None),
    )

