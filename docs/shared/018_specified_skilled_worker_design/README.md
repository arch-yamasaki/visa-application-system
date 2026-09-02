# 特定技能対応の全体設計

## 結論

特定技能を追加しても、現在の基本フローは変えない。

```text
書類アップロード
  -> AI抽出
  -> case_dataで人が確認・修正
  -> 対象フォーム用のapplication_dataを生成
  -> Chrome拡張でRASENSへ入力
```

変更するのは、主に次の3点だけでよい。

1. 案件作成時に「技人国 / 特定技能」を選べるようにする。
2. 共通データは今のまま使い、特定技能だけの値を1か所へ追加する。
3. RASENSのフォーム台帳とmappingを技人国用・特定技能用に分け、backendが案件に合う方を選ぶ。

Chrome拡張、workflow state、保存層を作り直す必要はない。特定技能の多数の確認事項を一つの巨大な共通schemaへ混ぜたり、技人国版のアプリを丸ごと複製したりもしない。

## 今回確認した範囲

対象MHTML:

`/Users/yohei/Downloads/【在留申請オンラインシステム及び電子届出システム】手続き申込：申込.mhtml`

保存されていた画面は、次の組合せだった。

- 手続き: 在留資格認定証明書交付申請
- RASENS区分: 区分V
- 在留資格: 特定技能

MHTMLには入力系control（input/select/textarea）が691個、buttonを含めると730個含まれていた。静的なHTMLだけで `display:none` や `type=hidden` を除くと入力系controlは378個だが、これはあくまで保存時点の補助指標であり、実務上の入力項目数ではない。1項目が複数controlを持つ場合や、JavaScript/CSSで条件表示される項目があるためである。

また、特定技能とは無関係な「高度専門職ポイント表」も非表示状態で同梱されていた。したがって、MHTML内の全項目を特定技能の入力対象としてコピーしてはいけない。フォーム台帳では「この申請プロファイルで有効か」と「どの条件で表示されるか」を持つ必要がある。

今回のMHTMLだけから確定できるのは、上記の在留資格認定証明書交付申請の構造である。在留資格変更許可申請と在留期間更新許可申請は、別の画面保存を取得してから別プロファイルとして確認する。

## 技人国と特定技能で何が違うか

### そのまま共通利用する情報

次の値は、特定技能でも既存の `case_data` をそのまま使う。

| 情報 | 保存先 |
|---|---|
| 氏名、国籍、生年月日、性別、出生地、本国住所 | `applicant.*` |
| 日本の連絡先、旅券 | `applicant.japan_contact.*`, `applicant.passport.*` |
| 入国予定、上陸予定港、在留予定期間 | `entry_plan.*` |
| 出入国歴、COE申請歴、犯罪歴、在日親族 | `applicant.immigration_history.*`, `applicant.family.*` |
| 所属機関名、法人番号、住所、資本金、売上、従業員数 | `employer.*` |
| 雇用期間、月額報酬、勤務地など共通する雇用条件 | `employment.*` |
| 代理人 | `proxy.*` |
| 取次者、受領方法 | 現行どおり、案件値とは分けた既存設定からrows生成時に入れる |

同じ意味の値を特定技能用の領域にも複製しない。例えば、法人番号を `employer.corporate_number` と特定技能用pathの両方に持つ設計にはしない。

### 特定技能で新しく必要になる情報

MHTMLで確認できた特定技能固有項目は、大きく4群にまとめられる。

| 群 | 主な内容 |
|---|---|
| 申請人の要件 | 技能水準、日本語能力、技能実習2号の良好修了、特定技能1号の通算期間、保証金・費用負担等 |
| 特定技能雇用契約 | 特定産業分野、業務区分、労働時間、日本人との報酬比較、支払方法、派遣先、職業紹介・外国機関等 |
| 特定技能所属機関 | 社会保険・労働保険、法令違反・欠格事由、契約履行体制、報酬支払の確認等 |
| 支援 | 支援委託、支援責任者・担当者、支援言語、1号支援計画、登録支援機関等 |

