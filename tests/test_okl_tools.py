"""Fixed input/output tests for summarize_okl and analyze_okl.

The fixtures were written by ``operant run --schedule "FI30s"
--exit-reinforcers 5 --seed 0`` and ``operant run --schedule
"Conc(VI30s, VI60s)" --exit-reinforcers 20 --seed 0``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from operantkit_mcp.okl_tools import analyze_okl, summarize_okl
from operantkit_mcp.simulate import simulate

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
FI = str(FIXTURES / "fi30s.okl.txt")
CONC = str(FIXTURES / "conc_vi30s_vi60s.okl.txt")


class TestSummarizeOkl:
    def test_fi_header_and_counts(self):
        s = summarize_okl(FI)
        assert s.session_name == "fi30"
        assert s.dsl == "FI30s"
        assert s.clock_type == "ManualClock"
        assert s.session_seconds == pytest.approx(154.564, abs=1e-3)
        assert s.counts == {
            "reinforcer_end": 5,
            "reinforcer_start": 5,
            "response": 132,
            "state_change": 12,
        }
        assert [(o.operandum, o.responses, o.reinforcers) for o in s.operanda] == [(None, 132, 5)]
        assert s.phase_markers == []

    def test_concurrent_counts_per_operandum(self):
        s = summarize_okl(CONC)
        assert s.dsl == "Conc(VI30s, VI60s)"
        assert [(o.operandum, o.responses, o.reinforcers) for o in s.operanda] == [
            (0, 360, 14),
            (1, 378, 6),
        ]

    def test_phase_markers(self, tmp_path):
        text = Path(FI).read_text()
        head, body = text.split("# ---\n")
        lines = body.splitlines()
        lines.insert(1, "0.5\tphase_enter\tAcquisition\tctxA\t-\t-\t-")
        lines.append("200.0\tphase_exit\tAcquisition")
        path = tmp_path / "phases.txt"
        path.write_text(head + "# ---\n" + "\n".join(lines) + "\n")
        markers = summarize_okl(str(path)).phase_markers
        assert [(m.kind, m.timestamp, m.label) for m in markers] == [
            ("enter", 0.5, "Acquisition"),
            ("exit", 200.0, "Acquisition"),
        ]
        assert markers[0].context == {"name": "ctxA"}

    def test_reads_what_simulate_writes(self, tmp_path):
        out = tmp_path / "fr3.txt"
        simulate("FR3", exit_reinforcers=2, output_path=str(out))
        s = summarize_okl(str(out))
        assert s.dsl == "FR3"
        assert s.counts["response"] == 6

    def test_missing_file_is_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            summarize_okl(str(tmp_path / "nope.txt"))


class TestAnalyzeOkl:
    def test_fi_all_analyses(self):
        a = analyze_okl(FI)
        assert a.analyses == ["prps", "irt", "bouts", "matching"]
        assert a.irt.n == 131
        assert a.irt.mean == pytest.approx(1.16186, abs=1e-4)
        # The fifth reinforcer ends the session, so 4 PRPs.
        assert a.prps.n == 4
        assert a.prp_values == pytest.approx([1.13893, 1.09415, 3.06502, 2.36483], abs=1e-4)
        assert a.bouts.n_irts == 131
        assert a.bouts.converged is True
        assert a.matching is None
        assert a.notes == ["matching: needs responses on exactly operanda 0 and 1"]
        assert a.png_path is None

    def test_concurrent_matching(self):
        a = analyze_okl(CONC, analyses=["matching"])
        m = a.matching
        assert m.responses == [360, 378]
        assert m.reinforcers == [14, 6]
        assert m.reinforcer_proportion == pytest.approx(0.7)
        assert m.response_proportion == pytest.approx(360 / 738)
        assert m.sensitivity == pytest.approx(-0.021189 / 0.367977, abs=1e-4)
        assert m.bias == 1.0
        assert a.irt is None and a.prps is None and a.bouts is None

    def test_writes_cumulative_record_png(self, tmp_path):
        out = tmp_path / "plots" / "fi.png"
        a = analyze_okl(FI, analyses=[], png_path=str(out))
        assert a.png_path == str(out.resolve())
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_unknown_analysis_is_value_error(self):
        with pytest.raises(ValueError, match="unknown analyses"):
            analyze_okl(FI, analyses=["prps", "magic"])
