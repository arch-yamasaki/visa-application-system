# Codex リモート実行基盤の全体方針

## 位置づけ

このディレクトリは、フロントサービスから別サーバー上の Codex に作業を依頼し、結果をフロントへ返すための設計メモを置く場所。

重要な前提として、ここで扱う `Codex App Server`、`Codex SDK`、`codex exec --json` は、いずれも **Codex CLI / SDK / App Server を起動した自社側サーバー上で動く**。OpenAI 側で動くのはモデル推論 API であり、ファイル読み書き、コマンド実行、workspace 操作は自社 worker の filesystem / shell 上で行われる。

この点は、Codex Cloud や ChatGPT 上の Codex タスクとは分けて考える。

## 目的

- フロントサービスから、別サーバー上の Codex worker に作業依頼できるようにする。
- セッション分離とセッション継続を設計に入れる。
- Cloud Run を使う場合の制約を踏まえ、同期 API と長時間実行を分ける。
- 案件データ、個人情報、API key、作業ログの保存境界を明確にする。

## 基本構成

```text
Browser / Frontend
  |
  | HTTPS / SSE / WebSocket
  v
自社 Backend / Gateway
  |
  | session 作成、job 起動、event 配信、権限制御
  v
Codex Worker
  |
  | codex app-server / @openai/codex-sdk / codex exec
  v
session ごとの workspace / git worktree / container
```

Codex worker は、Cloud Run Jobs、GKE、VM、専用 runner のいずれでもよい。ただし Cloud Run Service に長時間の Codex 実行を直接ぶら下げると、HTTP timeout、再接続、同一インスタンス保証、filesystem 永続化の扱いが重くなる。

## 3つの手段

| 手段 | Codex が動く場所 | 向いている用途 | 強み | 弱み |
| --- | --- | --- | --- | --- |
| 1. Codex App Server | `codex app-server` を起動した自社 worker | IDE 風 UI、進捗 stream、途中指示、割り込み、承認 UI | `thread/start`、`thread/resume`、`thread/fork`、`turn/steer`、`turn/interrupt` があり、セッション操作が一番細かい | JSON-RPC client 実装が必要。WebSocket transport は experimental / unsupported なので公開運用は注意 |
| 2. Codex SDK | SDK を実行する自社 backend / worker | 自社アプリへの組み込み、MVP の session 継続 | `startThread()`、同一 thread の `run()`、`resumeThread(threadId)` が扱いやすい | App Server ほど低レベルのイベント制御・承認 UI は作りにくい |
| 3. `codex exec --json` | `codex exec` コマンドを実行した自社 worker | Cloud Run Jobs、CI、ジョブキュー、単発または段階的な非対話実行 | 実装が単純。JSONL で進捗イベントを保存できる。`codex exec resume <SESSION_ID>` で継続も可能 | live attach、途中 steer、リッチな承認 UI には弱い。workspace と `CODEX_HOME` の永続化を自前で設計する必要がある |

## Cloud Run を使う場合の整理

### Cloud Run Service

Cloud Run Service は、受付 API、状態参照、SSE / WebSocket の短い stream、job 起動に向く。WebSocket は使えるが HTTP request として request timeout の対象で、最大 60 分まで。再接続と状態同期が前提になる。

長時間の Codex 実行プロセスを Service の request 中に保持する設計は避ける。

### Cloud Run Jobs

Cloud Run Jobs は、HTTP サーバーではなく、終了するバッチ処理向け。task timeout は最大 168 時間まで設定できるため、`codex exec --json` の worker と相性がよい。

ただし Cloud Run の filesystem は永続ストレージではない。セッション継続をするなら、少なくとも以下を外部保存・復元する。

- workspace snapshot
- `CODEX_HOME` 配下の session state
- Codex session id
- JSONL event log
- 最終 message / diff / artifact

## セッション分離と継続

アプリ側の session と Codex 側の thread/session を分けて管理する。

```text
app_session_id
user_id / tenant_id
worker_type
workspace_ref
codex_thread_id or codex_session_id
codex_home_ref
active_run_id
status
event_log_ref
created_at / updated_at
```

分離の基本は、session ごとに workspace と Codex state を分けること。

```text
/work/sessions/{app_session_id}/repo
/work/sessions/{app_session_id}/codex-home
```

Cloud Run Jobs では local path は毎回消える前提なので、GCS などから restore してから実行し、完了後に checkpoint を保存する。

## 推奨方針

MVP で Cloud Run を使うなら、まずは `3. codex exec --json + Cloud Run Jobs` が実装しやすい。

理由:

- Cloud Run Jobs と非対話 CLI 実行の相性がよい。
- `--json` の JSONL を保存すれば、フロントに進捗を返せる。
- `codex exec resume <SESSION_ID>` により、最低限のセッション継続ができる。
- App Server の WebSocket / JSON-RPC client 実装を後回しにできる。

一方で、将来「作業中の途中指示」「割り込み」「承認 UI」「thread fork」「IDE 風のライブ表示」が重要になったら、`2. SDK` または `1. App Server` に寄せる。

段階としては次が自然。

1. `codex exec --json + Cloud Run Jobs` で job 型 MVP。
2. `Codex SDK` で thread resume を backend から扱いやすくする。
3. `Codex App Server` でリッチな session UI / steer / interrupt / approval を実装する。

## 方針3の詳細

`codex exec --json` を Cloud Run Jobs で動かす場合の詳細は次の文書に分ける。

- [Option 3 詳細設計: codex exec --json on Cloud Run Jobs](option3_codex_exec_json_cloud_run_jobs.md)

## 注意点

- Codex worker をブラウザから直接叩かない。必ず自社 Backend / Gateway を挟む。
- App Server の WebSocket transport を非 loopback に公開しない。使う場合も auth、private network、SSH tunnel、Gateway を前提にする。
- 案件データを扱う場合、workspace snapshot と JSONL event log も個人情報資産として扱う。
- `danger-full-access` や sandbox bypass は、使うとしても完全に隔離された検証環境だけに限定する。
- セッション継続では、Codex の session id だけ保存しても足りない。workspace と Codex state の復元が必要。

## 参考リンク

- OpenAI Codex non-interactive mode: https://developers.openai.com/codex/noninteractive
- OpenAI Codex SDK: https://developers.openai.com/codex/sdk
- OpenAI Codex App Server: https://developers.openai.com/codex/app-server
- OpenAI Codex CLI reference: https://developers.openai.com/codex/cli/reference
- OpenAI Codex auth: https://developers.openai.com/codex/auth
- Cloud Run WebSockets: https://docs.cloud.google.com/run/docs/triggering/websockets
- Cloud Run request timeout: https://docs.cloud.google.com/run/docs/configuring/request-timeout
- Cloud Run Jobs: https://cloud.google.com/run/docs/create-jobs
- Cloud Run Jobs execution overrides: https://cloud.google.com/run/docs/execute/jobs
- Cloud Run container runtime contract: https://cloud.google.com/run/docs/container-contract