1号特定技能外国人について、受入れ機関は支援計画を作成して支援を行い、その実施を登録支援機関へ委託できることが入管庁の公式説明にも示されている。そのため、支援は単なる補足欄ではなく、特定技能1号の独立したレビュー群として扱う。詳細な制度判断は、実装時点の[出入国在留管理庁「1号特定技能外国人支援・登録支援機関について」](https://www.moj.go.jp/isa/policies/ssw/supportssw.html)と最新の運用要領で再確認する。

## 推奨するデータ設計

### case_data

共通部分を維持し、特定技能固有データだけを `specified_skilled_worker` にまとめる。

```text
case_data
  case
    application_type       # certificate_of_eligibility
    target_status          # specified_skilled_worker
    target_status_variant  # ssw_1 または ssw_2
  applicant                # 共通
  entry_plan               # 共通
  employer                 # 共通
  employment               # 共通
  proxy                    # 共通。案件ごとに確認する代理人
  specified_skilled_worker
    eligibility            # 技能・日本語・技能実習・申請人側確認
    contract               # 特定技能固有の契約情報
    organization           # 所属機関の適合性確認
    support                # 1号支援計画・登録支援機関
```

`status_specific.specified_skilled_worker` のような汎用wrapperは、今は作らない。在留資格が2種類の段階では階層が1つ増えるだけであり、必要になってから移行できるためである。

`target_status_variant` は1号/2号の条件表示に使う。1号用と2号用で `case_data` 全体やフォーム台帳を複製せず、同じ特定技能プロファイル内の `visible_when` で出し分ける。

### 値の入れ方は3種類だけにする

特定技能には、資料から読める値と、人が確認しなければならない宣言が混在する。各項目の入力方針は次の3種類に絞る。

| 方針 | 意味 | 例 |
|---|---|---|
| 資料から読む | AIが抽出し、根拠画像・page・quoteを付ける | 試験名、契約期間、分野、報酬、登録番号 |
| 人が確認する | AIは勝手にYes/Noを確定しない | 保証金、法令違反、欠格事由、支援体制の適合 |
| 設定または計算で入れる | 既存設定や決定的な変換から生成する | 取次者、受領方法、日付・金額の書式変換 |

案件ごとの値は従来どおり `case_data` に置き、既存の取次者・受領方法は現在の設定経路を維持する。入力方針を値のwrapperに混ぜず、フォームプロファイルまたはレビュー規則側で管理する。

特に「資料に記載がない」は「無」ではない。人確認項目は、AI抽出schemaの必須項目に入れず、担当者が確認した後で初めて `case_data` に値を持たせる。未確認の間は `review` 側に確認待ちとして出し、RASENS rows生成では値が無いものとしてスキップまたはブロックする。

既存の技人国向けには、過去の出入国歴や犯罪歴などを未記載時に `false` として扱う既定処理がある。特定技能の所属機関欠格事由、保証金、支援体制などはこの既定処理へ安易に追加しない。ここは「資料から推定したNo」ではなく「担当者が確認したNo」が必要な領域である。

## RASENSフォームの設計

### 既存ファイルは変更・改名しない

初回実装では既存の技人国ファイルをそのまま残す。

```text
rasens-autofill/data/
  form_definitions/
    rasens_offer_fields.json                 # 既存・技人国
    rasens_ssw_coe_fields_v1.json            # 新規・特定技能COE
  mappings/
    rasens_offer_mapping_v2.json             # 既存・技人国
    rasens_ssw_coe_mapping_v1.json            # 新規・特定技能COE
  form_profiles.json                          # どの組合せでどの2ファイルを使うか
```

`form_profiles.json` は小さな対応表だけにする。

```text
certificate_of_eligibility + engineer_humanities_international
  -> rasens_offer_fields.json
  -> rasens_offer_mapping_v2.json

certificate_of_eligibility + specified_skilled_worker
  -> rasens_ssw_coe_fields_v1.json
  -> rasens_ssw_coe_mapping_v1.json
```

特定技能1号/2号、直接雇用/派遣、支援委託あり/なしは、プロファイルを増やさず、特定技能mapping内の条件表示にする。

### なぜmappingを分けるのか

RASENSの `item[N]` やfield IDは業務上の意味を持つIDではない。同じ番号でも、技人国画面と特定技能画面で意味が異なる箇所が確認できた。技人国mappingを特定技能画面に使うと、値が別項目へ入る危険がある。

backendは `case.application_type + case.target_status` からプロファイルを選び、組合せが未対応ならrowsを生成せず明確なエラーにする。推測で既定の技人国mappingへfallbackしてはいけない。

`application_data` には、確認用として `form_profile_id` と `form_definition_version` を返す。現在のAPIは `mapping_version` と `form_definition` だけを返しているため、実装時にはこの返却項目を小さく拡張する。Chrome拡張は引き続き完成済みのrowsを入力するだけで、profile、mapping、変換規則を解釈しない。

`rasens-autofill/data/` を設計上の正本とし、デプロイ用の `visa-app/backend/data/` は同じ内容を同期する。2か所を人が別々に編集しない。同期方法は既存の運用に合わせ、ここでは新しい保存基盤の設計までは決めない。

### 旧案件・旧データはそのまま残す

- 既存の技人国 `case_data`、golden、form definition、mappingは書き換えない。
- 新しい `specified_skilled_worker` は特定技能案件にだけ持たせる。
- 既存案件は保存済みの `application_type + target_status` で技人国profileを選ぶ。
- 対象在留資格が欠けている、または未対応の旧案件は、技人国だと推測せず自動入力を止める。

これにより、特定技能追加のために旧データを一括変換する必要はない。

## AI抽出の設計

現行の共通scopeは再利用する。

- applicant identity
- entry plan / immigration history
- employer
- employment
- review

特定技能用は、初めから4つのGemini呼出しへ分割せず、まず `specified_skilled_worker` scopeを1つだけ追加する。そのschema内部を `eligibility / contract / organization / support` に分ける。データ量や精度に問題があることを計測してから分割する。

プロンプトのレビュー観点は在留資格ごとに切り替える。現在の技人国向け「学歴・専攻と職務のつながり」「単純労働に見えないか」を、特定技能へそのまま適用しない。特定技能では、資料に明示された技能・日本語要件、契約、分野・業務区分、支援情報の抽出と、未確認事項の洗い出しを担当させる。

AIが出した値は従来どおり `field_metadata` の根拠と一緒にレビューする。法的・実務的な適合判断をAIだけで確定しない。

## 利用者の体験

### 1. 案件作成

「新規案件」で次を選ぶ。

1. 申請手続き
2. 在留資格
3. 特定技能の場合だけ1号/2号

直接雇用/派遣、支援委託の有無まで最初に強制入力しない。分かっていれば入力できるが、資料抽出後にレビュー先頭で確認できるようにする。

### 2. 書類アップロード

現在の一括DropZoneは維持する。特定技能を選んだときだけ、提出状況の確認欄を切り替える。

- 共通: 旅券、本人情報、雇用条件、所属機関情報
- 特定技能: 技能水準、日本語能力、技能実習修了、特定技能雇用契約、支援計画・登録支援機関に関する資料

これは最終的な法定書類一覧ではなく、抽出とレビューに必要な資料カテゴリである。実際の提出様式・必要書類は、実装時点の[特定技能関係の申請・届出様式一覧](https://www.moj.go.jp/isa/applications/ssw/10_00020.html)で確認する。

### 3. レビュー

静的判定で見える378個の入力系controlを一列に並べない。次の順で折りたたみ表示する。

1. 共通の本人・入国情報
2. 技能・日本語要件
3. 特定技能雇用契約
4. 所属機関の確認
5. 支援計画・登録支援機関
6. 代理人・取次者・受領方法

各セクションには「資料から抽出済み」「人の確認待ち」「不足」の件数だけを先に見せる。根拠画像を右側で確認し、値を修正する現行体験は維持する。

レビュー上部で、条件分岐に大きく影響する次の3点を確認する。

- 特定技能1号 / 2号
- 直接雇用 / 派遣
- 1号支援を自社実施 / 登録支援機関へ委託

### 4. RASENS入力

入力前に次を確認する。

- 案件のプロファイルと開いているRASENS画面が一致する
- 人確認が必要な必須項目に未確認がない
- 条件分岐後の必須項目が埋まっている

一致しなければ自動入力を止める。最終送信は引き続き人が行い、Chrome拡張は送信しない。

## 正解データと精度評価

特定技能でも、正解データは「PDFに書かれた全文」ではなく、アプリが最終的に持つべき `case_data.golden.json` とする。

```text
AI抽出の評価
  AIが出した未mergeのcase_data
  vs
  goldenのうち資料から読む項目

RASENS変換の評価
  正しいgolden case_dataから生成したrows
  vs
  期待する特定技能RASENS rows
```

人確認の宣言、取次者、受領方法、RASENSでのみ必要な値はAI抽出の分母へ入れず、既存方針の `application_only` として扱う。条件上表示されない項目も分母から外す。

最初に最低限必要な分岐fixtureは次の4種類である。

1. 特定技能1号・直接雇用・登録支援機関へ全部委託
2. 特定技能1号・直接雇用・自社支援
3. 特定技能1号・派遣
4. 特定技能2号

今回のMHTMLだけでは全分岐の表示状態を確定できないため、それぞれの保存画面を取得して台帳とmappingを検証する。実資料fixtureはrestricted test dataのままとし、Gitには入れない。

## 実装作業計画

まだ実装しない。実装時は次の順に進める。

### Phase 0: 対応範囲の確定

- 初期対応を「COE・特定技能1号・直接雇用」に絞るか決める。
- 1号/2号、直接/派遣、支援委託あり/なしのRASENS画面を保存する。
- 各分岐の表示項目と必須項目を比較する。

完了条件: 初期対応する組合せと、対象外なら止める組合せが明文化されている。

### Phase 1: フォームプロファイル

- 特定技能COEのform definitionをMHTMLから作る。
- 小さな `form_profiles.json` を追加する。
- backendで案件に合うprofileを選び、未対応profileはエラーにする。
- 既存技人国profileが同じrowsを生成する回帰テストを入れる。

完了条件: 技人国と特定技能で別の正しい台帳を選び、取り違え時に入力を止められる。

### Phase 2: データ抽出とレビュー

- `case.target_status_variant` と `specified_skilled_worker` の4群を追加する。
- 特定技能用Gemini scopeを1つ追加する。
- 項目ごとに「資料から読む / 人が確認する / 設定・計算」を割り当てる。
- レビュー画面を共通群と特定技能4群に分ける。
- 人確認項目を抽出schemaのrequiredに入れず、未記載から自動でfalseにしないテストを入れる。

完了条件: 根拠付きの抽出値と、人が確認する値を画面上で区別できる。

### Phase 3: mappingと自動入力

- 共通項目から特定技能mappingを作る。
- 次に、技能・日本語、契約、所属機関、支援の順でmappingを追加する。
- 1号/2号、派遣、支援委託の条件表示を検証する。
- Chrome拡張は原則変更せず、profile一致確認が不足する場合だけ小さく追加する。

完了条件: 対応するRASENS画面にだけ正しいrowsが入り、未対応・不一致時は何も入力しない。

### Phase 4: goldenと精度検証

- 4分岐のfixtureを作る。
- AI抽出評価とRASENS変換評価を分ける。
- 主要項目を人と別レビュアーで二重確認する。
- 不一致を extraction / golden / mapping / form profile / manual confirmation に分類する。

完了条件: 共通項目と特定技能固有項目の精度、未確認数、mappingの正しさを別々に説明できる。

### 主な変更対象

| 対象 | 予定する変更 |
|---|---|
| 案件作成UI/API | 申請手続き・在留資格・1号/2号を選べるようにする |
| Gemini schema/prompt | 共通scopeを再利用し、特定技能scopeを1つ追加する |
| レビューUI | 特定技能4群の順序、ラベル、人確認状態を追加する |
| `application_data.py` | 固定ファイル読込をprofile選択へ置き換える |
| `rasens-autofill/data/` | 特定技能COEの台帳、mapping、profile対応表を追加する |
| `visa-eval/` | 特定技能goldenと分岐fixtureを追加し、抽出と変換を別々に採点する |

Chrome拡張本体は原則変更対象にしない。RASENS画面とのprofile一致を現在のrows情報だけで確認できない場合に限り、入力前ガードを追加する。

## 初期MVPの推奨範囲

最もシンプルに始めるなら、最初は次に絞る。

- 在留資格認定証明書交付申請
- 特定技能1号
- 直接雇用
- 登録支援機関への全部委託を優先

この組合せで、共通項目、技能・日本語、契約、所属機関基本情報、支援委託先までを扱う。多数の適合性宣言は、人確認として残す。

その後、自社支援、派遣、特定技能2号、在留資格変更、在留期間更新の順に広げる。この順番なら、最初から全分岐を一つの巨大な実装へ入れずに済む。

## 今回は決めないこと

- 保存層の細かな構成
- 会社情報や登録支援機関情報を組織マスタ化する方法
- 変更申請・更新申請のfield IDとmapping
- 各特定産業分野の法的な適合判断
- RASENSの最終送信自動化

まず、`case_data / form profile / mapping / review / eval` の境界だけを決める。保存先の最適化や再利用マスタは、特定技能の実案件データを見てから検討する。

## 調査・レビュー方法

今回の設計は、役割を分けて確認した。

- フォーム差分担当: MHTMLと既存技人国form definition/mappingを比較
- アーキテクチャ担当: `case_data`、Gemini schema、application-data API、Chrome拡張の責務を確認
- UX担当: 案件作成、アップロード、レビュー、入力前確認の流れを確認
- 統合担当: 重複を除き、既存構造を壊さない最小案へ整理

制度に関する最小限の確認には、[在留資格認定証明書交付申請](https://www.moj.go.jp/isa/applications/procedures/16-1.html)、[1号特定技能外国人支援・登録支援機関について](https://www.moj.go.jp/isa/policies/ssw/supportssw.html)、[特定技能関係の申請・届出様式一覧](https://www.moj.go.jp/isa/applications/ssw/10_00020.html)を参照した。制度・様式は変更されるため、実装開始時にも再確認する。
