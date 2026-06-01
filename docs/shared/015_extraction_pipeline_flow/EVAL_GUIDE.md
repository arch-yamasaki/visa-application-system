# 抽出品質 eval ガイド

バックエンドのみで抽出品質を評価する方法。

> 現在のeval方針の正本は `../../../visa-app/docs/008_eval_workflow/README.md` です。この文書は将来の pytest eval 構想メモとして扱います。

## 概要

visa-eval の既存ゴールデンデータ（13申請人分）を使い、pytest で自動評価する。
Gemini API を実際に叩くため、1ケースあたり約1-2円のコストが発生する。

## 前提

- visa-eval/test_cases_from_raw/ にゴールデンデータが配置済み
  - Round 1: 8申請人（amit_tamang等）
  - Round 2: 5申請人（bandana_joshi等）
- バックエンド環境（.env に GOOGLE_API_KEY）が設定済み

## ディレクトリ構成

```
visa-app/backend/
  eval/
    __init__.py
    conftest.py              # テストケースローダー、抽出fixture
    metrics.py               # 品質メトリクス計算
    test_extraction_eval.py  # eval テスト本体
```

## 品質メトリクス

| メトリクス | 定義 | 目標 |
|---|---|---|
| 値あり証跡率 | 値があるフィールドのうち source_refs ありの割合 | ≥ 95% |
| bbox率 | PDF参照フィールドのうち bbox ありの割合 | ≥ 70% |
| 値充足率 | 全フィールドのうち値が空でないフィールドの割合 | ≥ 60% |
| ゴールデン一致率 | ゴールデンデータと一致したフィールドの割合 | ≥ 85% |

## 実行方法

```bash
cd visa-app/backend

# 全ケース実行（実API、コスト発生）
pytest eval/ -m eval -v

# 特定ケースのみ
pytest eval/ -m eval -k "amit_tamang" -v

# ユニットテスト（モック、コストなし）は通常通り
pytest tests/ -v
```

## 仕組み

1. `conftest.py` が visa-eval/test_cases_from_raw/ を走査してテストケースを発見
2. 各ケースの scenario.json + input/document_manifest.json からファイルを読み込み
3. 抽出エンジンを**関数呼び出し**で直接実行（HTTP API経由ではない、GCS/Firestore不要）
4. 結果の品質メトリクスを計算し、閾値でアサート
5. expected/case_data.golden.json がある場合はゴールデン比較も実施

## visa-eval との棲み分け

| | visa-eval | visa-app/backend/eval |
|---|---|---|
| 目的 | ゴールデン作成・管理、ブラインド評価 | 自動品質ゲート |
| 実行方式 | スクリプト + Codex | pytest |
| Gemini呼び出し | Codex経由 | 直接（extractors/） |
| CI連携 | なし | 可能（将来） |

## コスト見積もり

| 実行パターン | ケース数 | 推定コスト | 所要時間 |
|---|---|---|---|
| 1ケースのみ | 1 | ~2円 | ~30秒 |
| Round 1 全件 | 8 | ~16円 | ~4分 |
| 全件 | 13 | ~26円 | ~7分 |

## 実装ステップ（未実装、今後の作業）

1. eval/metrics.py — メトリクス計算ロジック
2. eval/conftest.py — テストケースローダー + 抽出fixture
3. main.py の抽出ロジックを純粋関数に切り出し（GCS依存を注入可能に）
4. eval/test_extraction_eval.py — テスト本体
5. pytest.ini に eval マーカー登録

## 注意

- eval テストは実 Gemini API を叩くため **pytest tests/ では走らない**（`-m eval` マーカーで分離）
- visa-eval/test_cases_from_raw/ は実PII含むため git管理外
- ゴールデンデータの更新は visa-eval 側で行う（eval 側は参照のみ）
