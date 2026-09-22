import json
from pathlib import Path

from pa_scanner.config import CFG
from pa_scanner.strategy_board import assess_row, assess_rule


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tradingview/parity_fixture.json").read_text())
PINE = (ROOT / FIXTURE["pine_file"]).read_text()


def test_pa_confirm_risk_template_parity():
    standard = FIXTURE["risk_templates"]["standard"]
    assert standard == {
        "stop_atr": CFG.exit_stop_atr,
        "target_atr": CFG.exit_target_atr,
        "time_bars": CFG.exit_time_bars,
    }
    assert FIXTURE["risk_templates"]["S4_US"]["time_bars"] == CFG.s4_time_bars
    assert FIXTURE["risk_templates"]["India_S2_long"] == {
        "stop_atr": CFG.in_pos_stop_atr,
        "target_atr": CFG.in_pos_tgt_atr,
        "time_bars": CFG.in_pos_time_bars,
    }


def test_pa_confirm_evidence_parity():
    assert assess_rule("S3", "us", False)[0] == "PREFERRED"
    assert assess_rule("S4", "us", False)[0] == "EXPERIMENTAL"
    assert assess_rule("S4", "asx", False)[0] == "AVOID"
    assert assess_rule("S4", "in", False)[0] == "CONTEXT"
    assert assess_row({"signal": "S1", "side": "short"}, "in", False)[0] == "PREFERRED"
    assert assess_row({"signal": "S2", "side": "long"}, "in", False)[0] == "EXPERIMENTAL"


def test_pa_confirm_columns_and_compatibility_header():
    assert FIXTURE["source_commit"] in PINE
    assert "//@version=6" in PINE
    for token in (
        "S3_Neutral",
        "SignalConfirmed",
        "EvidenceTier",
        "EntryAuthorised",
        "ExitOrReduce",
        "Active Stop",
        "Active Target",
    ):
        assert token in PINE
