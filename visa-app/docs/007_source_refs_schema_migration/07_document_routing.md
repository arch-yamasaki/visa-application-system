# 07 document routing 実装

## 目的

scopeごとに必要な書類だけをGeminiへ渡し、遅延、timeout、誤抽出、source_refずれを減らす。

## 前提

document routing は scope分割が安定してから実装する。

最初から強いroutingを入れると、必要な書類をscopeに渡し忘れて抽出漏れが起きる。まず scope の owner field と merge 境界を固める。

## 方針

- document role だけに依存しない。
- ファイル名、拡張子、抽出済みテキスト、アップロード時の role を使う。
- 曖昧な書類は複数 scope に渡す。
- review scope は基本的に全書類を見る。
- manifest と実 contents は必ず一致させる。

## 調査対象ファイル

| ファイル | 現状 |
|---|---|
| `backend/extractors/document_preprocessor.py` | 拡張子別に PDF / text / image へ振り分ける |
| `backend/extractors/document_models.py` | `LoadedDocument`, `PreparedDocuments` の最小構造 |
| `backend/extractors/gemini_pipeline.py` | 全scopeに同じ `PreparedDocuments` から作った contents を渡している |
| `backend/extractors/prompt_template.py` | scope document role の枠はあるが、現状は実質未使用 |
| `backend/extractors/gemini.py` | scoped extraction を実行するが、routing結果は受け取っていない |

## 想定routing

| scope | 渡す書類の例 |
|---|---|
| `applicant_identity` | passport, resume, intake sheet |
| `entry_plan` | intake sheet, offer letter, company location documents |
| `immigration_history` | intake sheet, questionnaire |
| `education` | diploma, transcript, resume |
| `employment_history` | resume, CV |
| `employer` | company documents, offer letter, intake sheet |
| `employment` | offer letter, employment terms |
| `review` | 全書類 |

## 作業計画

1. `PreparedDocuments` に document単位の index を追加する設計を決める。
2. `prepare_documents()` で `document_id` から ext / role / text / bytes を引けるようにする。
3. deterministic routing を先に入れる。
4. 曖昧なものだけ Gemini 分類に回す。
5. `contents_by_scope` と `documents_by_scope` を同じ routing 結果から作る。
6. `scope_input_built` log に routing理由を出す。

## routing の段階

| 段階 | 内容 | 方針 |
|---|---|---|
| 1 | scope分割済み・routingなし | 全scopeに全書類を渡す |
| 2 | deterministic routing | 明らかな書類だけscopeへ寄せる |
| 3 | conservative routing | 曖昧な書類は複数scopeに渡す |
| 4 | Gemini classification | 曖昧な document だけ軽量分類する |

初期は段階2まででよい。強く絞るより、渡し漏れを避ける。

## 受け入れ条件

- 各scopeに渡した manifest と実 contents が一致する。
- 曖昧な書類は落とさず複数scopeに渡せる。
- routingを無効化して全書類投入に戻せる。
- `scope_input_built` で、なぜその書類が渡されたか追える。

## 注意点

強いroutingは精度を上げる一方で、必要書類の渡し漏れが抽出漏れにつながる。MVPでは保守的に、曖昧なら渡す。

## 削除・整理候補

- 実際には使われていない document role filter の説明
- routing済みに見えるが全scopeに全書類を渡している古い記述
- ファイル名 heuristic だけで分類する前提の説明
