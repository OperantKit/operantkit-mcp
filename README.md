# operantkit-mcp

:jp: [日本語版 README](README.ja.md)

operantkit-mcp lets an AI assistant (Claude Code, or any client that speaks the Model Context Protocol, MCP) use [OperantKit](https://github.com/OperantKit) when you ask it about a reinforcement schedule. Install it once and register it with your assistant; the assistant can then check a schedule written in [contingency-dsl](https://github.com/OperantKit/contingency-dsl), simulate it, turn it into a Method-section paragraph and back, and summarize or analyze an OKL (OperantKit Log) session log.

- **The schedule comes from a tested library,** not from code the assistant improvises for each answer.
- **Numbers are computed, not guessed:** counts, rates, and fits come from an actual simulated session or your log.
- **Runs on your machine** as a local process over standard input and output; nothing is sent elsewhere by the server.

For Claude Code, [claude-plugin](https://github.com/OperantKit/claude-plugin) installs this server together with a skill that tells Claude when to use it.

## Installation

Python 3.11 or newer. The OperantKit packages are not on PyPI yet, so install them from GitHub without dependency resolution, then add the four third-party libraries they need:

```bash
G=git+https://github.com/OperantKit
pip install --no-deps $G/contingency-dsl-py $G/contingency-py $G/contingency-dsl2procedure \
  $G/contingency-procedure2dsl $G/experiment-core $G/session-runner $G/session-recorder \
  $G/experiment-io $G/session-analyzer $G/operantkit-mcp
pip install "mcp>=2,<3" numpy scipy matplotlib
```

This puts the `operantkit-mcp` command in your environment. `pip check` reports version mismatches between the OperantKit development builds; they do not affect the server.

## Register it with your assistant

Claude Code:

```bash
claude mcp add --transport stdio operantkit -- operantkit-mcp
claude mcp list
# operantkit: operantkit-mcp  - ✔ Connected
```

If you installed into a virtual environment that is not active when Claude Code starts, give the full path instead, for example `-- /path/to/.venv/bin/operantkit-mcp`. Other MCP clients that launch stdio servers use the same command (`operantkit-mcp`, or `python -m operantkit_mcp`).

## Example

For a request such as *"Write a concurrent VI 30-s VI 60-s schedule with a 2-s changeover delay, simulate 30 minutes, and give me the Procedure paragraph,"* the assistant makes calls like the ones below. The results are what the server returned when these calls were made through an MCP client.

| Call | Result |
|---|---|
| `check_dsl("Conc(VI 30s, VI 60s, COD=2s)")` | `ok: true`, canonical form `Conc(VI30s, VI60s, COD=2s)` |
| `check_dsl("FR 0")` | `ok: false`, `ATOMIC_NONPOSITIVE_VALUE: FR must have a positive value (got 0.0); use EXT for extinction` |
| `dsl_to_method("Conc(VI30s, VI60s, COD=2s)")` | "Responses were reinforced under a concurrent VI 30-s VI 60-s schedule. A 2-s changeover delay was in effect." with Fleshler and Hoffman (1962) and Herrnstein (1961) as references |
| `simulate("Conc(VI30s, VI60s, COD=2s)", exit_time=1800, output_path="conc.okl")` | 1,800 s of session time; responses 1,759 and 1,759, reinforcers 31 and 21 on the two operanda; the log written to `conc.okl` |
| `analyze_okl("conc.okl", analyses=["matching"])` | relative reinforcement 0.596, relative responses 0.500, sensitivity 0.0 |

The sensitivity of 0 is expected: the simulated subject responds at the same constant rate on both operanda whatever the reinforcement (see Limitations). The simulation shows how many reinforcers the program delivered on each side (31 on VI 30 s, 21 on VI 60 s); it says nothing about how an animal would distribute its responses.

## Tools

| Tool | Input | Output |
|---|---|---|
| `check_dsl` | `source` | `ok`, `canonical` (normalized expression), `ast`, `warnings`, `error` (`type`, `message`); errors are returned as data |
| `simulate` | `source`, one of `exit_reinforcers` / `exit_time` (s), `virtual_rate_hz` (1.0), `seed` (0), `reinforcer_duration` (0.5), `output_path` | `session_seconds`, `counts` per event type, `responses_per_operandum`, `reinforcers_per_operandum`, response and reinforcement rates per minute, `okl_path` |
| `dsl_to_method` | `source`, `style` (`jeab` English / `jaba` Japanese) | `subjects`, `apparatus`, `procedure`, `references`, `markdown` |
| `method_to_dsl` | `text` (Method-section prose) | `dsl`, `schedules` (with `confidence` and `source_text`), `params`, `unrecognized_fragments` |
| `summarize_okl` | `path` (OKL log) | `session_name`, `dsl` (from the header), `clock_type`, `session_seconds`, `counts` per event type, `operanda` (responses and reinforcers per operandum), `phase_markers` |
| `analyze_okl` | `path`, `analyses` (any of `prps` / `irt` / `bouts` / `matching`; default all), `png_path` | `prps` and `prp_values`, `irt`, `bouts`, `matching`, `png_path` (cumulative record), `notes` |

`jeab` follows the Method-section style of the *Journal of the Experimental Analysis of Behavior* (JEAB); `jaba` writes Japanese in the style of the Japanese Association for Behavior Analysis (J-ABA). `prps` are post-reinforcement pauses, `irt` inter-response times, and `bouts` a two-component bout analysis of the inter-response times.

## Limitations

- **The simulated subject does not learn.** `simulate` gives each operandum an independent Poisson responder at `virtual_rate_hz`; reinforcement does not change it. Use simulation to check what the schedule delivers, not to predict behavior.
- **Simulated time.** Between responses the clock advances in 10-ms steps, so fixed-time, variable-time, DRO (differential reinforcement of other behavior), and limited-hold contingencies run even when the subject does not respond. Session times are not wall-clock times.
- **VI, VR, and VT values** follow the Fleshler and Hoffman (1962) progression. To fix them, put `@algorithm(seed=N)` in the expression; `seed` fixes only the responders.
- **`method_to_dsl` is rule-based.** No language model is called. Read `unrecognized_fragments` and fill in what it missed.
- **`analyze_okl` matching uses one condition.** It needs responses on operanda 0 and 1 and fixes log *b* at 0; fit several conditions with [session-analyzer](https://github.com/OperantKit/session-analyzer) for a real bias estimate. Inter-response times are pooled over operanda. An analysis that cannot be computed returns `null` with the reason in `notes`.
- **Paths are on the server's machine.** Relative `output_path`, `path`, and `png_path` are resolved against the server's working directory; the returned paths are absolute.

## Development

From a clone of this repository, after the installation above:

```bash
pip install --no-deps -e .
pip install pytest pytest-cov
pytest
```

## References

Fleshler, M., & Hoffman, H. S. (1962). A progression for generating variable-interval schedules. *Journal of the Experimental Analysis of Behavior*, *5*(4), 529–530. https://doi.org/10.1901/jeab.1962.5-529

Herrnstein, R. J. (1961). Relative and absolute strength of response as a function of frequency of reinforcement. *Journal of the Experimental Analysis of Behavior*, *4*(3), 267–272. https://doi.org/10.1901/jeab.1961.4-267

## License

MIT. See [LICENSE](LICENSE).
