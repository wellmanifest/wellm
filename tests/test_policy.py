from __future__ import annotations

from pathlib import Path

from wellmanifest.runtime import WellManifestRuntime

ROOT = Path(__file__).resolve().parents[1]


def test_policy_dialect_parses_example_rules() -> None:
    runtime = WellManifestRuntime()
    source = (ROOT / "examples" / "policy" / "CONTRIBUTING.policy").read_text()
    document = runtime.parse(source, dialect="policy")
    ids = [rule["id"] for rule in document.ir["rules"]]
    assert ids == ["C-CONTEXT-001", "C-CONTEXT-002"]
    assert document.ir["rules"][0]["actions"][0]["verb"] == "SET"
    assert document.ir["schema"] == "wellmanifest.policy/ir/v1"
    assert document.ir["dialect"] == "wellmanifest.policy/v1"
    assert document.ir["rules"][0]["condition"]["operator"] == "="
    action = document.ir["rules"][0]["actions"][0]
    assert action["kind"] == "action"
    assert action["opcode"] == "SET"
    assert action["payload"]["node"] == "binary"
    assert document.ir["rules"][0]["assertionNodes"][0]["node"] == "symbol"
    assert "BLOCKED" in document.ir["states"]


def test_original_contributing_markdown_is_importable_as_policy_ir() -> None:
    runtime = WellManifestRuntime()
    source = (ROOT / "tests" / "fixtures" / "governance" / "CONTRIBUTING.md").read_text()
    document = runtime.parse(source, dialect="policy")
    assert len(document.ir["rules"]) >= 40
    assert any(rule["id"] == "C-VALIDATION-006" for rule in document.ir["rules"])
    assert any(item["from"] == "START" and item["to"] == "ANALYSIS" for item in document.ir["transitions"])


def test_policy_actions_guards_and_next_targets_are_typed() -> None:
    source = """DOCUMENT TEST
VERSION 1
MODE STRICT
RULE C-TYPED-001
WHEN REQUESTED AND COUNT >= 2
DO VALIDATE INPUT WHEN SCHEMA_AVAILABLE
FORBID EXECUTE_UNAPPROVED_CHANGE
ASSERT RESULT = TRUE
NEXT VALIDATION WHEN COMPLETE OR PLAN
"""
    document = WellManifestRuntime().parse(source, dialect="policy")
    rule = document.ir["rules"][0]
    assert rule["condition"]["operator"] == "AND"
    assert rule["actions"][0]["guard"]["node"] == "symbol"
    assert rule["forbids"][0]["opcode"] == "EXECUTE_UNAPPROVED_CHANGE"
    assert rule["forbids"][0]["payload"] is None
    assert rule["assertionNodes"][0]["operator"] == "="
    assert rule["nextTargets"] == [
        {"target": "VALIDATION", "condition": {"node": "symbol", "name": "COMPLETE"}},
        {"target": "PLAN", "condition": None},
    ]
