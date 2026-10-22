"""Time-based schedules must advance between responses, not only at them."""

from __future__ import annotations

import pytest

from operantkit_mcp.simulate import simulate

pytestmark = pytest.mark.unit


class TestTimeAdvancesWithoutResponses:
    def test_dro_reinforces_pauses_longer_than_the_interval(self):
        # Mean IRT 20 s; about 60 % of IRTs exceed 10 s, so DRO 10-s pays.
        r = simulate("DRO 10s", exit_time=600, seed=0, virtual_rate_hz=0.05)
        assert r.reinforcers_per_operandum[0] >= 10

    def test_ft_delivers_on_time_regardless_of_responding(self):
        # FT times each interval from the previous delivery: about 600 / 5.
        r = simulate("FT 5s", exit_time=600, seed=0, virtual_rate_hz=0.05)
        assert 110 <= r.reinforcers_per_operandum[0] <= 120

    def test_ft_needs_no_responses(self):
        r = simulate("FT 5s", exit_reinforcers=10, seed=0, virtual_rate_hz=0.0001)
        assert r.responses_per_operandum == [0]
        assert r.reinforcers_per_operandum == [10]
        assert 50.0 <= r.session_seconds <= 51.0

    def test_session_ends_at_the_time_limit(self):
        r = simulate("DRO 10s", exit_time=600, seed=0, virtual_rate_hz=0.05)
        assert 600.0 <= r.session_seconds < 601.0
