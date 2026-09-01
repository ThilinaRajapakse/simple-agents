"""The example set, written as claims with their facts; every label is derived from the policy.

The claim text is what the pipeline reads. The facts beside it are what `extract` should
read off it and are its label; the decision each claim gets is computed here from the same
rules the policy states, so a label can never disagree with the policy it is scored under.
A claim finance cannot settle unattended (an escalation from a vendor that is not an
approved supplier) has an absence for its answer, because the pipeline parks it.

    uv run python examples.py      # writes evals/examples.jsonl
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from simple_agents import Unknown
from simple_agents.evaluation import Criteria, Criterion, Example, ExampleSet

from agent import (
    APPROVED_SUPPLIERS,
    LIMITS,
    MAX_AGE_DAYS,
    PO_REQUIRED,
    RECEIPT_REQUIRED_OVER,
    canonical_vendor,
)

SUBMITTED_ON = "2026-08-20"

# id, split, source, text, vendor, total, category, po, proof, expense date
CLAIMS = [
    ("c-001", "held_out", "app",
     "Client lunch at The Copper Kettle, 14 Aug 2026. Total £48.30 incl. service. Receipt attached.",
     "The Copper Kettle", 48.30, "meals", None, "receipt", "2026-08-14"),
    ("c-002", "held_out", "email",
     "Hi, claiming my train to Manchester on 3 August for the Quill onboarding. Brightline Rail, "
     "£112.40 return, e-ticket receipt attached. Thanks, Priya",
     "Brightline Rail", 112.40, "travel", None, "receipt", "2026-08-03"),
    ("c-003", "held_out", "scanned",
     "NORTHWIND STATIONERY LTD   RECEIPT   02-AUG-2026\nMONITOR ARM x1   189.00\nVAT 20%   37.80\n"
     "TOTAL   226.80\nPO: PO-77812",
     "Northwind Stationery", 226.80, "equipment", "PO-77812", "receipt", "2026-08-02"),
    ("c-004", "held_out", "app",
     "Kestrel Software annual licence renewal, £180.00, paid 10/08/2026, invoice attached, PO-80115.",
     "Kestrel Software", 180.00, "software", "PO-80115", "receipt", "2026-08-10"),
    ("c-005", "held_out", "email",
     "Claiming the Figma seat I bought on 12 Aug: £144.00 on the company card, receipt below. "
     "Didn't raise a PO, sorry.",
     "Figma", 144.00, "software", None, "receipt", "2026-08-12"),
    ("c-006", "held_out", "app",
     "Team dinner, Harbour Hotels restaurant, 7 Aug 2026, £212.00 for six people, receipt attached.",
     "Harbour Hotels", 212.00, "meals", None, "receipt", "2026-08-07"),
    ("c-007", "held_out", "scanned",
     "MERIDIAN CABS   11 AUG 26   AIRPORT-OFFICE   63.00   CARD   RECEIPT",
     "Meridian Cabs", 63.00, "travel", None, "receipt", "2026-08-11"),
    ("c-008", "held_out", "email",
     "Sandwich and coffee from Pret during the offsite, 18 Aug, £9.80. Lost the receipt.",
     "Pret", 9.80, "meals", None, "none", "2026-08-18"),
    ("c-009", "held_out", "app",
     "Hotel for the Leeds audit, Harbour Hotels, 2 nights 4-6 Aug 2026, £436.00, invoice attached.",
     "Harbour Hotels", 436.00, "travel", None, "receipt", "2026-08-04"),
    ("c-010", "held_out", "email",
     "Bought a second-hand desk from a colleague for £60 in cash on 15 August. No receipt, he can vouch.",
     None, 60.00, "equipment", None, "none", "2026-08-15"),
    ("c-011", "held_out", "scanned",
     "THE COPPER KETTLE   22/04/2026\nLUNCH 2 COVERS   41.50\nSERVICE   4.15\nTOTAL   45.65",
     "The Copper Kettle", 45.65, "meals", None, "receipt", "2026-04-22"),
    ("c-012", "dev", "app",
     "Conference ticket, DataWeek London, £95.00, 9 Aug 2026, receipt attached.",
     "DataWeek", 95.00, "other", None, "receipt", "2026-08-09"),
    ("c-013", "held_out", "email",
     "Printing 40 booklets for the client workshop at Northwind Stationery, £132.50 on 13 Aug, "
     "receipt attached.",
     "Northwind Stationery", 132.50, "other", None, "receipt", "2026-08-13"),
    ("c-014", "held_out", "app",
     "Ashgrove Audio transcription credits £220.00, 5 Aug 2026, PO-80231, receipt attached.",
     "Ashgrove Audio", 220.00, "software", "PO-80231", "receipt", "2026-08-05"),
    ("c-015", "held_out", "email",
     "Flights to Dublin for the Rowan pitch, booked 30 July, £289.99 with Aer Lingus. Card "
     "statement attached as proof.",
     "Aer Lingus", 289.99, "travel", None, "statement", "2026-07-30"),
    ("c-016", "dev", "scanned",
     "BREAKFAST   HARBOUR HOTELS   06/08/2026   14.50   RECEIPT",
     "Harbour Hotels", 14.50, "meals", None, "receipt", "2026-08-06"),
    ("c-017", "held_out", "app",
     "Noise-cancelling headphones, Ashgrove Audio, £249.00, 1 Aug 2026, receipt attached.",
     "Ashgrove Audio", 249.00, "equipment", None, "receipt", "2026-08-01"),
    ("c-018", "held_out", "email",
     "Standing desk from Northwind Stationery, £640.00 including delivery, ordered 8 Aug, "
     "invoice attached, PO-80190.",
     "Northwind Stationery", 640.00, "equipment", "PO-80190", "receipt", "2026-08-08"),
    ("c-019", "held_out", "email",
     "Laptop stand and a keyboard from Amazon, two orders on 16 Aug: £34.99 and £58.00. Both "
     "receipts attached.",
     "Amazon", 92.99, "equipment", None, "receipt", "2026-08-16"),
    ("c-020", "held_out", "app",
     "Working lunch, The Copper Kettle, 19 Aug 2026, £78.40, receipt attached.",
     "The Copper Kettle", 78.40, "meals", None, "receipt", "2026-08-19"),
    ("c-021", "dev", "scanned",
     "BRIGHTLINE RAIL   14 FEB 2026   LONDON-EDINBURGH   STD RETURN   158.00   E-TICKET",
     "Brightline Rail", 158.00, "travel", None, "receipt", "2026-02-14"),
    ("c-022", "held_out", "email",
     "Renewed our Kestrel Software team plan on 17 Aug, £96.00 for the month, receipt attached, "
     "no PO raised.",
     "Kestrel Software", 96.00, "software", None, "receipt", "2026-08-17"),
    ("c-023", "held_out", "app",
     "Stock photos, Unsplash+, £39.00, 12 Aug 2026, receipt attached.",
     "Unsplash", 39.00, "other", None, "receipt", "2026-08-12"),
    ("c-024", "held_out", "email",
     "Taxi home after the late deploy on 14 Aug, Meridian Cabs, £22.00. Forgot to get a receipt.",
     "Meridian Cabs", 22.00, "travel", None, "none", "2026-08-14"),
    ("c-025", "held_out", "scanned",
     "CLIENT DINNER   OSTERIA VERDE   03/08/2026\nFOOD 96.00   WINE 38.00   SERVICE 13.40\n"
     "TOTAL 147.40   RECEIPT",
     "Osteria Verde", 147.40, "meals", None, "receipt", "2026-08-03"),
    ("c-026", "dev", "app",
     "Adobe Acrobat licence, £15.17, 11 Aug 2026, receipt attached, no PO.",
     "Adobe", 15.17, "software", None, "receipt", "2026-08-11"),
    ("c-027", "held_out", "email",
     "Mileage for the Bristol site visit on 5 Aug, 142 miles at 45p = £63.90. Mileage log attached.",
     None, 63.90, "travel", None, "receipt", "2026-08-05"),
    ("c-028", "held_out", "scanned",
     "NORTHWIND STATIONERY   17-MAR-2026\nWHITEBOARD   89.00\nMARKERS   12.40\nTOTAL   101.40\nPO-77102",
     "Northwind Stationery", 101.40, "equipment", "PO-77102", "receipt", "2026-03-17"),
    ("c-029", "held_out", "app",
     "Coffee with a candidate, 20 Aug 2026, Grind, £7.60, receipt attached.",
     "Grind", 7.60, "meals", None, "receipt", "2026-08-20"),
    ("c-030", "held_out", "email",
     "Annual membership of the BCS, £120.00, paid 6 Aug, receipt attached. HR said this is claimable.",
     "BCS", 120.00, "other", None, "receipt", "2026-08-06"),
    ("c-031", "dev", "app",
     "Parking at NCP Reading, 13 Aug 2026, £18.00, receipt attached.",
     "NCP Reading", 18.00, "travel", None, "receipt", "2026-08-13"),
    ("c-032", "held_out", "email",
     "Webcam for the home office, a Logitech bought from Currys, £79.00, 10 Aug, receipt attached.",
     "Currys", 79.00, "equipment", None, "receipt", "2026-08-10"),
    ("c-033", "held_out", "scanned",
     "HARBOUR HOTELS BAR   09/08/2026\nDRINKS 62.00   SERVICE 6.20\nTOTAL 68.20",
     "Harbour Hotels", 68.20, "meals", None, "receipt", "2026-08-09"),
    ("c-034", "held_out", "app",
     "Kestrel Software add-on seats, £310.00, 15 Aug 2026, PO-80244, invoice attached.",
     "Kestrel Software", 310.00, "software", "PO-80244", "receipt", "2026-08-15"),
    ("c-035", "dev", "email",
     "Replacement office plant, £28.00 from a market stall on 19 Aug. Paid cash, no receipt.",
     None, 28.00, "other", None, "none", "2026-08-19"),
    ("c-036", "held_out", "email",
     "Train to the Cardiff client on 2 May 2026, Brightline Rail, £84.00, e-ticket attached. "
     "Sorry this is late.",
     "Brightline Rail", 84.00, "travel", None, "receipt", "2026-05-02"),
]


def policy_decision(total: float, category: str, po: str | None, proof: str,
                    expense_date: str) -> str:
    """What the policy gives, in the order the policy states it."""
    age = (date.fromisoformat(SUBMITTED_ON) - date.fromisoformat(expense_date)).days
    if proof != "receipt" and total > RECEIPT_REQUIRED_OVER:
        return "reject"
    if age > MAX_AGE_DAYS:
        return "reject"
    if total > LIMITS[category]:
        return "escalate"
    if category in PO_REQUIRED and po is None:
        return "escalate"
    return "approve"


def approved_supplier(vendor: str | None) -> bool:
    return vendor is not None and any(
        canonical_vendor(vendor) == canonical_vendor(name) for name in APPROVED_SUPPLIERS
    )


def build() -> ExampleSet:
    examples = []
    for (id_, split, source, text, vendor, total, category, po, proof, expense_date) in CLAIMS:
        decided = policy_decision(total, category, po, proof, expense_date)
        final = decided
        if decided == "escalate":
            final = "approve" if approved_supplier(vendor) else None
        extract_label = {
            "vendor": vendor if vendor is not None else Unknown(reason="the claim names nobody"),
            "total": total,
            "category": category,
            "po_number": po if po is not None else Unknown(reason="no PO number is stated"),
            "receipt": proof,
            "expense_date": expense_date,
            "submitted_on": SUBMITTED_ON,
        }
        if final is None:
            expected = Unknown(reason="finance cannot settle it unattended, so it is parked")
        else:
            expected = Criteria([
                Criterion(id="decision", text=f"the decision is {final}", required=True, weight=2),
                Criterion(id="vendor", text=f"the vendor is {vendor}") if vendor is not None
                else Criterion(id="vendor", text="no vendor is named", expects_absence=True),
                Criterion(id="total", text=f"the total is £{total:.2f}"),
                Criterion(id="category", text=f"the category is {category}"),
                Criterion(id="po_number", text=f"the PO number is {po}") if po is not None
                else Criterion(id="po_number", text="no PO number is stated", expects_absence=True),
            ])
        examples.append(Example(
            id=id_,
            inputs={"claim": text, "submitted_on": SUBMITTED_ON},
            expected=expected,
            split=split,
            source=source,
            expected_by_node={
                "intake": {"claim": text, "submitted_on": SUBMITTED_ON},
                "extract": extract_label,
                "decide": decided,
            },
            metadata={"category": category},
        ))
    return ExampleSet(examples)


if __name__ == "__main__":
    out = build().to_jsonl(Path("evals") / "examples.jsonl")
    print(out)
