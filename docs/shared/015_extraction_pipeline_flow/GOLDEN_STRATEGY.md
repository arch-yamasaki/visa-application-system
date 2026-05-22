# ゴールデンデータ戦略

## 現状の課題

既存のゴールデン（visa-eval/test_cases_from_raw/.../expected/case_data.golden.json）は初期段階で作成されたもので、以下の問題がある。

### 品質の問題
- intake Excel からの自動生成のみ。PDF（パスポート、オファーレター、会社書類）の情報が未反映
- 申請フォーム項目の約30%しかカバーしていない
- 性別が全員 "unknown"（パスポートから取れるはず）
- employment_conditions セクションが不存在（月給、契約形態、職種等）
- employer は会社名のみ（法人番号、資本金、従業員数等なし）
- 卒業日に実申請データとのズレあり（検証未了）
- 手動レビューされていない

### スキーマの不一致
- ゴールデン（case_data.schema.json 準拠）と visa-app（schema.py）でフィールド名が異なる
  - `birth_date` vs `date_of_birth`
  - `nationality_region` vs `nationality`
  - `sex` vs `gender`
- 自動比較が現状不可能

## 方針: visa-app 出力ベースで新ゴールデンを作成

### 理由
1. visa-app の抽出結果は PDF も含めて全書類から情報を取得（68フィールド、値あり証跡率100%）
2. フロントエンドの ReviewPage で人手レビュー・修正が可能
3. case_data.schema.json に schema.py のキー名を合わせれば、eval 比較・mapping がそのまま動く

### 実施ステップ

| # | 作業 | 担当 | 工数 |
|---|---|---|---|
| 1 | schema.py のキー名を case_data.schema.json に揃える | Engineer | 半日 |
| 2 | case_data.schema.json に employment_conditions セクション追加 | Engineer | 1時間 |
| 3 | eval_extract.py 作成（ローカルファイル→Gemini抽出→JSON保存） | Engineer | 2時間 |
| 4 | 13ケース分を eval_extract.py で一括抽出 | 自動 | ~7分 |
| 5 | 各ケースを ReviewPage で人手レビュー・修正 | PdM/QA | 1-2時間 |
| 6 | レビュー済みデータを expected/case_data.golden.json として保存 | Engineer | 30分 |
| 7 | eval_check.py 作成（品質メトリクス＋ゴールデン比較） | Engineer | 2時間 |
| 8 | rasens_offer_mapping.json の value_path を統一スキーマに合わせて確認 | Engineer | 1時間 |

### 新ゴールデンの構造

visa-app の `display_case_data` スキーマをそのまま採用。全フィールドはプレーン値（STRING）。

```json
{
  "golden_version": "2.0",
  "applicant": {
    "name_roman": "AMIT TAMANG",
    "nationality_region": "NEPAL",
    "birth_date": "1998-07-12",
    "sex": "男",
    ...
  },
  "passport": {
    "number": "PA2789572",
    "expiry_date": "2034-05-18"
  },
  "employer": {
    "name": "株式会社フジタ",
    "corporate_number": "8011001039242",
    "capital_jpy": "14002205010",
    ...
  },
  "employment_conditions": {
    "monthly_salary": "260000",
    "joining_date": "2026-04-01",
    ...
  },
  ...
}
```

### 既存ゴールデンとの関係

- 既存ゴールデン（v1）は削除しない。`golden_version: "1.0"` としてそのまま残す
- 新ゴールデン（v2）は `case_data.golden.v2.json` として並置する（移行完了後に v2 を正本に昇格）
- `compare_with_golden.py` は v2 形式に対応させる

### 正本の定義

```
case_data.schema.json  ← フィールド名・構造の正本
    ↓
schema.py (Gemini用)   ← 正本に準拠したスコープ別スキーマ
    ↓
display_case_data      ← 抽出結果（正本と同じキー名）
    ↓
case_data.golden.json  ← 人手レビュー済み正解データ（正本と同じ構造）
    ↓
rasens_offer_mapping   ← 正本のパスで case_data → フォーム入力値を変換
```

全てが case_data.schema.json のキー名に統一され、中間変換が不要になる。
