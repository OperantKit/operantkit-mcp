"""The README examples run as written and give the numbers the README shows."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from operantkit_mcp.dsl_tools import check_dsl
from operantkit_mcp.okl_tools import analyze_okl
from operantkit_mcp.simulate import simulate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
READMES = [ROOT / "README.md", ROOT / "README.ja.md"]

SOURCE = 'Conc(VI30s, VI60s, COD=2s) @algorithm("fleshler-hoffman", seed=1)'
SIMULATE_CALL = f"simulate('{SOURCE}', exit_time=1800, output_path=\"conc.okl\")"
ANALYZE_CALL = 'analyze_okl("conc.okl", analyses=["matching"])'

EN_SIMULATE = re.compile(
    r"responses ([\d,]+) and ([\d,]+), reinforcers (\d+) and (\d+) on the two operanda"
)
JA_SIMULATE = re.compile(r"反応 ([\d,]+) 回と ([\d,]+) 回、強化子 (\d+) 回と (\d+) 回")
EN_MATCHING = re.compile(
    r"relative reinforcement ([\d.]+), relative responses ([\d.]+), sensitivity ([\d.]+)"
)
JA_MATCHING = re.compile(r"強化の相対頻度 ([\d.]+)、反応の相対頻度 ([\d.]+)、感度 ([\d.]+)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ints(match: re.Match[str]) -> list[int]:
    return [int(g.replace(",", "")) for g in match.groups()]


def _run(tmp_path: Path, name: str):
    out = tmp_path / name
    result = simulate(SOURCE, exit_time=1800, output_path=str(out))
    return result, analyze_okl(str(out), analyses=["matching"]).matching, out.read_bytes()


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("readme")
    return _run(tmp, "first.okl"), _run(tmp, "second.okl")


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_example_calls_appear_verbatim(readme):
    text = _text(readme)
    assert f"`{SIMULATE_CALL}`" in text
    assert f"`{ANALYZE_CALL}`" in text


def test_example_is_reproducible(measured):
    (first, first_match, first_log), (second, second_match, second_log) = measured
    assert first.ok and second.ok
    assert first.responses_per_operandum == second.responses_per_operandum
    assert first.reinforcers_per_operandum == second.reinforcers_per_operandum
    assert first_match == second_match
    assert first_log == second_log


@pytest.mark.parametrize(
    ("readme", "sim_pattern", "match_pattern"),
    [(READMES[0], EN_SIMULATE, EN_MATCHING), (READMES[1], JA_SIMULATE, JA_MATCHING)],
    ids=["README.md", "README.ja.md"],
)
def test_example_numbers_match_readme(measured, readme, sim_pattern, match_pattern):
    (result, matching, _), _ = measured
    text = _text(readme)
    sim = sim_pattern.search(text)
    assert sim is not None, "simulate row not found"
    assert _ints(sim) == result.responses_per_operandum + result.reinforcers_per_operandum
    found = match_pattern.search(text)
    assert found is not None, "analyze_okl row not found"
    shown = [float(g) for g in found.groups()]
    actual = [matching.reinforcer_proportion, matching.response_proportion, matching.sensitivity]
    assert shown == [round(v, 3) for v in actual]


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_algorithm_annotation_in_limitations_is_accepted(readme, tmp_path):
    snippets = [
        s
        for s in re.findall(r"`([^`]*@algorithm\([^`]*\))`", _text(readme))
        if "simulate(" not in s
    ]
    assert snippets, "no @algorithm example in README"
    for snippet in snippets:
        source = snippet if snippet.lstrip().startswith(("Conc", "VI", "FR")) else f"VI30s {snippet}"
        checked = check_dsl(source)
        assert checked.ok, (source, checked.error)
        assert simulate(source, exit_reinforcers=2).ok
