# Golden抽出精度レポート - 2026-09-02

## 結論

現在の主指標は、8 fixture・287 verified extraction値項目に対して **260/287 = 90.6%**。

| 指標 | 件数 |
|---|---:|
| 一致 | 260 |
| 値違い | 27 |
| 抽出漏れ | 0 |
| extra | 34 |
| scope失敗 | 0 |

287項目は、input資料からAIが取れるべき `case_data` のうち、人が確認済みの項目だけである。RASENSで入力するための値でも、input資料から完全には決められない項目は `application_only` として採点から外した。

同じAI runは、見直し前の評価契約では259/315 = 82.2%だった。今回、住所・法人番号・役職の39不一致を原資料とRASENS出力で再監査し、正解値の誤りと採点scopeを修正した。90.6%への変化は、**モデルの改善ではなく、評価データを正しくした影響**である。

このレポートでは、値精度、source_ref充足、anchor表示、semantic正確性、extraを別指標として扱う。`source_refs` とquoteが存在することは、viewerでanchor表示できることや、表示位置が意味上正しいことを保証しない。anchor表示とsemantic正確性は、統一アンカー実装と人手レビューで別途確認する。

また、この最終runには現行の `run_manifest.json` 契約がまだ揃っていないため、model、prompt/schema hash、retry条件を機械的に完全再現するには制約がある。今後の抽出runでは `run_manifest.json` を必須にし、golden revisionは比較結果側へ記録する。

## 何と何を比較したか

```text
AIへ渡すもの
  input/document_manifest.json で use_as_input=true の原資料だけ

AIへ渡さないもの
  output/rasens_application/ の入力済み申請書
  expected/ と expected_verified/ のgolden

比較
  AIが生成した canonical case_data
    vs
  expected_verified/case_data.golden.json のうち
  golden_manifestで extraction / verified の項目
```

旧 `expected/` は変更していない。新しい比較用データは `expected_verified/` に分けて保存している。

## Golden側の現在状態

| 区分 | 件数 |
|---|---:|
| fixture | 8 |
| field rules | 577 |
| 採点対象 extraction | 287 |
| application_only | 218 |
| excluded | 72 |
| goldenの needs_review | 0 |
| 未分類 | 0 |
| manifest path error | 0 |

入社日は6 fixtureともinput原資料では年月までしか確認できなかったため、値を削除せず `application_only` へ移した。日を推測して完全日付を作ることはしていない。

職種goldenのうち、旧い短縮ラベルだった4 fixtureは、原資料の予定業務と現行RASENS選択肢を照合し、正式ラベルへ更新した。旧 `expected/` は変更していない。

### 住所・法人番号・役職の再監査

判定基準は「AIに渡したinput資料だけで、値と粒度を一意に決められるか」の1つに絞った。

| 分類 | 対応 |
|---|---|
| 出生地 | 7件ともinputから再現できるため `extraction` 維持 |
| 本国住所 | 3件はinputの現住所でgoldenを修正、残りは維持 |
| 所属機関住所 | inputだけでRASENSの粒度まで決められない6件を `application_only` |
| 法人番号 | inputに「法人番号」として明示された13桁がない6件を `application_only` |
| 法人番号の有無 | 番号本体からの派生値として `application_only` |
| 役職名 | 職種・担当業務を役職としていた4件を空に修正 |
| 役職の有無 | 役職名からの派生値として `application_only` |

値の正本は `case_data.golden.json` 1つのままで、中間goldenは増やしていない。存在する旧 `expected/` 2件はSHAで不変を確認した。

## 実装修正

- 比較器は、全角半角、余分な空白、大文字小文字、安全なboolean・性別・婚姻状態・国名・関係ラベルだけを限定的に正規化する。
- 住所要素の欠落、法人番号の桁違い、年月と年月日の差、意味の違う職種は一致扱いにしない。
- 法人番号は記号除去後13桁だけを採用し、12桁を補完しない。不確かな値はprimaryにも候補にも残さず空欄にして、人の確認へ回す。
- 性別・婚姻状態は内部値へ統一し、引用は原文のまま残す。
- 役職名、現在職、採用後職種を分ける。職種は特定fixture由来のカテゴリへbackendで固定変換せず、Geminiへ現行RASENSラベルでの出力を指示する。
- 一時的なGemini API障害だけ、初回を含め最大3回まで再試行する。認証エラーやJSON不正は再試行しない。

再試行追加前のrunでは、一時的な503により2 fixtureで合計3 scopeが欠け、20項目が抽出漏れになった。再試行追加後の最終runではscope失敗0、抽出漏れ0になった。

## 精度結果

### 項目グループ別

| グループ | 一致 | 採点対象 | 正答率 |
|---|---:|---:|---:|
| applicant | 191 | 215 | 88.8% |
| employer | 29 | 30 | 96.7% |
| employment | 40 | 42 | 95.2% |
| 合計 | 260 | 287 | 90.6% |

残る不一致は申請人情報に集中している。

### 不一致27件の内訳

