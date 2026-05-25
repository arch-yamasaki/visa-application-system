# ステータス管理の簡素化

## 目的

MVPでは、業務状態とレビュー画面内の確認進捗を分けて扱う。

ユーザーに見せる状態は、まず次の4つだけにする。

| 表示状態 | 意味 |
| --- | --- |
| 未抽出 | case はあるが、抽出結果がまだない |
| 抽出中 | Gemini / Codex で抽出処理中 |
| 抽出済み | 抽出結果が保存され、レビュー画面で確認・編集できる |
| 抽出失敗 | 抽出に失敗し、再実行が必要 |

`needs_review` と `ready_to_fill` は、移行互換として読み取る。ただし新しく保存する `workflow_state` は `draft / extracting / extracted / failed` に寄せる。

## 対象ファイル

| 領域 | ファイル | 役割 |
| --- | --- | --- |
| frontend | `frontend/src/lib/workflowState.ts` | backend の `workflow_state` をUI用4状態へ正規化 |
| frontend | `frontend/src/pages/CaseListPage.tsx` | 案件一覧の状態表示と遷移先 |
| frontend | `frontend/src/pages/ReviewPage.tsx` | レビュー画面、保存処理 |
| frontend | `frontend/src/components/review/ReviewBanner.tsx` | レビュー画面上部の状態表示 |
| frontend | `frontend/src/components/review/FieldPanel.tsx` | 表示フィールドの組み立て |
| frontend | `frontend/src/components/review/FieldSection.tsx` | セクション表示 |
| frontend | `frontend/src/components/review/FieldRow.tsx` | フィールド行表示、証跡ジャンプ、編集 |
| backend | `backend/main.py` | Firestore の `workflow_state` 更新 |
| backend | `backend/application_data.py` | Chrome拡張向け `/application-data` の `fillable` 判定 |
| extension | `rasens-autofill/extension/api_client.js` | Chrome拡張の case 一覧取得 |
| extension | `rasens-autofill/extension/popup.js` | Chrome拡張の状態表示と投入可否表示 |

## 設計方針

### 表示状態は frontend で正規化する

backend の保存値をすぐ全変更すると、既存 Firestore データ、Chrome拡張、テストへの影響が大きい。

そのため第一段階では、frontend の `workflowState.ts` で表示用状態に寄せる。

```ts
draft / uploading -> draft
extracting -> extracting
needs_review / ready_to_fill / extracted -> extracted
extraction_failed / launch_failed / failed -> failed
```

### レビュー進捗は workflow_state に混ぜない

MVPでは「AI抽出結果は必ず人が見る」前提なので、`needs_review` をユーザー状態として見せる意味は薄い。

また、`human_reviewed`、`confirmed_at`、セクション単位の「全て確認済み」は、現時点では業務上の必須条件にしない。レビュー画面は、抽出結果を見て編集し、保存する画面にする。

### Chrome拡張の投入可否は `/application-data` で判定する

Chrome拡張は `workflow_state` 名を直接判断しない。backend の `/application-data` が返す `fillable` と `warnings` を見て、入力ボタンを制御する。

MVPでは、抽出済みデータは必ず人間がレビュー画面で確認・編集できる前提なので、`extracted` 相当を投入可能にする。

## 今回完了したこと

- `frontend/src/lib/workflowState.ts` を追加し、UI表示を4状態に統一した。
- 案件一覧の状態表示を `未抽出 / 抽出中 / 抽出済み / 抽出失敗` に簡素化した。
- `needs_review`、`ready_to_fill`、将来の `extracted` は、一覧からレビュー画面へ遷移するようにした。
- `ReviewBanner` から確認済カウント、進捗バー、要対応件数、編集済件数を削除した。
- `FieldSection` から `0/11` の確認進捗、`全て確認済み`、`確認完了` を削除した。
- `FieldRow` から信頼度ドット、編集済バッジ、要確認バッジ、要対応バッジを削除した。
- `FlagBadge.tsx` を削除した。
- レビュー画面下部の `確認して完了` を `保存` に変更した。
- 保存時に `workflow_state: ready_to_fill` を送らないようにした。
- PDF / xlsx の証跡ジャンプと bbox 表示導線は残した。
- E2Eを新しいUIに合わせて更新した。
- backend の抽出成功保存値を `extracted`、失敗保存値を `failed` に寄せた。
- `/application-data` は `extracted / needs_review / ready_to_fill` を `fillable=true` として扱うようにした。
- Chrome拡張popupの状態表示を `未抽出 / 抽出中 / 抽出済み / 抽出失敗` に統一した。
- Chrome拡張の case 一覧取得から `workflow_state=ready_to_fill` 固定を外した。
- Cloud Run でも同じ form definition を読めるように、`backend/data/form_definitions/rasens_offer_fields.json` を同梱した。

## 残り作業

### 1. 型・docs・テストから古い概念を削る

削除候補:

- `human_reviewed`
- `confirmed_at`
- `ready_to_fill`
- `needs_review`
- `FlagBadge` 系の説明

ただし Firestore 既存データに残る値は、読み取り互換を残したうえで段階削除する。

### 2. Chrome拡張の実RASENS QAを進める

`content.js` のDOM入力は今回ほぼ触っていない。次は実RASENS画面で `preview / fill / progressive fill` を確認し、missed項目があれば mapping / form definition 側を直す。

### 3. Cloud Run デプロイ後の連携確認

デプロイ後は popup の API URL を Cloud Run に切り替え、`/cases/{case_id}/application-data` が `fillable=true` と rows を返すことを確認する。

## 注意点

- `workflow_state` 旧値は互換読み取り用に残す。新規保存は4状態へ寄せる。
- `review.missing_items` / `validation_errors` 由来の項目追加はまだ残している。バッジは消したが、確認すべき空欄が一覧から消えるのは避ける。
- `human_edited` は内部メタデータとして残しているが、UIには出さない。
- PDF / xlsx の証跡表示は、ステータス簡素化とは別の重要導線なので消さない。
- 実PIIを含むケースでQAする場合、スクリーンショットや `chrome.storage.local` の残存に注意する。

## 推奨コミット分割

1. frontend 表示簡素化、E2E更新
2. backend `workflow_state` の新旧互換、`/application-data` と Chrome拡張の `extracted` 対応
3. 古い型・docs・テストの削除
4. Chrome拡張の実RASENS QAと mapping 修正
