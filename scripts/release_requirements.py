"""Render the auditable 3.5 requirement ledger; status is never inferred from code."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs" / "releases" / "3.5"


def render():
    rows = json.loads((DIRECTORY / "requirements.json").read_text(encoding="utf-8"))
    assert len({r["id"] for r in rows}) == len(rows)
    assert {r["source"] for r in rows} == set(range(1, 56))
    phases = ("implemented", "unit_tested", "integration_tested", "live_tested", "visually_reviewed", "user_approved")
    output = ["# OLIVE 3.5 individual requirement ledger", "",
        "Authority: the user's fresh 55-section master brief. No older Google-dependent scope applies.",
        "Stable IDs are append-only within their source section. `requirements.json` is the editable source;",
        "run `scripts/release_requirements.py` to regenerate this view. No scope downgrade is agreed.", "",
        "I = implemented, U = unit tested, X = integration tested, L = live tested, V = visually reviewed",
        "by the assistant, A = explicitly user approved. A dash is not evidence of completion. Tests and",
        "approval are separate states. Conditional items retain the condition from the master brief.",
        "Controls and prohibitions need an audit even when no new feature code is necessary.", "",
        f"**{len(rows)} tracked obligations** across all 55 source sections; no domain is accepted merely because its page opens.", ""]
    for section in range(1, 56):
        output += [f"## Source section {section}", "",
            "| ID | Requirement | Class / milestone | Implementation | Acceptance | I/U/X/L/V/A | Status / evidence | Limitation |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            if r["source"] != section:
                continue
            values = [r["id"], r["description"], r["classification"] + " / " + r["milestone"],
                r["implementation"], r["acceptance"], "/".join("yes" if r[p] else "-" for p in phases),
                r["status"] + "; " + r["evidence"], r["limitation"]]
            output.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in values) + " |")
        output.append("")
    (DIRECTORY / "REQUIREMENTS.md").write_text("\n".join(output), encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    print(f"Rendered {render()} requirements")