| 原因グループ | 件数 | 主な項目 |
|---|---:|---|
| 出生地・本国住所 | 10 | `birth_place`, `home_country_address` |
| 現在職・国籍 | 6 | `occupation`, `nationality_region` |
| 学歴 | 4 | 学歴detail、卒業日、学校名、専攻other |
| 職種分類 | 2 | `job_category_primary` |
| 日本連絡先 | 2 | email、mobile |
| その他 | 3 | 資本金、職歴終了日、家族名 |

法人番号と役職は、モデルの間違いを隠したのではなく、そもそもAI入力から決められない値、または派生値だったため、値を残したまま採点対象から分けた。残る最大の課題は出生地と本国住所の10件である。

### 根拠品質

| status | 項目数 | source refsあり | quoteあり | input manifest内のdoc id |
|---|---:|---:|---:|---:|
| 一致 | 260 | 260 | 260 | 260 |
| 不一致 | 27 | 21 | 21 | 21 |
| 合計 | 287 | 281 | 281 | 281 |

一致項目は全件に原資料の引用がある。不一致27件のうち6件はprimary根拠が空で、学歴補助項目、連絡先、職歴終了日などである。

この表はsource_ref充足の確認であり、anchor表示率やsemantic正確性の確認ではない。PDF bbox、XLSX cell、DOCX blockとして画面で表示できるか、またその位置が意味上正しいかは別指標として扱う。

golden側の `needs_review` は0だが、最終AI runでは8 fixture中6件が `needs_review` になった。6件とも法人番号の13桁確認ができなかったことが原因である。golden未確認とAI出力の要確認は別の数字として扱う。

## extra 34件とは何か

extraは「AI出力には非空値があるが、goldenの同じpathが存在しない項目」。正答率287項目の分母・分子には入らない。

extra 34件は全件に `source_refs` とquoteがあり、根拠なしの幻覚は見つからなかった。ただし、根拠があることと、アプリで必要な正解項目であることは別である。

| 分類 | 件数 | なぜextraになるか | 方針 |
|---|---:|---|---|
| 職歴の配列行差 | 19 | AIは資料上の複数職歴を拾うが、goldenは申請で必要な行・粒度だけを持つ | 必要行のルールを決め、全行を無条件にgoldenへ足さない |
| 会社郵便番号 | 7 | AIは会社資料から拾うが、現在のgoldenにpathがない | アプリ入力で使うならgolden追加。不要なら抽出抑制 |
| 日本連絡先mobile | 3 | 入力資料に根拠はあるが、golden対象が未決定 | 必要ならgolden追加。不要なら抑制 |
| 役職名 | 3 | `has_position` と条件が合わない、またはgoldenに役職名がない | `has_position=true` のときだけ扱う |
| 日本連絡先email | 2 | 根拠はあるが、今回の検証スコープでは不要寄り | いったん抽出抑制 |
| 合計 | 34 |  |  |

旧runのextra 44件からは10件減った。学歴補助欄、専攻補助欄、入社日、業種その他などのノイズが減っている。一方、extraをすべてAIミスと決めたり、すべてgoldenへ追加したりするのはどちらも誤りである。

## run間の読み方

| run | 条件 | 結果 | 扱い |
|---|---|---:|---|
| 2026-09-01 独立rescore | 当時の321項目 | 255/321 = 79.4% | 当時の公表値 |
| 同じ旧runを現在の契約で再集計 | 現在の315項目・比較器 | 263/315 = 83.5% | 比較契約変更の影響を見る参考値 |
| 修正後1回目 | 現在の315項目、scope 3件が503 | 248/315 = 78.7% | API一時障害込み。主結果にしない |
| 修正・再試行追加後の最終run | 当時の315項目、scope失敗0 | 259/315 = 82.2% | golden再監査前の履歴値 |
| 同じ最終runをgolden再監査後に再採点 | 287項目、scope失敗0 | 260/287 = 90.6% | 現在の主指標。モデル改善ではない |

最終run自体は同じで、82.2%から90.6%への変化は評価契約の修正による。8 fixtureのfieldは互いに独立ではなく、同じ会社資料を使うfixtureも多い。モデル改善は、次に別runを実行して判定する。

## レビューと検証

実装、比較契約、golden監査、extra監査、根拠監査を担当分けし、実装担当と別担当が相互レビューした。

- backend: 268 tests passed
- comparator checks: 8 passed
- golden audit: 8 fixture、287 scored、needs_review 0、unclassified 0、manifest error 0
- 住所・法人番号・役職の画像証拠レビュー: 39 field、3カテゴリすべて独立レビュー済み、needs_review 0
- 旧 `expected/`: 存在する2 fixtureでSHA不変
- diff check: passed
- retry最終レビュー: Critical 0、Major 0
- run健全性: 8/8完走、scope failure 0、missing 0、golden混入0

## 次の改善順

1. 残る住所系10件は、別住所を拾った誤りと、同じ住所の表記差を分け、authority資料の優先順位を抽出指示に反映する。比較器で住所要素の欠落を無理に一致させない。
2. 現在職・国籍の6件を、項目の取得元違いと表記変換に分ける。
3. extraは、会社郵便番号とmobileの必要性だけ決める。職歴配列へ複雑な自動整列はまだ入れない。

この3点以外の少数項目は後回しでよい。
