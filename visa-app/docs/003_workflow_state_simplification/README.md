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

`needs_review` と `ready_to_fill` は、移行期間中は backend / Firestore に残してよい。ただし UI ではどちらも `抽出済み` と表示する。

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

### Chrome拡張の投入可否は別フェーズで整理する

現在の `/application-data` は `workflow_state == "ready_to_fill"` のときだけ `fillable=true` にしている。

UIから `ready_to_fill` 遷移を消すと、Chrome拡張側では投入不可に見える可能性がある。次フェーズで `extracted` 相当の状態を投入可能として扱う。

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

## 残り作業

### 1. backend の状態名を整理する

現在の backend は抽出成功時に `needs_review`、抽出失敗時に `extraction_failed` を保存している。

次のように寄せる。

| 現状 | 変更後 |
| --- | --- |
| `needs_review` | `extracted` |
| `extraction_failed` | `failed` |
| `launch_failed` | `failed` |

ただし、移行期間中は旧値も読み取れるようにする。

### 2. `/application-data` の fillable 判定を更新する

現在:

```py
fillable = workflow_state == "ready_to_fill"
```

変更案:

```py
fillable = workflow_state in {"extracted", "needs_review", "ready_to_fill"}
```

MVPでは、抽出済みデータは人間がレビュー画面で確認・編集できるため、Chrome拡張が case ID 指定で取得できる状態にする。

### 3. Chrome拡張の状態表示を更新する

`rasens-autofill/extension/popup.js` はまだ `要レビュー`、`入力準備完了` を表示する。

visa-app frontend と同じ考え方で、拡張側も次の4表示に寄せる。

- 未抽出
- 抽出中
- 抽出済み
- 抽出失敗

### 4. Chrome拡張の case 一覧取得を更新する

`rasens-autofill/extension/api_client.js` は現在 `workflow_state=ready_to_fill` で一覧取得している。

次フェーズでは、backend 側に `workflow_state=extracted` 相当の一覧取得を用意するか、拡張では case ID 指定取得を主導線にする。

### 5. 型・docs・テストから古い概念を削る

削除候補:

- `human_reviewed`
- `confirmed_at`
- `ready_to_fill`
- `needs_review`
- `FlagBadge` 系の説明

ただし Firestore 既存データに残る値は、読み取り互換を残したうえで段階削除する。

## 注意点

- `workflow_state` の保存値変更は、Chrome拡張の `fillable` 判定と同時に見る。
- `review.missing_items` / `validation_errors` 由来の項目追加はまだ残している。バッジは消したが、確認すべき空欄が一覧から消えるのは避ける。
- `human_edited` は内部メタデータとして残しているが、UIには出さない。
- PDF / xlsx の証跡表示は、ステータス簡素化とは別の重要導線なので消さない。
- 実PIIを含むケースでQAする場合、スクリーンショットや `chrome.storage.local` の残存に注意する。

## 推奨コミット分割

1. frontend 表示簡素化、E2E更新
2. backend `workflow_state` の新旧互換
3. `/application-data` と Chrome拡張の `extracted` 対応
4. 古い型・docs・テストの削除
