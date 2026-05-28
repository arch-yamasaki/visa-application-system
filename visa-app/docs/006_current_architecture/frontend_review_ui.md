# Frontend Review UI

## 役割

`visa-app/frontend` は React + Vite のレビューUIです。案件一覧、書類アップロード、抽出開始、抽出結果のレビュー、原本ビューアを担当します。

| 領域 | 主なファイル |
|---|---|
| ルーティング | `frontend/src/App.tsx` |
| API client | `frontend/src/api/client.ts` |
| 案件一覧 | `frontend/src/pages/CaseListPage.tsx` |
| アップロード | `frontend/src/pages/UploadPage.tsx` |
| レビュー画面 | `frontend/src/pages/ReviewPage.tsx` |
| フィールド一覧 | `frontend/src/components/review/FieldPanel.tsx` |
| 行表示/編集 | `frontend/src/components/review/FieldRow.tsx` |
| 繰り返し項目 | `frontend/src/components/review/RepeatedFieldGroup.tsx` |
| 原本ビューア | `frontend/src/components/viewer/DocumentViewer.tsx` |
| viewer state | `frontend/src/store/viewerStore.ts` |
| 表示順 | `frontend/src/lib/reviewFieldOrder.ts` |
| ラベル/型補助 | `frontend/src/lib/fieldPaths.ts` |

## 画面

| パス | 役割 |
|---|---|
| `/` | 案件一覧。case id、申請人名、案件名、状態を表示 |
| `/cases/{case_id}/upload` | 書類アップロードと抽出開始 |
| `/cases/{case_id}/review` | 左に抽出項目、右に原本を表示して編集 |

## レビュー画面の考え方

レビューUIは、RASENSフォーム順に近い順序で `case_data` を表示します。順序の正本は `reviewFieldOrder.ts` です。設計上の対応表は `visa-app/docs/005_case_navigation_and_review_order/form_order_detail_design.md` を参照します。

フィールドをクリックすると、対応する `field_metadata.source_refs[0]` へ移動します。PDFの場合は bbox があれば座標ハイライト、なければ text quote の検索ハイライトを使います。DOCX/XLSXはHTMLプレビュー上でテキスト検索します。

## 入力UI

`FieldRow` は field path の型に応じて、テキスト、数値、日付、select、boolean などの入力UIを切り替えます。

在日親族・同居者や職歴のような繰り返し項目は `RepeatedFieldGroup` で扱います。親項目が「有」のときだけ詳細を開き、最大3件まで入力できます。親項目が「無」の場合は詳細を保存必須にしません。

## workflow state 表示

UI上の状態表示は最小構成です。

```text
draft      未抽出
extracting 抽出中
extracted  抽出済み
failed     抽出失敗
```

旧 `needs_review` / `ready_to_fill` は互換として「抽出済み」に丸めます。レビュー完了状態、信頼度ドット、確認済み進捗、フィールド単位の要確認バッジはMVPから外しています。

## 保存

backend は `GET /cases/{case_id}` で表示用 `case_data` と保存用 `canonical_case_data` を返します。フロントエンドは編集時に両方を更新し、保存時は `canonical_case_data` を送ります。

表示用 default がそのままFirestoreへ混ざるのを避けるため、保存処理では `canonical_case_data ?? case_data` を使います。
