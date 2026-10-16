"""Fixed input/output tests for each tool function."""

from __future__ import annotations

import pytest

from operantkit_mcp.dsl_tools import check_dsl, dsl_to_method, method_to_dsl
from operantkit_mcp.simulate import simulate

pytestmark = pytest.mark.unit

CONC = "Conc(VI30s, VI60s, COD=2s)"
CONC_PROCEDURE = (
    "Responses were reinforced under a concurrent VI 30-s VI 60-s schedule. "
    "A 2-s changeover delay was in effect."
)


class TestCheckDsl:
    def test_normalizes_spacing(self):
        r = check_dsl("FR 5")
        assert r.ok is True
        assert r.canonical == "FR5"
        assert r.ast["schedule"] == {"type": "Atomic", "dist": "F", "domain": "R", "value": 5.0}
        assert r.error is None

    def test_compound_round_trips(self):
        assert check_dsl(CONC).canonical == CONC

    def test_parse_error_is_data_not_exception(self):
        r = check_dsl("FR5 FR")
        assert r.ok is False
        assert r.canonical is None
        assert r.error.type == "ParseError"
        assert "line 1, col 5" in r.error.message


class TestSimulate:
    def test_fr_exits_after_requested_reinforcers(self):
        r = simulate("FR3", exit_reinforcers=4, seed=0)
        assert r.reinforcers_per_operandum == [4]
        assert r.responses_per_operandum == [12]
        assert r.counts["response"] == 12

    def test_same_seed_gives_identical_result(self):
        a = simulate("FI30s", exit_reinforcers=5, seed=0)
        b = simulate("FI30s", exit_reinforcers=5, seed=0)
        assert a == b
        assert a.reinforcers_per_operandum == [5]
        assert a.session_seconds >= 150.0

    def test_concurrent_gets_one_operandum_per_component(self):
        r = simulate("Conc(VI30s, VI60s)", exit_time=300.0, seed=1)
        assert len(r.responses_per_operandum) == 2
        assert all(n > 0 for n in r.responses_per_operandum)

    def test_writes_okl_when_path_given(self, tmp_path):
        out = tmp_path / "fr3.txt"
        r = simulate("FR3", exit_reinforcers=2, output_path=str(out))
        assert r.okl_path == str(out.resolve())
        assert out.read_text().strip()

    @pytest.mark.parametrize(
        "kwargs",
        [{}, {"exit_reinforcers": 1, "exit_time": 1.0}, {"exit_reinforcers": 0}, {"exit_time": -1.0}],
    )
    def test_rejects_bad_exit(self, kwargs):
        with pytest.raises(ValueError):
            simulate("FR3", **kwargs)

    def test_rejects_bad_dsl(self):
        with pytest.raises(ValueError, match="ParseError"):
            simulate("FR5 FR", exit_reinforcers=1)


class TestDslToMethod:
    def test_jeab_procedure_text(self):
        m = dsl_to_method(CONC)
        assert m.procedure == CONC_PROCEDURE
        assert "fleshler_hoffman_1962" in [r.key for r in m.references]
        assert m.markdown.startswith("## Method")

    def test_jaba_style_is_japanese(self):
        m = dsl_to_method("FR5", style="jaba")
        assert any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in m.procedure)

    def test_bad_dsl_raises_value_error(self):
        with pytest.raises(ValueError):
            dsl_to_method("FR5 FR")


class TestMethodToDsl:
    def test_round_trip_from_dsl_to_method(self):
        r = method_to_dsl(CONC_PROCEDURE)
        assert r.dsl == "COD = 2s\nConc(VI30s, VI60s)"
        assert r.schedules[0].dsl == "Conc(VI30s, VI60s)"
        assert r.schedules[0].source_text == "concurrent VI 30-s VI 60-s schedule"
        assert [(p.name, p.value, p.unit) for p in r.params] == [("COD", 2.0, "s")]
        assert check_dsl(r.dsl).ok

    def test_no_schedule_gives_none(self):
        r = method_to_dsl("Subjects were four pigeons.")
        assert r.dsl is None
        assert r.schedules == []
