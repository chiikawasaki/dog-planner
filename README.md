# NBIS--

仮想の犬（ペット）とユーザーの触れ合いを Gemini で処理する API サーバーと、その応答時間・トークン消費を計測して可視化するための実験スクリプト群です。

長時間の対話では履歴が膨らんで応答が遅くなるため、古い履歴を要約して圧縮する仕組みを入れています。「圧縮あり／なし」で応答時間がどう変わるかを 1000 試行ぶん計測し、グラフにするのが一連のスクリプトの目的です。

## セットアップ

### 1. 仮想環境の有効化

Python 3.13.5 を使用しています。

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

有効化されるとプロンプトの先頭に `(.venv)` が付きます。抜けるときは以下です。

```bash
deactivate
```

仮想環境を有効化せずに実行したい場合は、`python` の代わりに `.venv/bin/python` を直接指定しても構いません。

### 2. 仮想環境を新しく作り直す場合

`.venv/` は Git に含めていないので、クローンした直後は自分で作る必要があります。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn google-genai supabase python-dotenv pydantic pandas matplotlib requests
```

### 3. 環境変数の設定

API キーは `.env` から読み込みます。`.env.example` をコピーして値を埋めてください。

```bash
cp .env.example .env
```

| 変数名 | 内容 |
| --- | --- |
| `SUPABASE_URL` | Supabase プロジェクトの URL |
| `SUPABASE_KEY` | Supabase のシークレットキー |
| `GEMINI_API_KEY` | Gemini API のキー |

`.env` は `.gitignore` で除外しています。キーが書かれたファイルをコミットしないよう注意してください。

## API サーバー

### server-gemini.py

FastAPI + Gemini + Supabase で動くペットの行動生成 API です。ペットの状態（空腹度・エネルギー・親密度など）を Supabase から読み、Gemini に渡して次の行動や振動パターンを決めさせ、結果を書き戻します。

```bash
uvicorn server-gemini:app --reload --host 0.0.0.0 --port 8000
```

エンドポイントは 6 つあります。

| エンドポイント | 用途 |
| --- | --- |
| `POST /pet/init` | ペットを新規作成して `pet_id`（UUID）を発行する |
| `POST /pet/plan` | ペットの自律行動を生成する |
| `POST /pet/train` | 「おすわり」訓練の応答を生成する |
| `POST /pet/production` | 「おすわり」本番の応答を生成する |
| `POST /pet/vibration` | 撫で始めの振動パターンを生成する |
| `POST /pet/petting` | 撫で終わりのエネルギー・親密度を更新する |

`/pet/vibration` のレスポンスには処理時間の内訳（`db_select_time` / `gemini_time` / `compress_time` / `update_time` / `total_time`）とトークン使用量が含まれ、これが計測スクリプトの入力になります。

### history.py

履歴圧縮のロジックをまとめたモジュールです。単体では実行せず `server-gemini.py` から呼ばれます。

履歴が 100 件（`MAX_HISTORY`）を超えると、直近 50 件（`KEEP_RECENT`）を残して古い履歴を Gemini に 500 文字程度へ要約させ、以降はその要約を文脈として使います。これによりプロンプトが際限なく伸びるのを防いでいます。

## 計測スクリプト

### vibration_times_to_csv.py

サーバーに対して「振動 → 5 秒待つ → 撫で終了」を 1000 回繰り返し、応答時間とトークン数を CSV に記録します。**実行前にサーバーを起動しておく必要があります。**

```bash
python vibration_times_to_csv.py
```

- 出力: `petting_test_compressed3.csv`（計測結果）、`error_log3.csv`（エラー記録）
- 対象サーバー: `http://127.0.0.1:8000`（`BASE_URL` で変更可）
- 計測対象のペット: `PET_ID` に UUID を直接記述しています。別のペットで計測する場合は `/pet/init` で発行した UUID に書き換えてください。

エラーが返った試行はカウントせず、2 秒待って同じ試行をやり直します。1 行ごとに `flush()` しているので、途中で止めてもそこまでの結果は残ります。5 秒の待機を含むため 1000 試行には数時間かかります。

## 可視化・集計スクリプト

いずれも計測済みの CSV を読んでグラフや統計量を出力します。`plt.show()` でウィンドウが開くので、閉じるとスクリプトが終了します。

| スクリプト | 入力 | 出力 | 内容 |
| --- | --- | --- | --- |
| `csv_to_graph.py` | `petting_test2.csv` | `petting_test2.png`, `trial-responsetime-compressed3.png` | 応答時間の折れ線・散布図・50 試行移動平均。散布図には右軸で累積トークン数を重ねる |
| `AI_time.py` | `petting_test_compressed3.csv` | `ai_time_compressed3.png` | Gemini の処理時間（`gemini_time` + `compress_time`）の散布図 |
| `db_connect_time.py` | `petting_test_compressed3.csv` | `db_connect_time.png` | DB 処理時間（`db_select_time` + `update_time`）の散布図 |
| `boxplot.py` | `petting_test_compressed.csv` | `boxplot-compressed.png` | 試行 1-599 / 600-1000 / 全体で応答時間を比較する箱ひげ図 |
| `csv_to_energygraph.py` | `petting_test.csv` | `energy.png` | エネルギー値の推移（最初の 100 試行） |
| `analysis.py` | `petting_test_compressed3.csv` | `response-time-summary-compressed3.csv` | 上記と同じ 3 区分の基本統計量（件数・平均・標準偏差・四分位数）を CSV 出力 |

実行例です。

```bash
python csv_to_graph.py
```

`csv_to_graph.py` は 3 つのグラフをすべて `petting_test2.png` という同じ名前で保存するため、最後に描画されるトークン数の折れ線だけがファイルとして残ります。個別に保存したい場合は `savefig()` のファイル名を変更してください。

読み込む CSV のファイル名は各スクリプトの冒頭にベタ書きされています。別の計測結果を対象にするときはそこを書き換えてください。

## データファイル

| ファイル | 内容 |
| --- | --- |
| `petting_test.csv`, `petting_test2.csv` | 履歴圧縮を入れる前の計測結果 |
| `petting_test_compressed.csv` 〜 `_compressed3.csv` | 履歴圧縮を入れた後の計測結果 |
| `error_log.csv` 〜 `error_log3.csv` | 計測中に発生した HTTP エラーの記録 |
| `response-time-summary*.csv` | `analysis.py` が出力した統計量 |
| `*.png`, `*.pdf` | 生成済みのグラフ |

計測結果の CSV は列構成が世代ごとに異なります。`petting_test2.csv` は 10 列（trial, vibration_ms, petting_ms, vibration_pattern, energy, intimacy, 各トークン数）ですが、`petting_test_compressed3.csv` は処理時間の内訳と圧縮フラグを加えた 20 列です。スクリプトによって入力ファイルが違うのはこのためです。
