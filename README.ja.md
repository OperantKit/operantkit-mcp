# operantkit-mcp

:gb: [English README](README.md)

operantkit-mcp は、強化スケジュールについて AI アシスタント（Claude Code、または Model Context Protocol（MCP）に対応した任意のクライアント）に尋ねたとき、アシスタントが [OperantKit](https://github.com/OperantKit) を使えるようにするサーバです。一度インストールしてアシスタントに登録すると、アシスタントは [contingency-dsl](https://github.com/OperantKit/contingency-dsl) で書いたスケジュールを検査し、シミュレーションし、方法セクション（Method 節）の段落との間で相互に変換し、OKL（OperantKit Log）形式のセッションログを要約・分析できるようになります。

- **スケジュールは検証済みのライブラリが実行します。** 回答のたびにアシスタントがその場で書くコードではありません。
- **数値は推測ではなく計算されます。** 件数・率・当てはめは、実際に走らせた模擬セッションか、あなたのログから求めます。
- **手元のマシンで動きます。** 標準入出力でやり取りするローカルのプロセスで、サーバが外部へ何かを送ることはありません。

Claude Code では、[claude-plugin](https://github.com/OperantKit/claude-plugin) を入れると、このサーバと、いつ使うかを Claude に教える skill がまとめて入ります。

## インストール

Python 3.11 以上が必要です。OperantKit の各パッケージはまだ PyPI に登録されていないので、GitHub から依存の解決なしで入れ、その後で必要な外部ライブラリ 4 つを入れます:

```bash
G=git+https://github.com/OperantKit
pip install --no-deps $G/contingency-dsl-py $G/contingency-py $G/contingency-dsl2procedure \
  $G/contingency-procedure2dsl $G/experiment-core $G/session-runner $G/session-recorder \
  $G/experiment-io $G/session-analyzer $G/operantkit-mcp
pip install "mcp>=2,<3" numpy scipy matplotlib
```

これで環境に `operantkit-mcp` コマンドが入ります。`pip check` は OperantKit の開発版どうしのバージョンの食い違いを報告しますが、サーバの動作には影響しません。

## アシスタントへの登録

Claude Code の場合:

```bash
claude mcp add --transport stdio operantkit -- operantkit-mcp
claude mcp list
# operantkit: operantkit-mcp  - ✔ Connected
```

Claude Code の起動時に有効になっていない仮想環境に入れた場合は、`-- /path/to/.venv/bin/operantkit-mcp` のようにフルパスを指定してください。stdio のサーバを起動できる他の MCP クライアントでも、同じコマンド（`operantkit-mcp` または `python -m operantkit_mcp`）を使います。

## 例

「切替遅延 2 秒の並立 VI 30 秒 VI 60 秒スケジュールを書いて、30 分シミュレーションして、Procedure の段落をください」のような依頼に対して、アシスタントは次のような呼び出しをします。結果は、これらの呼び出しを MCP クライアントから実際に行ったときにサーバが返したものです。

| 呼び出し | 結果 |
|---|---|
| `check_dsl("Conc(VI 30s, VI 60s, COD=2s)")` | `ok: true`、正規形 `Conc(VI30s, VI60s, COD=2s)` |
| `check_dsl("FR 0")` | `ok: false`、`ATOMIC_NONPOSITIVE_VALUE: FR must have a positive value (got 0.0); use EXT for extinction` |
| `dsl_to_method("Conc(VI30s, VI60s, COD=2s)")` | 「Responses were reinforced under a concurrent VI 30-s VI 60-s schedule. A 2-s changeover delay was in effect.」と、参考文献として Fleshler と Hoffman (1962)、Herrnstein (1961) |
| `simulate("Conc(VI30s, VI60s, COD=2s)", exit_time=1800, output_path="conc.okl")` | セッション時間 1,800 秒。2 つのオペランダムで反応 1,759 回と 1,759 回、強化子 31 回と 21 回。ログを `conc.okl` に書き出し |
| `analyze_okl("conc.okl", analyses=["matching"])` | 強化の相対頻度 0.596、反応の相対頻度 0.500、感度 0.0 |

感度が 0 になるのは想定どおりです。模擬被験体は、強化にかかわらず両方のオペランダムで同じ一定の率で反応します（「制限」を参照）。このシミュレーションが示すのは、プログラムが各側に何回強化子を提示したか（VI 30 秒側 31 回、VI 60 秒側 21 回）であり、動物が反応をどう配分するかについては何も言いません。

## 道具

| 道具 | 入力 | 出力 |
|---|---|---|
| `check_dsl` | `source` | `ok`、`canonical`（正規化した式）、`ast`、`warnings`、`error`（`type`、`message`）。エラーは例外ではなくデータとして返る |
| `simulate` | `source`、`exit_reinforcers` / `exit_time`（秒）のどちらか一方、`virtual_rate_hz`（1.0）、`seed`（0）、`reinforcer_duration`（0.5）、`output_path` | `session_seconds`、イベント種ごとの `counts`、`responses_per_operandum`、`reinforcers_per_operandum`、毎分の反応率と強化率、`okl_path` |
| `dsl_to_method` | `source`、`style`（`jeab` 英語 / `jaba` 日本語） | `subjects`、`apparatus`、`procedure`、`references`、`markdown` |
| `method_to_dsl` | `text`（方法セクションの文章） | `dsl`、`schedules`（`confidence` と `source_text` 付き）、`params`、`unrecognized_fragments` |
| `summarize_okl` | `path`（OKL ログ） | `session_name`、`dsl`（ヘッダから）、`clock_type`、`session_seconds`、イベント種ごとの `counts`、`operanda`（オペランダムごとの反応数と強化子数）、`phase_markers` |
| `analyze_okl` | `path`、`analyses`（`prps` / `irt` / `bouts` / `matching` の任意の組み合わせ。既定はすべて）、`png_path` | `prps` と `prp_values`、`irt`、`bouts`、`matching`、`png_path`（累積記録）、`notes` |

`jeab` は *Journal of the Experimental Analysis of Behavior*（JEAB）の方法セクションの書式に、`jaba` は日本行動分析学会（J-ABA）の書式の日本語に従います。`prps` は強化後休止（PRP）、`irt` は反応間時間（IRT）、`bouts` は反応間時間の 2 成分による反応バウト分析です。

## 制限

- **模擬被験体は学習しません。** `simulate` は各オペランダムに `virtual_rate_hz` の独立した Poisson 反応源を付けます。強化によってこれは変わりません。シミュレーションは、スケジュールが何を提示するかを確かめるために使い、行動の予測には使わないでください。
- **時刻は模擬時間です。** 反応と反応の間は時計が 10 ミリ秒刻みで進むので、固定時間・変動時間・DRO（他行動分化強化）・限定保持は、被験体が反応しなくても働きます。セッション時間は壁時計の時刻ではありません。
- **VI・VR・VT の値**は Fleshler と Hoffman (1962) の数列に従います。値を固定するには式に `@algorithm(seed=N)` を書きます。`seed` が固定するのは反応源だけです。
- **`method_to_dsl` は規則ベースです。** 言語モデルは呼びません。`unrecognized_fragments` を読み、取りこぼした部分を補ってください。
- **`analyze_okl` のマッチングは 1 条件です。** オペランダム 0 と 1 の反応が必要で、log *b* を 0 に固定します。偏好（バイアス）をきちんと推定するには、複数の条件を [session-analyzer](https://github.com/OperantKit/session-analyzer) で当てはめてください。反応間時間はオペランダムをまとめて扱います。計算できない分析は `null` を返し、理由を `notes` に入れます。
- **パスはサーバ側のマシン上のものです。** 相対パスの `output_path`・`path`・`png_path` はサーバの作業ディレクトリを基準に解決され、返るパスは絶対パスです。

## 開発

このリポジトリを clone し、上のインストールを済ませた後で:

```bash
pip install --no-deps -e .
pip install pytest pytest-cov
pytest
```

## 参考文献

Fleshler, M., & Hoffman, H. S. (1962). A progression for generating variable-interval schedules. *Journal of the Experimental Analysis of Behavior*, *5*(4), 529–530. https://doi.org/10.1901/jeab.1962.5-529

Herrnstein, R. J. (1961). Relative and absolute strength of response as a function of frequency of reinforcement. *Journal of the Experimental Analysis of Behavior*, *4*(3), 267–272. https://doi.org/10.1901/jeab.1961.4-267

## ライセンス

MIT。[LICENSE](LICENSE) を参照してください。
