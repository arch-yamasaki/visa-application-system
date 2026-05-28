# Current Architecture

このディレクトリは、visa-app の現行アーキテクチャの入口です。

古い `docs/visa-reviewer-architecture.md` と `docs/shared/010_visa_app_overall_design/`、`011_frontend_design/`、`012_backend_api_design/` は、旧ステータスや旧レビューUIの説明が残っていたため削除しました。現行仕様はこのディレクトリと `visa-app/docs/002` 以降を正本として扱います。

## 全体像

visa-app は、申請書類をアップロードし、Gemini で `case_data`、`field_metadata`、`review` を抽出し、人間がレビュー画面で確認・補正したうえで、Chrome拡張へ `application-data` を渡すシステムです。

```text
Frontend
  Upload / Review UI
    ↓ /api
Backend FastAPI
  cases / documents / extraction / application-data
    ↓
Firestore + GCS
    ↓
Gemini extraction + bbox locator
    ↓
Chrome extension
  /cases/{case_id}/application-data の rows を RASENS DOM に入力
```

## 正本ドキュメント

| 領域 | 正本 |
|---|---|
| canonical case_data / field_metadata / review | `visa-app/docs/002_review_field_order/canonical_case_data_v2.md` |
| RASENS順レビュー項目 | `visa-app/docs/002_review_field_order/review_field_catalog.md` |
| Chrome拡張向け rows API | `visa-app/docs/002_review_field_order/application_data_api.md` |
| workflow state | `visa-app/docs/003_workflow_state_simplification/README.md` |
| Chrome拡張連携 | `visa-app/docs/004_chrome_extension_integration/README.md` |
| 案件一覧・レビュー順序 | `visa-app/docs/005_case_navigation_and_review_order/README.md` |

## 現行の状態方針

`workflow_state` は業務上の保存状態だけを表します。

```text
draft -> extracting -> extracted
                    -> failed
```

`needs_review` と `ready_to_fill` は旧データ互換として読むことがありますが、UIの正規状態として増やしません。

Chrome拡張の部分入力は許可します。`/application-data` の `fillable` は workflow 状態ベースで決まり、必須不足、warning、レビュー未完了では `fillable=false` にしません。取得できた `rows` だけを投入し、残った空欄は人がレビュー画面またはRASENS画面で補完します。

## ファイル構成

```text
visa-app/
  frontend/      React UI
  backend/       FastAPI, Gemini extraction, application-data generator
  jobs/          Codex runner job

rasens-autofill/
  extension/     Chrome拡張本体
  data/          RASENSフォーム台帳、mapping、合成fixture

visa-eval/
  scripts/       restricted評価用の補助script
  raw/           実案件資料。git管理外
  test_cases_from_raw/
```

詳細は次を参照してください。

- `backend_api_and_extraction.md`
- `frontend_review_ui.md`
