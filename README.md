# operantkit-mcp

:jp: [日本語版 README](README.ja.md)

An MCP server (stdio) that lets an AI assistant design reinforcement schedules with OperantKit instead of hand-writing FR/VI generators. The schedule is written as one [contingency-dsl](https://github.com/OperantKit/contingency-dsl) expression; the server checks it, simulates it against virtual subjects, and translates between the expression and a Method section.

## Tools

| Tool | Input | Output |
|---|---|---|
| `check_dsl` | `source` | `ok`, `canonical` (normalized DSL), `ast`, `warnings`, `error` (`type`, `message`) — errors are returned as data |
| `simulate` | `source`, one of `exit_reinforcers` / `exit_time` (s), `virtual_rate_hz` (1.0), `seed` (0), `reinforcer_duration` (0.5), `output_path` | `session_seconds`, `counts` per event type, `responses_per_operandum`, `reinforcers_per_operandum`, response and reinforcement rates per minute, `okl_path` |
| `dsl_to_method` | `source`, `style` (`jeab` English / `jaba` Japanese) | `subjects`, `apparatus`, `procedure`, `references`, `markdown` |
| `method_to_dsl` | `text` (Method-section prose) | `dsl`, `schedules` (with `confidence` and `source_text`), `params`, `unrecognized_fragments` |

All tools return structured content with a published output schema.

- `simulate` runs on a virtual clock: a session of minutes finishes in well under a second. The same `seed` gives the same result. A concurrent schedule gets one independent Poisson responder per component. Seed VI/VR/VT values with `@algorithm(seed=N)` in the DSL.
- `method_to_dsl` uses the rule-based extractor only. No LLM is called; read `unrecognized_fragments` and fill the gaps yourself.

## Install

```bash
pip install operantkit-mcp
```

Python 3.11+.

## Use with Claude Code

```bash
claude mcp add --transport stdio operantkit -- operantkit-mcp
claude mcp list    # operantkit: operantkit-mcp - ✔ Connected
```

Any MCP client that launches stdio servers works the same way: the command is `operantkit-mcp` (or `python -m operantkit_mcp`).

## Example

```text
check_dsl("Conc(VI 30s, VI 60s, COD=2s)")
  → canonical "Conc(VI30s, VI60s, COD=2s)"
dsl_to_method("Conc(VI30s, VI60s, COD=2s)")
  → procedure "Responses were reinforced under a concurrent VI 30-s VI 60-s schedule.
               A 2-s changeover delay was in effect."
simulate("FI30s", exit_reinforcers=5, seed=0)
  → reinforcers_per_operandum [5], session_seconds ≥ 150
```

## Dependencies

`mcp` (2.x), `contingency-dsl-py`, `contingency-py`, `contingency-dsl2procedure`, `contingency-procedure2dsl`, `experiment-core`, `session-runner`, `session-recorder`, `experiment-io`.

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest
```

## License

MIT
