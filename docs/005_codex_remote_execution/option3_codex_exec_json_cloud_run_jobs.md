# Option 3 詳細設計: `codex exec --json` on Cloud Run Jobs

## 1. 対象と設計方針

この案は、HTTP を受ける常駐コンポーネントを `Cloud Run Service`、実際に `codex exec --json` を走らせる実行面を `Cloud Run Jobs` に分ける。ジョブは 1 実行 = 1 Codex run とし、会話の継続は `codex exec resume` を使って次のジョブで再開する。

前提:

- `codex exec --json` は非対話実行で JSONL を標準出力に流せる。`codex exec resume [SESSION_ID]` で既存セッション再開ができる。`--ephemeral` はセッションをディスクに残さないため、この案では使わない。
- Codex CLI の設定とセッション状態は `CODEX_HOME` 配下を使う。API key 認証は `codex exec` では `CODEX_API_KEY` を使えるため、Cloud Run Jobs では Secret Manager から環境変数またはファイルで注入する。
- Cloud Run Jobs はリクエスト待受をしないバッチ向けで、実行履歴は Cloud Run 側では直近 1,000 件または 7 日の短い保持しかない。したがって永続的な正本は GCS + DB に置く。

この設計では、Cloud Run のジョブ実行履歴は運用補助でしか使わず、以下を自前保持の正本にする。

- セッション/実行メタデータ: Firestore
- ワークスペース、`CODEX_HOME` スナップショット、JSONL 生イベント、最終成果物: GCS

参考:

- OpenAI Codex non-interactive: https://developers.openai.com/codex/noninteractive
- OpenAI Codex auth: https://developers.openai.com/codex/auth
- OpenAI Codex config: https://developers.openai.com/codex/config
- Cloud Run Jobs 実行: https://cloud.google.com/run/docs/execute/jobs
- Cloud Run Jobs 作成/再試行/タイムアウト: https://cloud.google.com/run/docs/create-jobs

## 2. 全体構成

構成要素:

- `codex-orchestrator` (`Cloud Run Service`)
  - セッション作成、resume 要求、状態照会、cancel 要求の API
  - Firestore のロック取得、GCS 入出力 URI 発行
  - Cloud Run Admin API で `codex-runner-job` を execution override 付きで起動
- `codex-runner-job` (`Cloud Run Jobs`)
  - 1 execution で 1 セッションの 1 run だけ処理
  - GCS から workspace / `CODEX_HOME` を restore
  - Secret Manager から API key を受けて認証 bootstrap
  - `codex exec --json` または `codex exec --json ... resume ...` を起動
  - JSONL を chunk 化して GCS へ保存、要約状態だけ Firestore 更新
  - 終了時に workspace / `CODEX_HOME` を checkpoint
- Firestore
  - セッション正本、run 正本、lease、checkpoint ポインタ
- GCS
  - immutable な raw artifact 保管庫
- Secret Manager
  - OpenAI API key
- 任意: Cloud Tasks
  - API から Job 起動までの非同期化と API 再試行

この分離により、Service は短時間 HTTP、Jobs は長時間バッチに責務を固定できる。

## 3. セッション分離

### 3.1 論理分離

1 セッションごとに `session_id` を払い出し、すべての永続データをその prefix に閉じ込める。

- Firestore key: `sessions/{session_id}`
- GCS prefix: `gs://{bucket}/sessions/{session_id}/...`

1 run ごとに `run_id` を払い出し、セッション配下の immutable な実行単位にする。

- Firestore key: `sessions/{session_id}/runs/{run_id}`
- GCS prefix: `sessions/{session_id}/runs/{run_id}/...`

### 3.2 実行分離

Cloud Run Job は以下で固定する。

- task count: 1
- parallelism: 1
- 1 execution が 1 session/run のみ担当

同一セッションに対する並列 run は禁止する。`codex-orchestrator` は Firestore transaction で `active_run_id` lease を取得し、既存 lease が生きている間は `409 Conflict` を返す。

### 3.3 lease モデル

`sessions/{session_id}` に以下を持つ。

