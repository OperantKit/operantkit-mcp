# operantkit-mcp

:gb: [English README](README.md)

AI アシスタントが FR / VI の生成器を自作せず、OperantKit で強化スケジュールを設計するための MCP サーバ（stdio）です。スケジュールは [contingency-dsl](https://github.com/OperantKit/contingency-dsl) の式 1 つで書きます。サーバはその式を検査し、仮想被験体でシミュレーションし、式と Method 節を相互に変換します。

## 道具

| 道具 | 入力 | 出力 |
|---|---|---|
| `check_dsl` | `source` | `ok`、`canonical`（正規化した DSL）、`ast`、`warnings`、`error`（`type`, `message`）— エラーは例外でなくデータで返す |
| `simulate` | `source`、`exit_reinforcers` / `exit_time`（秒）のどちらか 1 つ、`virtual_rate_hz`（1.0）、`seed`（0）、`reinforcer_duration`（0.5）、`output_path` | `session_seconds`、事象の種類ごとの `counts`、`responses_per_operandum`、`reinforcers_per_operandum`、毎分の反応率と強化率、`okl_path` |
| `dsl_to_method` | `source`、`style`（`jeab` 英語 / `jaba` 日本語） | `subjects`、`apparatus`、`procedure`、`references`、`markdown` |
| `method_to_dsl` | `text`（Method 節の本文） | `dsl`、`schedules`（`confidence` と `source_text` 付き）、`params`、`unrecognized_fragments` |

どの道具も出力スキーマ付きの構造化データを返します。

- `simulate` は仮想時計で走るため、数分のセッションが 1 秒未満で終わります。同じ `seed` なら結果は同じです。並立スケジュールでは成分ごとに独立した Poisson 反応者を置きます。VI / VR / VT の値は DSL の `@algorithm(seed=N)` で固定します。
- `method_to_dsl` は規則ベースの抽出だけを使います。LLM は呼びません。`unrecognized_fragments` は呼ぶ側が読んで補ってください。

## 導入

```bash
pip install operantkit-mcp
```

Python 3.11 以上。

## Claude Code で使う

```bash
claude mcp add --transport stdio operantkit -- operantkit-mcp
claude mcp list    # operantkit: operantkit-mcp - ✔ Connected
```

stdio サーバを起動できる MCP クライアントなら同じ手順で使えます。コマンドは `operantkit-mcp`（または `python -m operantkit_mcp`）です。

## 例

```text
check_dsl("Conc(VI 30s, VI 60s, COD=2s)")
  → canonical "Conc(VI30s, VI60s, COD=2s)"
dsl_to_method("Conc(VI30s, VI60s, COD=2s)")
  → procedure "Responses were reinforced under a concurrent VI 30-s VI 60-s schedule.
               A 2-s changeover delay was in effect."
simulate("FI30s", exit_reinforcers=5, seed=0)
  → reinforcers_per_operandum [5], session_seconds ≥ 150
```

## 依存関係

`mcp`（2.x）、`contingency-dsl-py`、`contingency-py`、`contingency-dsl2procedure`、`contingency-procedure2dsl`、`experiment-core`、`session-runner`、`session-recorder`、`experiment-io`。

## 開発

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest
```

## ライセンス

MIT
