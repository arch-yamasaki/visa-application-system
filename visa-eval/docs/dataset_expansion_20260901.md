# Fixture dataset expansion - 2026-09-01

## 結論

`visa-eval/test_cases_from_raw/` の申請人数を2名から8名へ増やした。

現在の状態は次のとおり。

| 状態 | 人数 | できること |
|---|---:|---|
| fixture ready | 8 | inputを使ったAI抽出、outputを使ったgolden監査 |
| scoring ready | 8 | `expected_verified` を使った定量精度評価 |
| golden pending | 0 | 新規6名も `expected_verified` 作成済み |

新規6名についても、旧 `expected/` は作らず、現在の比較用正本として `expected_verified/case_data.golden.json` と `golden_manifest.json` を作成した。AI結果は下書き・差分発見の補助として使い、正解の扱いは manifest の `scope` で分ける。

## PDFの分離結果

結合PDFは「先頭10ページ固定」では分けず、各PDFの実ページを確認して物理分割した。

| 元PDFのページ数 | output / RASENS | input / 添付資料 | 備考 |
|---:|---:|---:|---|
| 23 | 1-8 | 10-23 | 9ページ目は空白セパレーター |
| 19 | 1-10 | 11-19 |  |
| 15 | 1-10 | 11-15 |  |
| 21 | 1-11 | 12-21 | RASENS側が11ページある例外 |
| 16 | 1-10 | 11-16 |  |
| 21 | 1-10 | 11-21 |  |
| 18 | 1-10 | 11-18 | 既存fixture |
| 20 | 1-10 | 11-20 | 既存fixture |

配置先は次で統一した。

```text
input/submitted_application_attachments/  # 旅券、学歴証明等。AI入力
output/rasens_application/                # 入力済み申請画面・申請書。AIには渡さない
```

rawに別置きされていた申請人別資料は、氏名が一意に対応したものだけ `input/files/` に追加した。対応する申請人を確定できなかった資料はfixtureへ混ぜていない。

## 実施した検証

- 8 fixtureが8人・8個の元申請PDF束へ一意に対応すること
- input manifestの資料合計46件、output manifestの資料合計8件が実在すること
- PDFの `origin_pages` と分割後ページ数が一致すること
- 分割後152ページを再レンダリングし、元PDFの対応ページと画素単位で一致すること
- outputとinputの境界が重ならないこと
- 唯一の欠番が23ページPDFの空白9ページ目だけであること
- `use_as_input=true` がinputだけ、RASENS outputは `false` であること
- Gemini bytes evalの `--dry-run` が8件すべて成功すること
- raw、旧 `expected/`、既存 `expected_verified/` を変更していないこと

## Golden 作成結果

新規6名の `expected_verified` を追加し、全8名を scoring ready にした。

作業はCodex実装担当3名が2 fixtureずつ受け持ち、その後、担当を入れ替えた3名で交差レビューした。Claude Code側にも実装・レビュー役を分けた確認を依頼したが、長時間無出力の処理は中断し、最終判断はCodex側の原PDF目視、同一資料SHA照合、manifest coverage検査、独立再抽出runの結果で確定した。レビュー指摘はそのまま採用せず、別担当とrootが原資料で再判定した。

| 対象 | field_rules | extraction | application_only | excluded | needs_review |
|---|---:|---:|---:|---:|---:|
| 既存2名 | 139 | 74 | 51 | 14 | 0 |
| 新規6名 | 442 | 241 | 143 | 58 | 0 |
| 合計8名 | 581 | 315 | 194 | 72 | 0 |

採点母数は `scope=extraction` かつ `verification=verified` のみ。`entry_plan.*`、固定値、派生値、RASENS出力でのみ確認できる値、活動内容の申請向け文言、否定のカウント系などは、AI抽出精度へ混ぜない。

新規6名は初版を `v0001` とし、交差レビューで修正したfixtureはrevisionを更新した。全件のstatusは `reviewed`。旧 `expected/` がないため、`source_expected_dir` と `source_golden_sha256` は `null` にしている。

交差レビューでは、同一会社資料を使う7件の会社情報がAI下書きの揺れによって不一致になっていることを検出した。会社資料のSHA-256が同一であることを確認し、既存の原資料監査済みfixtureを基準に13項目を統一した。これにより、法人番号の桁落ち、会社項目の欠落、申請で使わない補助欄、fixtureごとに異なる郵便番号候補を除去した。別の1件ではinput CVとRASENS outputで職歴行の構成が一致しないため、値は保持しつつ職歴9項目を `excluded` にした。

## 再抽出比較

`20260901_eight_fixture_eval` は新規golden作成時の下書き補助として使ったため、そのまま精度指標にはしない。別run `20260901_eight_fixture_rescore` で8名を再抽出し、当時の `expected_verified` と比較した。次の321項目は当時の評価契約による履歴値であり、現在は入社日6項目を `application_only` へ移したため採点対象は315項目である。

| 指標 | 件数 |
|---|---:|
| 採点対象field | 321 |
| 一致 | 255 |
| 不一致 | 66 |
| 抽出漏れ | 0 |
| 過剰抽出 | 44 |
| manifest CONFIG_ERROR | 0 |
| needs_review | 0 |

AI抽出のgolden比較一致率は 255/321 = 79.4%。この数字はgolden作成に使ったrunとは別の再抽出runによるAI抽出の回帰比較値であり、RASENS変換やChrome拡張入力の評価は含めない。

根拠参照は、独立再抽出runで採点対象321項目中316項目（98.4%）に存在した。全参照のdocument idはinput manifest内にあり、空quoteは0。根拠参照がない5項目は値比較と混ぜず、AI側のevidence issueとして残す。golden作成補助runでは319/321項目にanchorがあり、206項目にはbboxも付与されていたが、このrunの一致率は自己比較になるため精度値には使わない。

## rawの重複と削除方針

rawのzipと展開済みファイルは同じ受領データだったため、人数として二重計上しない。会社資料PDFにも同一内容の複製が1組あるが、manifestでは片方だけを使う。

rawは受領原本・provenanceなので削除していない。削除対象にしたのは、ページ確認のために生成した一時レンダーとOCR派生物だけである。

## 次の作業

2026-09-02に、比較契約、golden分類、抽出後処理、API一時障害retryを修正し、8 fixtureを再実行した。現在の主結果は315項目中259項目一致、82.2%、抽出漏れ0、extra 34である。詳細は `accuracy_report_20260902.md` を参照する。

1. 住所系、法人番号scope、役職境界の3点を優先する
2. extraの会社郵便番号とmobileを検証対象にするか決める
3. 必要になった段階で `case_data -> application_data` のRASENS変換比較を別スコープで追加する