```json
{
  "state": "running",
  "active_run_id": "run_20260505_000123",
  "lease_expires_at": "2026-05-05T12:34:56Z",
  "heartbeat_at": "2026-05-05T12:30:01Z"
}
```

ルール:

- Job は 30-60 秒ごとに `heartbeat_at` を更新
- Service は `lease_expires_at` を超えた run を stale と判定
- stale でも自動 resume はしない
- stale 時は `interrupted` に遷移させ、人または明示 API から resume する

理由は、Codex が既に外部副作用を伴うコマンドを実行した後に自動再試行すると二重実行になるため。

## 4. セッション継続 / resume

### 4.1 resume の基本

初回 run:

```bash
CODEX_HOME=/codex-state/home \
CODEX_API_KEY="$OPENAI_API_KEY" \
codex exec --json \
  --sandbox workspace-write \
  --ask-for-approval never \
  -C /workspace/current \
  "$PROMPT"
```

継続 run:

```bash
CODEX_HOME=/codex-state/home \
CODEX_API_KEY="$OPENAI_API_KEY" \
codex exec --json \
  --sandbox workspace-write \
  --ask-for-approval never \
  -C /workspace/current \
  resume "$CODEX_SESSION_ID" "$PROMPT"
```

resume の成立条件:

- 前回 run の `CODEX_HOME` checkpoint が GCS に正常保存済み
- `codex_session_id` が Firestore に記録済み
- restore 後の workspace path を毎回同じにする

`codex exec resume --last` は cwd 依存の選別が入るため、Job では必ず明示 `SESSION_ID` を使う。

### 4.2 `codex_session_id` の採番と保持

Codex のセッション ID は runner が JSONL の初期イベントから取得して Firestore に書く。取得前に失敗した run は resumable ではない。

`sessions/{session_id}`:

```json
{
  "codex_session_id": "3f3c0d7d-....",
  "last_resumable_run_id": "run_0007"
}
```

### 4.3 resume 要求フロー

1. クライアントが `POST /sessions/{session_id}:resume`
2. Service が `active_run_id` 不在を確認し、新しい `run_id` を採番
3. `last_resumable_run_id` から workspace / `CODEX_HOME` checkpoint URI を取得
4. prompt を GCS に保存
5. Job を `MODE=resume` で起動
6. Job が restore 後に `codex exec --json ... resume "$codex_session_id" "$prompt"`
7. 正常終了したら checkpoint head を新 run に更新

### 4.4 中断時の扱い

Cloud Run Job は対話型の「その場で attach して続ける」仕組みを持たないため、継続は常に次の Job execution で行う。したがってこの案の resume は「checkpoint-based resume」であり、「live process continuation」ではない。

## 5. `CODEX_HOME` 永続化

### 5.1 なぜ必要か

Codex CLI の resume は `CODEX_HOME` 配下の session state に依存する。単に最終メッセージだけ保存しても `codex exec resume` はできない。

### 5.2 保存方針

Job 起動時:

- GCS の最新 `codex_home` archive を `/codex-state/home` に restore
- 初回 run は seed config だけを展開

Job 終了時:

- `/codex-state/home` を tar.zst 化して GCS へ upload
- ただし `auth.json` は archive から除外

保存対象:

- `config.toml`
- session state 一式
- MCP/CLI が resume に使う補助状態

保存しないもの:

- `auth.json`
- 一時ログ
- キャッシュ類のうち再生成可能でサイズだけ大きいもの

### 5.3 認証 bootstrap

認証は Secret Manager の API key を Job 実行時に注入する。認証情報そのものは checkpoint に残さない。

推奨手順:

1. Secret Manager から API key を環境変数または file mount で受け取る
2. runner entrypoint で `OPENAI_API_KEY="$(cat /var/run/secrets/openai_api_key)"` のように読み込む
3. `CODEX_API_KEY="$OPENAI_API_KEY" codex exec ...` として run 実行
4. checkpoint 前に `/codex-state/home/auth.json` が存在すれば削除する

こうすると、resume に必要な session state は残しつつ、漏えい影響の大きい credential file は永続化しない。

参考:

