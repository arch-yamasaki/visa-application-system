# visa-app

ビザ申請書類のレビュー支援アプリケーション。

## 構成

- `frontend/` — React 19 + Vite。ケース管理、ドキュメントレビュー、PDFハイライト表示。
- `backend/` — FastAPI + Uvicorn。抽出エンジン（Gemini同期/Codex非同期）、GCS/Firestore管理。
- `jobs/codex-runner/` — Cloud Run Job。Codex CLI非同期実行コンテナ。

## 開発

```bash
# ターミナル1: フロントエンド
cd frontend && npm run dev        # localhost:5173

# ターミナル2: バックエンド
cd backend && uvicorn main:app --reload --port 8080
```

frontend の Vite proxy が `/api/*` を `localhost:8080` に転送する。

## 抽出エンジン

| エンジン | 方式 | 用途 |
|---|---|---|
| Gemini | 同期。PDF/テキスト→Gemini API→構造化JSON | 通常の申請書類抽出 |
| Codex | 非同期。Cloud Run Job→codex exec→結果収穫 | 複雑な分析・統合処理 |

## GCPリソース

| リソース | 値 |
|---|---|
| GCS Bucket | `visa-codex-mvp-data` |
| GCP Project | `visa-codex-mvp` |
| Region | `asia-northeast1` |
| Firestore Collection | `sessions` |
| Cloud Run Job | `codex-runner-job` |
