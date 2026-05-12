# AIエージェント実行基盤の調査

## 位置づけ

この文書は、Codex 固有ではない AI エージェント実行基盤の調査メモ。対象は、LLM agent がファイル操作、コード実行、OCR、PDF処理、ブラウザ操作、外部ツール呼び出しを行うための sandbox / job / workflow 基盤。

2026-05-05 時点の公式ドキュメント・一次情報を前提にしている。製品仕様は変わるため、採用前に再確認する。

## この案件で必要な性質

在留資格申請支援では、申請人情報、旅券、在留カード、学歴、給与、雇用契約などの個人情報を扱う。したがって、単に「agent が動く」だけでは足りない。

必要な性質:

- セッション単位、案件単位、テナント単位で workspace を分離できる
- 任意コード実行や外部コマンド実行を sandbox 化できる
- 実行ログ、入力ファイル、出力ファイルを監査可能に保存できる
- retry、timeout、cancel、再実行、冪等性を管理できる
- secrets を workspace / prompt / log に混ぜない
- PII を含む artifact の保存先、保持期間、削除経路を決められる
- 将来、ブラウザ操作や申請入力支援に広げられる

## まず分けるべきレイヤー

AIエージェント基盤は、1つの製品だけで完結させようとすると判断がぶれる。次の4層に分ける。

```text
1. App/API layer
   - ユーザー認証、案件管理、ジョブ作成、状態表示

2. Durable orchestration layer
   - 長時間処理、retry、cancel、human review、再実行

3. Execution / sandbox layer
   - コード実行、ファイル操作、OCR、ブラウザ、ツール実行

4. Storage / audit layer
   - 入力資料、workspace snapshot、event log、成果物、削除
```

この案件の初期MVPでは、`1` と `4` は GCP 側に寄せる。`2` と `3` をどこまで managed service に任せるかが選択肢になる。

## 自前GCP寄りの選択肢

| 候補 | 位置づけ | 良い点 | 弱い点 | この案件での使い方 |
| --- | --- | --- | --- | --- |
| Cloud Run Service | API / UI backend | フルマネージド、HTTP API に強い、認証・IAM・VPC と統合しやすい | request timeout があり、長時間 agent 実行本体には弱い | 受付 API、状態参照、SSE、job 起動 |
| Cloud Run Jobs | 非同期 worker | バッチ実行向き。task timeout は最大 168 時間。実行時 override が使える | filesystem は永続でない。セッション workspace は外部保存が必要 | OCR、抽出、整合性チェック、短中期 agent worker |
| GKE Autopilot | 本番 sandbox / worker 基盤 | Kubernetes の制御力を残しつつノード運用を GKE に任せられる。VPC、IAM、永続 volume、policy と相性がよい | Kubernetes 設計・運用の複雑さは残る | PII 要件が強い本番 runner、長寿命 workspace |
| GKE Sandbox / gVisor | Pod sandbox 強化 | コンテナ境界より強い syscall レベルの隔離を追加できる | 全 workload と相性がよいわけではない。性能・互換性検証が必要 | 任意コード実行系の worker に限定適用 |
| Cloud Batch | 大量バッチ | VM/コンテナの大量並列処理、再処理、スケジューリングに向く | session / workspace API は自前 | 大量OCR、再抽出、過去案件再評価 |
| Cloud Build private pools | build/test 隔離 | VPC 内 private pool、public IP 無効化など CI 的隔離がしやすい | agent runtime ではなく build 基盤 | container build、テスト、policy check |
| Kubernetes Jobs | 汎用 worker primitive | backoff、parallelism、completion 管理が標準化されている | cluster 運用が必要 | GKE 採用時の agent run 単位 |

GCP に寄せるなら、MVP は `Cloud Run Service + Cloud Run Jobs + GCS + Firestore/Cloud SQL` が一番軽い。PII やネットワーク分離が重くなったら `GKE Autopilot + GKE Sandbox` に移す。

## Managed sandbox / agent 実行サービス

| 候補 | 位置づけ | 良い点 | 弱い点 | この案件での評価 |
| --- | --- | --- | --- | --- |
| Modal Sandboxes | Python/コンテナ実行基盤 | custom image、volumes、filesystem snapshots、sandbox networking。OCR/PDF/抽出系に向く | GCP 外部サービスになる。PII のデータ経路・契約確認が必要 | PoC / 非本番 / 匿名化データなら強い |
| E2B | AI agent 用 sandbox | agent 向け Linux sandbox、persistence、desktop / browser / computer-use 系に強い。BYOC もある | MVP の書類処理にはやや重い。PII ではデータ所在確認が必要 | 将来のブラウザ操作・GUI 自動化候補 |
| Daytona | workspace-first sandbox | snapshots、volumes、Git、PTY、self-host / customer managed compute がある | 導入は Modal/E2B より重め | 自社管理 workspace 基盤が欲しくなった段階で再評価 |
| Cloudflare Sandboxes | Workers 連携 sandbox | TypeScript / Workers から sandbox を扱いやすい。storage mount や secrets 代理注入の設計がある | Python/OCR 中心なら GCP との距離が出る | Workers 前提のプロダクトなら有力 |
| CodeSandbox SDK | coding agent / dev env | microVM、fork/restore、browser 接続、collaboration に強い | 書類処理MVPには方向がやや違う | コード生成・開発環境系なら候補 |
| Fly Machines | 低レベル VM primitive | VM lifecycle API、suspend、volumes がある | sandbox 製品ではない。監査・分離・job 制御は自前 | 特殊要件の escape hatch |
| OpenHands runtime | OSS agent runner | Docker sandbox 等の実装参考になる | managed 実行基盤ではない | 自前 runner を作る時の参考 |