- https://developers.openai.com/codex/auth
- https://developers.openai.com/codex/config
- Cloud Run secrets: https://cloud.google.com/run/docs/configuring/services/secrets

## 6. workspace 永続化

### 6.1 基本方針

workspace は GCS を正本、Job ローカルを作業コピーにする。Codex は大量の小さいファイル操作を行うため、workspace を直接 GCS FUSE mount で実行しない。

理由:

- Cloud Storage FUSE mount は起動時処理が長いと instance start failure になり得る
- Git repo とエディタ系ワークロードはローカルファイルシステムの方が安定する

### 6.2 Job 内レイアウト

- `/workspace/current`: 復元された作業コピー
- `/workspace/out`: 最終成果物、中間 tar 作成用
- `/codex-state/home`: `CODEX_HOME`

Cloud Run の root writable filesystem は in-memory 扱いなので、workspace は `emptyDir` volume を `medium=DISK` で mount する。

参考:

- Cloud Run container contract: https://cloud.google.com/run/docs/container-contract
- Volume `emptyDir.medium`: https://cloud.google.com/run/docs/reference/rest/v2/Volume

### 6.3 checkpoint 形式

MVP では差分ではなく full snapshot を標準にする。

- `workspace/base.tar.zst`
- `workspace/checkpoints/run-0001.tar.zst`
- `workspace/checkpoints/run-0002.tar.zst`

Firestore の session doc が「最新 head」を指す。

```json
{
  "workspace_head": {
    "run_id": "run_0002",
    "gcs_uri": "gs://.../workspace/checkpoints/run-0002.tar.zst",
    "sha256": "..."
  }
}
```

理由:

- resume 時に単一 archive を restore できる
- 差分チェーン破損時の復元失敗を避けやすい

将来最適化:

- Git repo 前提なら patch + object cache
- 大きい案件では content-addressed chunking

### 6.4 初回投入

初回 session 作成時に Service が以下どちらかを受け付ける。

- upload 済み tarball の GCS URI
- Git ref から作った workspace tarball

どちらでも Job への入力は `workspace_input_uri` で統一する。

## 7. GCS / Firestore スキーマ

### 7.1 GCS オブジェクト配置

```text
gs://{bucket}/sessions/{session_id}/
  session.json
  prompts/
    run-{run_id}.txt
  workspace/
    base.tar.zst
    checkpoints/
      run-{run_id}.tar.zst
  codex_home/
    checkpoints/
      run-{run_id}.tar.zst
  runs/{run_id}/
    request.json
    stdout/
      parts/00000001.jsonl
      parts/00000002.jsonl
      manifest.json
    stderr.txt
    last_message.txt
    summary.json
```

設計ルール:

- raw event は immutable
- `latest.jsonl` のような append 更新はしない
- run ごとに chunk file を閉じて upload する
- 最新 head は Firestore のポインタで表す

### 7.2 Firestore スキーマ

`sessions/{session_id}`

