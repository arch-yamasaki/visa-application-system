# Chrome DevTools MCP QA

visa-app の実画面QAを Chrome DevTools MCP で効率よく行うための最小手順。

## 目的

- 実データcaseがフロントで表示できるか確認する。
- PDF bbox がレビュー画面で見えるか確認する。
- API / PDF / preview の Network と Console error を確認する。
- 同じ確認を短時間で繰り返せるようにする。

RASENSの最終送信は対象外。実RASENS画面を触る場合も最終送信は押さない。

## 起動

```bash
cd visa-app/backend
.venv/bin/python -m uvicorn main:app --reload --port 8080
```

```bash
cd visa-app/frontend
npm run dev
```

開くURL:

```text
http://127.0.0.1:5173/cases/{case_id}/review
```

## 基本確認

1. `take_snapshot` で画面構造を見る。
2. `抽出済み` が表示されることを確認する。
3. `身分事項`, `入国計画`, `所属機関`, `雇用・活動内容` が表示されることを確認する。
4. Networkは `/cases/` と `/documents/` を中心に見る。
5. `list_network_requests` で以下が 200 になっていることを確認する。
   - `/api/cases/{case_id}`
   - `/api/cases/{case_id}/documents/{document_id}/preview`
   - `/api/cases/{case_id}/documents/{document_id}/content`
6. `list_console_messages` で error / warning が出ていないことを確認する。

## PDF bbox確認

PDF由来で bbox が付きやすい項目をクリックする。

- 月額給与
- 契約の形態
- 雇用開始年月日
- 所属機関名
- 法人番号

確認すること:

1. クリックした行が選択状態になる。
2. 右側のdocument tabが対象PDFに切り替わる。
3. PDFページが表示される。
4. オレンジ色のbboxハイライトが表示される。
5. bboxがない場合でも画面が落ちず、証跡ページまたは文書表示に移動できる。

確認後は `take_screenshot` で現在のviewportを1枚残す。スクリーンショットは実PIIを含むため `qa/screenshots/` 配下でローカル管理し、gitに入れない。

## 確認マトリクス

同じcaseで毎回同じ代表項目を見る。

| 種類 | 代表項目 | 期待するviewer | 確認すること |
|---|---|---|---|
| PDF bboxあり | 月額給与 | PDF | PDFタブへ切替、bboxハイライト表示 |
| PDF bboxあり | 法人番号 | PDF | 会社書類PDFへ切替、bboxハイライト表示 |
| PDF bboxなし / fallback | bboxがないPDF証跡項目 | PDF | 画面が落ちず、ページまたはquote検索に進む |
| DOCX | オファーレター由来項目 | HTML preview | iframe内で該当quoteがハイライトされる |
| XLSX | 申請人情報由来項目 | HTML preview | 対象sheet/previewが表示され、該当quoteがハイライトされる |

正常な許容差:

- bboxなしは常に不具合ではない。backendのallowlist対象外やGemini bbox失敗でも、抽出結果は有効な場合がある。
- 現行UIは `source_refs[0]` を primary evidence として使う。
- PDF fallback は部分一致のため、誤ハイライトの余地がある。
- DOCX / XLSX は最初に見つかった一致箇所を `<mark>` する。

## APIレスポンス確認

必要に応じてbackend APIを直接見る。

```bash
cd visa-app/backend
.venv/bin/python - <<'PY'
import requests

case_id = "{case_id}"
base = "http://127.0.0.1:8080"
case = requests.get(f"{base}/cases/{case_id}").json()
metadata = case.get("field_metadata", {})

source_refs = 0
bbox_refs = 0
for item in metadata.values():
    for ref in item.get("source_refs") or []:
        source_refs += 1
        bbox_refs += bool(ref.get("bbox"))

print("metadata_fields", len(metadata))
print("source_refs", source_refs)
print("bbox_refs", bbox_refs)
PY
```

期待値:

- `case_data` に `source`, `source_ref`, `source_refs` が混入していない。
- 証跡は `field_metadata.*.source_refs[]` にある。
- PDF由来の一部 `source_refs` に `bbox` がある。

## 効率化のコツ

- 毎回同じ実データcaseを1つ決め、case IDをメモしておく。
- まず `GET /cases/{case_id}` で `workflow_state=extracted` を確認してから画面を開く。
- bbox確認は毎回同じ代表項目を見る。おすすめは `月額給与`。
- Console / Network / screenshot の3点だけを記録し、長いDOM全文や実値をログに残さない。
- 問題が出たら、まず API response の `field_metadata` に bbox があるかを確認し、次に viewer 表示の問題か backend 抽出の問題かを分ける。