この案件だけを見ると、最速で外部 sandbox を試すなら `Modal Sandboxes`、将来のブラウザ / desktop 操作まで見据えるなら `E2B`、自社管理を強めるなら `Daytona` が候補になる。

ただし、本番の申請人データを外部 sandbox に投入する判断は、技術選定だけではなく、契約、データ保護、ログ保持、削除、国外移転、委託先管理の確認が必要。

## Durable orchestration

AI agent は単発 API 呼び出しではなく、途中で失敗し、ユーザー確認を挟み、再実行される。実行基盤とは別に durable orchestration を考える。

候補:

- Cloud Tasks
  - HTTP task queue、retry、rate limit に向く。
  - 単純な非同期ジョブ起動には十分。
- Workflows
  - GCP サービス同士の手順実行に向く。
  - OCR -> 抽出 -> チェック -> 通知のような固定フローに合う。
- Temporal
  - 長時間 workflow、human-in-the-loop、retry、activity history に強い。
  - 運用は増えるが、複雑な agent workflow では有力。
- LangGraph
  - LLM agent の state graph、checkpoint、human review に寄せた実装がしやすい。
  - 実行 sandbox そのものではない。worker / storage と組み合わせる。

初期は Cloud Tasks / Workflows でよい。人のレビュー、再開、分岐、長い案件処理が増えたら Temporal または LangGraph を検討する。

## 推奨アーキテクチャ

### MVP

```text
Frontend
  |
  v
Cloud Run Service
  - 認証
  - 案件API
  - job作成
  - 状態参照
  |
  v
Cloud Tasks or direct Cloud Run Jobs execution
  |
  v
Cloud Run Jobs
  - OCR
  - 項目抽出
  - 不足確認
  - 整合性チェック
  |
  v
GCS / Firestore / Cloud SQL
  - raw資料
  - case_data
  - event log
  - generated output
```

この段階では、任意コード実行を広げない。実行 image を固定し、許可された処理だけを worker に入れる。

### Sandbox 強化フェーズ

```text
Cloud Run Service
  |
  v
Durable orchestrator
  |
  v
GKE Autopilot
  - tenant/sessionごとの Job/Pod
  - gVisor sandbox
  - NetworkPolicy
  - Secret Manager / Workload Identity
  |
  v
GCS / DB / audit log
```

本番で任意コマンド、ブラウザ操作、外部ライブラリ実行を許すなら、GKE 側に寄せる。Cloud Run Jobs は簡単だが、細かい network policy、workspace volume、長寿命 session、隔離強化では GKE の方が設計しやすい。

### 外部 sandbox 利用フェーズ

```text
Cloud Run Service
  |
  v
Sandbox Broker
  |
  +-- Modal: Python/OCR/抽出系の隔離実行
  +-- E2B: browser/desktop/computer-use 系
  +-- Daytona: self-host/workspace-first 系
```

外部 sandbox は、匿名化データ、検証環境、非本番用途から始める。本番投入するなら、データ処理契約、保存場所、削除保証、ログ、暗号化、BYOC 可否を確認する。

## 現時点の結論

この案件の初期MVPでは、AI agent 基盤を先に大きく作らない方がよい。

まずは:

- `Cloud Run Service`: API / UI backend
- `Cloud Run Jobs`: 非同期処理 worker
- `GCS`: raw file / generated artifact
- `Firestore or Cloud SQL`: session / case / run metadata
- `Cloud Tasks`: job 起動と retry

で十分。

次に、任意コード実行やブラウザ操作が必要になったら:

- GCP 内に閉じたい: `GKE Autopilot + GKE Sandbox`
- Python sandbox を速く試したい: `Modal Sandboxes`
- GUI / browser / computer-use を試したい: `E2B`
- 自前 workspace API が欲しい: `Daytona`

の順で検討する。

個人情報を扱う本番では、最終的には `GCP 内の制御面 + 必要最小限の sandbox 実行 + 監査ログ` を軸にするのが堅い。

## 参考リンク

GCP:

- Cloud Run Jobs: https://cloud.google.com/run/docs/create-jobs
- Cloud Run task timeout: https://cloud.google.com/run/docs/configuring/task-timeout
- Cloud Run request timeout: https://cloud.google.com/run/docs/configuring/request-timeout
- GKE Autopilot overview: https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview
- GKE Sandbox / sandbox Pods: https://cloud.google.com/kubernetes-engine/docs/concepts/sandbox-pods
- Cloud Batch: https://cloud.google.com/batch/docs/get-started
- Cloud Build private pools: https://cloud.google.com/build/docs/private-pools/private-pools-overview
- Cloud Tasks retry: https://cloud.google.com/tasks/docs/configuring-queues
- Kubernetes Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/

Managed sandbox:

- Modal Sandboxes: https://modal.com/docs/guide/sandboxes
- Modal sandbox networking: https://modal.com/docs/guide/sandbox-networking
- E2B docs: https://e2b.dev/docs
- E2B persistence: https://e2b.dev/docs/sandbox/persistence
- E2B computer use: https://e2b.dev/docs/use-cases/computer-use
- Daytona sandboxes: https://www.daytona.io/docs/en/sandboxes/
- Daytona snapshots: https://www.daytona.io/docs/en/snapshots/
- Cloudflare Sandboxes: https://developers.cloudflare.com/sandbox/
- CodeSandbox SDK: https://codesandbox.io/sdk
- Fly Machines: https://fly.io/docs/machines/
- OpenHands sandboxes: https://docs.openhands.dev/openhands/usage/sandboxes/overview

Workflow / agent state:

- Temporal docs: https://docs.temporal.io/
- LangGraph durable execution: https://docs.langchain.com/oss/javascript/langgraph/durable-execution