```json
{
  "tenant_id": "tenant_a",
  "state": "idle",
  "codex_session_id": "uuid-or-null",
  "active_run_id": null,
  "last_resumable_run_id": "run_0002",
  "workspace_head_run_id": "run_0002",
  "workspace_head_gcs_uri": "gs://.../workspace/checkpoints/run-0002.tar.zst",
  "codex_home_head_run_id": "run_0002",
  "codex_home_head_gcs_uri": "gs://.../codex_home/checkpoints/run-0002.tar.zst",
  "heartbeat_at": null,
  "lease_expires_at": null,
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

`sessions/{session_id}/runs/{run_id}`

```json
{
  "mode": "exec",
  "status": "running",
  "attempt": 1,
  "prompt_gcs_uri": "gs://.../prompts/run-run_0003.txt",
  "workspace_input_gcs_uri": "gs://.../workspace/checkpoints/run-0002.tar.zst",
  "workspace_output_gcs_uri": null,
  "codex_home_input_gcs_uri": "gs://.../codex_home/checkpoints/run-0002.tar.zst",
  "codex_home_output_gcs_uri": null,
  "cloud_run_execution_name": "projects/.../jobs/.../executions/...",
  "cloud_run_task_index": 0,
  "event_manifest_gcs_uri": "gs://.../runs/run_0003/stdout/manifest.json",
  "event_count": 0,
  "last_event_seq": 0,
  "final_message_gcs_uri": null,
  "codex_session_id": null,
  "exit_code": null,
  "error_code": null,
  "error_summary": null,
  "started_at": "timestamp",
  "finished_at": null,
  "heartbeat_at": "timestamp"
}
```

理由:

- Firestore は session/run の親子構造と部分更新に向く
- raw event 全件を DB に入れず、検索用メタデータだけ持てる

参考:

- Firestore data model: https://cloud.google.com/firestore/native/docs/data-model

## 8. Cloud Run Service + Jobs フロー

### 8.1 新規 session

1. クライアントが `POST /sessions`
2. Service が `session_id` と `run_id` を採番
3. prompt / request manifest / 初期 workspace tarball URI を GCS に確定
4. Firestore に `sessions/{session_id}` と `runs/{run_id}` を `queued` で作成
5. Service が Cloud Run Job execution を override 付きで起動
6. Job が restore -> login bootstrap -> `codex exec --json`
7. Job が chunked JSONL を GCS へ保存しながら heartbeat
8. Job 完了後に workspace / `CODEX_HOME` checkpoint を upload
9. Job が Firestore の run/session head を更新して lease 解放

### 8.2 resume

1. クライアントが `POST /sessions/{session_id}:resume`
2. Service が `last_resumable_run_id` を参照
3. 新 run を `queued` で作成
4. Job が前回 checkpoint を restore
5. `codex exec --json ... resume "$codex_session_id" "$prompt"`
6. 完了後に新 head へ入れ替え

### 8.3 実行パラメータの渡し方

Cloud Run Job の固定 image は 1 つにし、run ごとの差分は execution override で environment variables / args として渡す。

例:

```text
SESSION_ID=session_01
RUN_ID=run_0003
MODE=resume
PROMPT_GCS_URI=gs://.../prompts/run-run_0003.txt
WORKSPACE_INPUT_GCS_URI=gs://.../workspace/checkpoints/run-0002.tar.zst
CODEX_HOME_INPUT_GCS_URI=gs://.../codex_home/checkpoints/run-0002.tar.zst
FIRESTORE_DOCUMENT_PATH=sessions/session_01/runs/run_0003
```

参考:

- Cloud Run Jobs execute overrides: https://cloud.google.com/run/docs/execute/jobs

## 9. event JSONL handling

### 9.1 取り扱い原則

`codex exec --json` の stdout をそのまま raw event 正本にする。解析用の要約は runner が別途 Firestore に反映する。

原則:

- raw JSONL は改変しない
- 1 run = 1 event stream
- セッション横断の巨大 1 ファイルは作らない

### 9.2 chunking

GCS は append ログ用途に向かないため、runner はローカルで行単位に受けながら 1-5 MB または 100-500 行ごとに chunk を閉じて upload する。

例:

```text
runs/run_0003/stdout/parts/00000001.jsonl
runs/run_0003/stdout/parts/00000002.jsonl
runs/run_0003/stdout/manifest.json
```

`manifest.json`:

```json
{
  "run_id": "run_0003",
  "chunk_count": 2,
  "event_count": 184,
  "first_seq": 1,
  "last_seq": 184
}
```

### 9.3 Firestore へ反映する派生情報

全イベントは DB に入れない。以下だけ反映する。

- `event_count`
- `last_event_seq`
- `codex_session_id`
- 現在フェーズ (`booting`, `running`, `checkpointing`)
- 最後の agent message 要約
- 失敗原因の短い summary

### 9.4 最終メッセージ

`--output-last-message` を併用して最終メッセージを別 file に切り出す。

```bash
codex exec --json --output-last-message /workspace/out/last_message.txt ...
```

これにより UI は JSONL 全読込なしで結果サマリを取得できる。

参考:

- https://developers.openai.com/codex/noninteractive
- Cloud Storage consistency: https://cloud.google.com/storage/docs/consistency

## 10. retries

### 10.1 基本方針

Cloud Run Job の task-level retry は `0` を推奨する。自動再試行が同じ run を再実行すると、Codex が既に行った編集や外部副作用を二重化し得るため。

代わりに retry は phase ごとに分ける。

- Service/API phase
  - idempotency key 付きで再試行可
  - Cloud Tasks で exponential backoff 可
- Job setup phase
  - GCS download、Firestore read、secret read は内部再試行可
- Codex execution phase
  - 自動再試行しない
  - 失敗時は `interrupted` か `failed`
- Checkpoint upload phase
  - object upload と Firestore final update は再試行可

### 10.2 失敗分類

- `setup_failed`
  - `codex exec` 起動前失敗
  - 同じ prompt で fresh rerun 可
- `interrupted`
  - `codex exec` 開始後に Job crash / timeout
  - 自動 rerun しない
  - 明示 resume が必要
- `checkpoint_failed`
  - Codex 実行後に upload 失敗
  - run は要人手確認

### 10.3 timeout

run ごとに想定上限を設け、Cloud Run Job timeout をそれに合わせる。timeout 超過は `interrupted` として扱い、最後に成功した checkpoint から resume する。

参考:

- Cloud Run Jobs retries / timeout: https://cloud.google.com/run/docs/create-jobs

## 11. セキュリティ / sandboxing

### 11.1 Cloud Run 側

- `codex-orchestrator` は公開しない。可能なら ingress を internal にする
- Service と Job は別 service account
- Job service account には最小権限だけ付与
  - GCS 対象 bucket の object read/write
  - Firestore read/write
  - Secret Manager access
  - Logging write
- bucket は uniform bucket-level access、有効期限付き保持、監査ログを有効化

参考:

- Cloud Run ingress: https://cloud.google.com/run/docs/securing/ingress
- Cloud Run service-to-service auth: https://cloud.google.com/run/docs/authenticating/service-to-service

### 11.2 Codex 側

Job 内の Codex は以下を原則にする。

- `--sandbox workspace-write`
- `--ask-for-approval never`
- `--dangerously-bypass-approvals-and-sandbox` は使わない
- `--search` は既定で無効

意味:

- コンテナ自体で環境分離
- その上で Codex の workspace sandbox も残す
- 外部 Web 検索や広いネットワーク権限は明示用途だけ許可

### 11.3 秘密情報

- API key は Secret Manager の versioned secret
- Job へは file mount か env で注入
- secret 値を prompt、JSONL、workspace に書き戻さない
- `auth.json` を checkpoint に含めない

### 11.4 個人情報

このリポジトリの対象領域では申請人の個人情報を扱うため、raw event と workspace snapshot も個人情報資産として扱う。運用上は以下が必要。

- 開発/検証/本番 bucket 分離
- retention 期間定義
- delete API と物理削除バッチ
- signed URL を多用せず、原則は Service 経由参照

## 12. 既知の制約

1. resume は live attach ではなく checkpoint resume だけ
2. Cloud Run Job 実行履歴は短期保持なので、永続監査は自前保存が前提
3. workspace full snapshot は大きい repo だと転送コストと起動時間が重い
4. `CODEX_HOME` 内部構造は Codex CLI 実装依存なので、CLI 更新時に resume 互換性検証が必要
5. Job crash が checkpoint upload 前に起きると、その run の最新ローカル変更は失われる
6. GCS prefix 単位の IAM 分離は弱いので、厳密な顧客分離が必要なら bucket または project 自体を分ける方が安全
7. `codex exec --json` のイベント schema は将来変わり得るため、parser は unknown event を破棄せず raw 保存優先にする
8. Cloud Run Job は WebSocket/対話端末用途ではないため、リアルタイム UI は polling か別ストリーム実装が必要

## 13. 実装時の最低限ルール

- session 単位で単一 active run を強制する
- raw JSONL は immutable chunk 保存にする
- workspace と `CODEX_HOME` は別 snapshot にする
- `auth.json` は永続化しない
- Cloud Run Job retry は 0、resume は明示 API からだけ行う
- Cloud Run 履歴ではなく Firestore/GCS を正本にする
