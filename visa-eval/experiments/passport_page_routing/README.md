# Passport page routing experiment

方式②「最初にPDFの全ページを分類し、後続の抽出scopeへ必要ページだけをroutingする」が成立するかを、本体に接続せず評価する実験です。

## 安全上の境界

- 入力は `visa-eval/test_cases_from_raw/` のrestricted fixtureをローカルで読むだけです。
- ファイル名やmanifestのdocument IDはAPIへ送らず、`doc_001` のような実験内IDへ置き換えます。
- プロンプトとJSON Schemaは、氏名・生年月日・旅券番号・住所・原文引用を出力しないよう制限しています。
- APIの生レスポンスは `runs/` にのみ保存し、同ディレクトリはgit管理外です。
- `results/` に置く集計は、匿名case ID、ページ番号、分類、confidence、token、latencyだけです。
- 本体コード、Cloud Run、Firestore、GCSは変更しません。

## 比較する設定

`configs.json` では次を比較します。

- `gemini-3.6-flash`: thinking `MINIMAL / LOW / MEDIUM`、media resolution `LOW / MEDIUM / HIGH`
- `gemini-3.5-flash-lite`: thinking `MINIMAL / LOW`、media resolution `MEDIUM / HIGH`
- `gemini-3-flash-preview`: 現行互換の `temperature=0` とtemperature省略
- prompt: 短い指示と、旅券ページを早期除外しないconservative指示
- すべてPDF direct input + structured output(JSON Schema)

Gemini 3.6/3.5以降では `temperature`、`top_p`、`top_k` が非推奨なので、3.6/3.5の設定では送信しません。現行3 Flash Previewだけ比較用に明示ゼロと省略を用意しています。

## 実行

backendと同じvenvを使います。APIキーは `visa-app/backend/.env` の `GOOGLE_API_KEY` を読みますが、値は表示しません。

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/experiments/passport_page_routing/run_experiment.py \
  --check-models

visa-app/backend/.venv/bin/python \
  visa-eval/experiments/passport_page_routing/run_experiment.py \
  <fixture_dir_1> <fixture_dir_2> \
  --ground-truth-document-role submitted_application_bundle \
  --ground-truth-page 1 \
  --repetitions 3 \
  --summary-output \
  visa-eval/experiments/passport_page_routing/results/YYYY-MM-DD_summary.json
```

今回のground truthは、文字が読めない大きさまで縮小したcontact sheetを人が目視し、旅券の身分事項ページのレイアウトだけを確認して作ります。集計にはdocument ordinalとpage番号だけを残し、ファイル名・元document ID・本文は残しません。
匿名ラベルは `ground_truth.json` に保存しています。現行2 fixtureはいずれも、入力PDFの3番目・1ページ目が旅券身分事項ページです。

特定設定だけを再実行する場合は `--config-id <id>` を複数指定できます。生結果の保存先を変える場合は `--output-dir` を使います。

## テスト

```bash
visa-app/backend/.venv/bin/python -m unittest discover \
  -s visa-eval/experiments/passport_page_routing/tests \
  -p 'test_*.py'
```

テストは合成dictだけを使い、APIを呼びません。

## 判定基準

- API成功率
- 全物理ページのcoverageが100%か
- 既存identity source refの旅券候補を含むか
- 不要な追加旅券候補数
- token数とlatency
- 公式Standard料金からの推定USD
- thinking/media/prompt/temperature差による結果の安定性

実運用へ接続する場合も、classifierの陰性だけでページを捨てません。低confidence、候補なし、複数候補、coverage不足は後続identity scopeまたは人手レビューへ残す前提です。

## 料金前提

2026-08-09取得のGoogle公式Standard料金を使います。

- `gemini-3.6-flash`: input $1.50/M、output（thinking含む）$7.50/M
- `gemini-3.5-flash-lite`: input $0.30/M、output（thinking含む）$2.50/M
- `gemini-3-flash-preview`: input $0.50/M、output（thinking含む）$3.00/M

1 runの推定額は `(prompt_tokens × input単価 + (candidate_tokens + thought_tokens) × output単価) / 1,000,000` です。税、通信、保存、後続の本体抽出callは含みません。
