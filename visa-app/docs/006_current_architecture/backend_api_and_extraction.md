# Backend API And Extraction

## 役割

`visa-app/backend` は FastAPI サービスです。ケース管理、書類管理、Gemini抽出、PDF bbox取得、Chrome拡張向け `application-data` 生成を担当します。

| 領域 | 主なファイル |
|---|---|
| API | `backend/main.py` |
| Chrome拡張向け rows 生成 | `backend/application_data.py` |
| Gemini抽出 | `backend/extractors/gemini.py` |
| Gemini schema | `backend/extractors/schema.py` |
| Gemini prompt | `backend/extractors/prompt_template.py` |
| anchor / PDF bbox | `backend/extractors/anchor_resolver.py`, `backend/extractors/bbox_locator.py` |
| DOCX/XLSX/PDF処理 | `backend/extractors/docx_text.py`, `xlsx.py`, `pdf_text.py` |

## 主要API

| API | 役割 |
|---|---|
| `POST /cases` | ケース作成 |
| `GET /cases` | ケース一覧 |
| `GET /cases/{case_id}` | ケース詳細。表示用 `case_data` と保存用 `canonical_case_data` を返す |
| `PATCH /cases/{case_id}` | `case_data`, `field_metadata`, `workflow_state` の保存 |
| `POST /cases/{case_id}/documents` | 書類アップロード |
| `GET /cases/{case_id}/documents/{document_id}/content` | 原本表示用のバイナリ取得 |
| `GET /cases/{case_id}/documents/{document_id}/preview` | DOCX/XLSX HTMLプレビュー |
| `POST /cases/{case_id}/extract` | Gemini/Codex抽出開始 |
| `GET /cases/{case_id}/extraction-status` | 抽出状態確認 |
| `GET /cases/{case_id}/application-data` | Chrome拡張向け rows 取得 |

## 抽出フロー

```text
1. ユーザーが書類をアップロード
2. backend が GCS に保存し、Firestore の document_manifest を更新
3. `POST /extract` で workflow_state を extracting にする
4. PDFはGeminiへ直接送信、DOCX/XLSXはテキスト化してpromptへ入れる
5. Geminiが FieldValue (`value`, `source_ref`, optional `alternatives`) 形式で抽出する
6. backend が表示用 value-only `case_data` と、証跡用 `field_metadata` (`source_refs`, optional `alternatives`) に正規化する
7. anchor resolver / bbox locator が primary refs と alternatives refs の位置を補完する
8. Firestoreへ保存し、workflow_state を extracted にする
```

Gemini抽出は `case_data` を value-only の canonical data として保存します。フォーム入力用の `field_id` や select value は `case_data` には保存せず、`application-data` 生成時に mapping と form definitions から作ります。

値が書類間で食い違う場合は、primary value 以外の候補を `field_metadata[path].alternatives[]` に保持します。各 alternative は `value` と `source_refs[]` を持ち、primary `source_refs[]` と同じ anchor / bbox 解決対象です。表示用 `case_data` には alternatives を混ぜません。

抽出結果の保存時は、既存の `case_data` を土台にしてGemini結果を deep merge します。これにより、ケース作成時や人手編集で持っている `case.*`、`proxy`、`receiving_method` など、Geminiが責任を持たない領域を抽出結果で消さないようにします。`review` と `field_metadata` は最新抽出結果で置き換えます。

## application-data

`GET /cases/{case_id}/application-data` は、Chrome拡張がそのまま入力できる `rows` を返します。

```text
Firestore case_data
  + Firestore org_settings/{org_id}
  + backend/data/mappings/rasens_offer_mapping_v2.json
  + backend/data/form_definitions/rasens_offer_fields.json
  + 固定値/推測値
  -> rows
```

`fillable` は原則として workflow 状態で決めます。

```text
fillable = workflow_state in extracted / needs_review / ready_to_fill
           and intermediary org settings is 5/5 configured
           and notification email is configured
```

一般項目の必須不足や空欄は `fillable=false` の理由にしません。空値の mapping は rows から落ち、取得できた行だけがChrome拡張で部分入力されます。ただし組織共通の取次者5項目と通知メールは一体で確認し、欠けている場合は `fillable=false` にします。受領方法は `メール Email` 固定で、通知メール再入力欄にも同じ値を生成します。`/api` 経路では Firestore `org_settings/{org_id}` だけを正本にし、未登録時にグローバル環境変数へfallbackしません。

## 保存データと表示データ

`GET /cases/{case_id}` は、レビュー画面で見やすいように default や推測値を適用した `case_data` を返します。同時に、保存用の元データとして `canonical_case_data` も返します。

フロントエンドは編集時に表示用 `case_data` と保存用 `canonical_case_data` の両方を更新し、保存時は `canonical_case_data` を送ります。

## GCP

| サービス | 用途 |
|---|---|
| Firestore | `cases`, `sessions` |
| GCS | アップロード書類、Codex runner成果物 |
| Cloud Run | `visa-app` |
| Cloud Run Jobs | `codex-runner-job` |
| Secret Manager | `GOOGLE_API_KEY` |

Codex runner はMVPの主導線ではありません。現行の実データ抽出はGeminiを中心に扱います。
