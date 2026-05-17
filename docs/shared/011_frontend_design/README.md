# visa-app フロントエンド設計ドキュメント

> 本ドキュメントはUI実装の動きと具体例に特化する。ディレクトリ構成・API・型定義の全体像は `docs/visa-reviewer-architecture.md` を参照。

---

## 1. 技術スタック

| ライブラリ | バージョン | 用途 |
|---|---|---|
| React | 19.2.x | UI ライブラリ |
| Vite | 8.x | ビルド / dev server。`/api/*` をバックエンド (`localhost:8080`) へ proxy |
| Zustand | 5.x | 軽量グローバル状態管理（viewerStore） |
| Tailwind CSS | 4.x (`@tailwindcss/vite`) | ユーティリティ CSS |
| pdfjs-dist | 5.7.x | PDF レンダリング（Canvas + テキストレイヤ） |
| react-router-dom | 7.x | クライアントサイドルーティング |
| Playwright | 1.60.x (devDependency) | E2E テスト |

---

## 2. ページ構成とルーティング

`main.tsx` で `<BrowserRouter>` を設置し、`App.tsx` 内の `<Routes>` でルートを定義する。

```tsx
// App.tsx
<Routes>
  <Route path="/"                       element={<CaseListPage />} />
  <Route path="/cases/:caseId/upload"   element={<UploadPage />} />
  <Route path="/cases/:caseId/review"   element={<ReviewPage />} />
  <Route path="*"                       element={<Navigate to="/" />} />
</Routes>
```

| パス | ページ | 役割 |
|---|---|---|
| `/` | `CaseListPage` | 案件一覧の表示。新規案件作成ボタン。`workflow_state` に応じてアップロードまたはレビューへ遷移。 |
| `/cases/:caseId/upload` | `UploadPage` | ドラッグ&ドロップによるファイルアップロード、抽出エンジン（Gemini / Codex）の選択と実行。完了後にレビューへ遷移。 |
| `/cases/:caseId/review` | `ReviewPage` | 抽出結果のフィールド一覧と書類ビューアを左右分割で表示。フィールド編集、証跡ハイライト、確認完了操作を行う。 |

---

## 3. コンポーネントツリー

```
App
├── CaseListPage
│
├── UploadPage
│   ├── DropZone              ← ドラッグ&ドロップ / ファイル / フォルダ選択
│   ├── FileList              ← アップロード済みドキュメント一覧
│   └── ExtractionProgress    ← 抽出中のスピナー / 失敗メッセージ
│
└── ReviewPage
    ├── ReviewBanner          ← ケースID、ワークフロー状態、確認進捗バー、警告件数
    ├── FieldPanel            ← 左ペイン（フィールド一覧）
    │   └── FieldSection[]    ← セクション単位の折りたたみ（申請人、旅券、所属機関...）
    │       └── FieldRow[]    ← 各フィールド行（ラベル、値、信頼度ドット、FlagBadge）
    │           └── FlagBadge ← OK / 要確認 / 不足 / エラー / 編集済 のバッジ
    └── DocumentViewer        ← 右ペイン（書類表示）
        ├── PdfViewer         ← PDF レンダリング + bbox/テキストハイライト
        ├── HtmlViewer        ← DOCX/XLSX の HTML プレビュー（iframe）
        └── ImageViewer       ← 画像表示
```

ReviewPage の左右ペインはドラッグハンドル付きの可変幅スプリッター（`splitRatio`、初期値 0.45、0.25〜0.75 の範囲でリサイズ可能）で分割される。

---

## 4. 状態管理（Zustand viewerStore）

### ストア定義 (`store/viewerStore.ts`)

```ts
interface ViewerState {
  documents: DocumentEntry[]          // 現在のケースのドキュメント一覧
  currentDocumentId: string | null    // 表示中のドキュメントID
  currentPage: number                 // 表示中のページ番号
  highlightText: string | null        // テキスト検索用のハイライト文字列
  highlightSourceRef: SourceRef | null // bbox 付き SourceRef（bbox 優先）
  signedUrls: Record<string, string>  // docId → signed URL キャッシュ
  activeFieldPath: string | null      // 左ペインで選択中のフィールドパス
}
```

### アクション一覧

| アクション | 動作 |
|---|---|
| `setDocuments(docs)` | ドキュメント一覧をセットし、先頭を `currentDocumentId` に設定 |
| `setSignedUrl(docId, url)` | signed URL をキャッシュに追加 |
| `navigateToSource(ref)` | `currentDocumentId`, `currentPage`, `highlightText`, `highlightSourceRef` を一括更新。フィールドクリック時の証跡ジャンプに使用 |
| `setPage(page)` | ページ番号を変更し、ハイライトをクリア |
| `clearHighlight()` | ハイライト情報をクリア |
| `setActiveFieldPath(path)` | 選択中のフィールドパスを設定（行の青背景表示に使用） |

### どのコンポーネントが何を参照するか

| コンポーネント | 読み取り | 書き込み |
|---|---|---|
| `ReviewPage` | - | `setDocuments` |
| `FieldRow` | `activeFieldPath` | `navigateToSource`, `setActiveFieldPath` |
| `DocumentViewer` | `documents`, `currentDocumentId`, `currentPage`, `highlightText`, `highlightSourceRef`, `signedUrls` | `setSignedUrl`, `navigateToSource` |
| `PdfViewer` | - (props 経由) | `setPage` |

---

## 5. APIクライアント (`api/client.ts`)

### 構造

`apiClient` オブジェクトが全APIメソッドを公開する。各メソッドの先頭で `isDemoMode()` をチェックし、デモモードなら `mockApi`（`mockData.ts`）に委譲する。

### デモモード判定 (`isDemoMode()`)

以下のいずれかで有効化される（優先順）:

1. 環境変数 `VITE_DEMO=true`
2. URL パラメータ `?demo=true`（検知時に `sessionStorage` に保存）
3. `sessionStorage` の `visa_demo_mode` フラグ

### 主要メソッド

| メソッド | HTTP | パス | 用途 |
|---|---|---|---|
| `listCases()` | GET | `/api/cases` | 案件一覧取得 |
| `createCase(params)` | POST | `/api/cases` | 新規案件作成 |
| `getCase(caseId)` | GET | `/api/cases/:id` | ケース全データ取得 |
| `updateCase(caseId, updates)` | PATCH | `/api/cases/:id` | case_data / field_metadata / workflow_state 更新 |
| `uploadDocument(caseId, file, role)` | POST | `/api/cases/:id/documents` | FormData でファイルアップロード |
| `listDocuments(caseId)` | GET | `/api/cases/:id/documents` | ドキュメント一覧 |
| `getDocumentUrl(caseId, docId)` | GET | `/api/cases/:id/documents/:docId/url` | signed URL 取得 |
| `getDocumentContentUrl(caseId, docId)` | - | （URL 文字列生成のみ） | コンテンツ直接 URL |
| `getDocumentPreviewUrl(caseId, docId, sheet?)` | - | （URL 文字列生成のみ） | DOCX/XLSX の HTML プレビュー URL |
| `getDocumentSheets(caseId, docId)` | GET | `/api/cases/:id/documents/:docId/sheets` | XLSX のシート名一覧 |
| `startExtraction(caseId, options)` | POST | `/api/cases/:id/extract` | 抽出開始（backend: gemini/codex） |
| `getExtractionStatus(caseId)` | GET | `/api/cases/:id/extraction-status` | 抽出状態ポーリング |

### mockData.ts

デモ用にインラインで `demoCaseData`（技人国のベトナム人申請サンプル）、`demoReview`（missing_items / findings 付き）、`demoDocuments`（passport.pdf, resume.pdf）を定義。`generateFieldMetadata()` で各フィールドに `source_refs`（confidence / text_quote 付き）を自動生成する。PDF は Mozilla の公開サンプル PDF を使用。

---

## 6. PDFビューア & ハイライト機能 (`PdfViewer.tsx`)

### レンダリングフロー

1. `url` が変わるたびに `pdfjsLib.getDocument()` で PDF をロードし、`pdfDoc` state に保存
2. `pdfDoc` / `page` / ハイライト情報が変わるたびに `renderPage()` を呼ぶ
3. `renderPage()` は `<canvas>` に `pdfPage.render()` でラスタライズ（scale = 1.5）
4. ハイライトは canvas 上に重ねた `<div>` オーバーレイで実現

### ハイライト方式（2種類）

#### 方式A: bbox 座標によるハイライト（優先）

`sourceRef.bbox` が存在する場合に使用。Gemini が返す正規化座標（0〜1000）を viewport サイズに変換する。

```ts
// bbox は { y_min, x_min, y_max, x_max } で 0〜1000 の正規化座標
div.style.left   = `${(x_min / 1000) * viewport.width}px`
div.style.top    = `${(y_min / 1000) * viewport.height}px`
div.style.width  = `${((x_max - x_min) / 1000) * viewport.width}px`
div.style.height = `${((y_max - y_min) / 1000) * viewport.height}px`
```

スタイル: `rgba(255, 160, 0, 0.45)` の半透明オレンジ背景 + `rgba(255, 140, 0, 0.7)` のボーダー。

#### 方式B: テキストマッチによるハイライト（フォールバック）

bbox がない場合、`highlightText` を使って PDF のテキストレイヤから該当箇所を検索する。

1. `pdfPage.getTextContent()` で全テキストアイテムを取得
2. 全テキストを NFKC 正規化 + 空白・句読点除去して連結
3. 正規化した `quote` で `indexOf` 検索。見つからない場合は先頭から10文字以上の部分一致を試行
4. マッチしたテキストアイテムの座標（`Util.transform` で viewport 座標に変換）にオーバーレイ div を配置

### ページネーション

`numPages > 1` の場合、「前へ / 次へ」ボタンとページ番号を表示。ボタンクリックで `viewerStore.setPage()` を呼ぶ。

---

## 7. DOCX/XLSX プレビュー (`HtmlViewer.tsx`)

### 表示方法

バックエンドの `/preview` エンドポイントが DOCX/XLSX を HTML に変換して返す。フロントエンドは `<iframe>` でそのまま表示する。

```
URL = /api/cases/:caseId/documents/:docId/preview[?sheet=シート名]
```

### XLSX シート切り替え

1. `DocumentViewer` が `apiClient.getDocumentSheets()` でシート名一覧を取得
2. `HtmlViewer` にシート一覧を `sheets` prop で渡す
3. シートが2つ以上の場合、タブ UI を表示。クリックで `onSheetChange` コールバックを呼び、`DocumentViewer` が `selectedSheet` を更新 → `previewUrl` が再生成される

### ハイライト

iframe ロード後、`contentDocument` にアクセスしてテキスト検索を行い、該当ノードを `<mark>` タグでラップする。スタイルは PDF と同じオレンジ系。cross-origin の場合はハイライトなしで表示。

---

## 8. フィールドパネル

### 構造: FieldPanel → FieldSection → FieldRow

#### FieldPanel (`components/review/FieldPanel.tsx`)

- `flattenCaseData(caseData)` で全フィールドをドットパス形式（`applicant.name_roman` 等）に展開
- `getSectionForPath()` でトップレベルキーからセクション名（「申請人」「旅券」「所属機関」等）に変換
- `review.missing_items`, `review.validation_errors`, `review.findings` から flagged なパスの Set を構築
- セクションごとに `FieldSection` を、フィールドごとに `FieldRow` を生成

#### FieldSection (`components/review/FieldSection.tsx`)

- 折りたたみ可能なセクション（デフォルト展開）
- ヘッダーに「確認済: N/M」のカウント表示
- 「全て確認済み」ボタン（未完了時のみ表示） → `onMarkSectionReviewed` で一括 `human_reviewed = true`
- 全完了時は「確認完了」ラベル表示

#### FieldRow (`components/review/FieldRow.tsx`)

- **シングルクリック**: `setActiveFieldPath(fieldPath)` + `navigateToSource(source_refs[0])` で証跡ジャンプ
- **ダブルクリック**: インライン編集モード開始
- **キーボード**: Enter で編集開始、矢印キーで行間移動、Escape で編集キャンセル
- **信頼度ドット** (`ConfidenceDots`): confidence を 5 段階で表示。0.9 以上は緑、0.7 以上は黄、それ以下は赤
- **FlagBadge**: `ok` / `needs_review` / `missing` / `error` / `edited` の 5 種類。アイコン + 日本語ラベル
- **ラベル変換**: `fieldPaths.ts` の `getFieldLabel()` で英語パスを日本語ラベルに変換（300+ のマッピング）
- **値変換**: `getDisplayValue()` で内部値（`male`, `certificate_of_eligibility` 等）を日本語表示に変換

#### ReviewBanner (`components/review/ReviewBanner.tsx`)

- ワークフロー状態バッジ（要レビュー / 入力準備完了 / 抽出中 等）
- 確認進捗プログレスバー（`human_reviewed` の割合）
- 警告件数（missing_items + validation_errors）とfindings件数

---

## 9. 具体例: ユーザーがフィールド「資本金」をクリックしたときの流れ

以下、`employer.capital_jpy` フィールドの証跡ジャンプの全ステップを追う。

### ステップ 1: FieldRow の onClick ハンドラ発火

```
FieldRow (path="employer.capital_jpy") → handleClick()
```

1. `setActiveFieldPath("employer.capital_jpy")` を呼び、viewerStore の `activeFieldPath` が更新される
2. `meta.source_refs[0]` が存在するか確認。存在する場合:

```ts
// source_refs[0] の例:
{
  document_id: "doc_001",
  page: 1,
  text_quote: "10,000,000",
  confidence: 0.93,
  bbox: { y_min: 520, x_min: 300, y_max: 550, x_max: 480 }  // ある場合
}
```

3. `navigateToSource(source_refs[0])` を呼ぶ

### ステップ 2: viewerStore が一括更新

`navigateToSource(ref)` が以下の state を一度に set する:

```ts
{
  currentDocumentId: "doc_001",       // 表示ドキュメント切替
  currentPage: 1,                     // ページ番号
  highlightText: "10,000,000",        // テキスト検索フォールバック用
  highlightSourceRef: ref,            // bbox 含む SourceRef 全体
}
```

### ステップ 3: DocumentViewer が反応

`DocumentViewer` は viewerStore から `currentDocumentId`, `signedUrls` を subscribe しているため:

1. `currentDocumentId` が `"doc_001"` に変わる
2. `signedUrls["doc_001"]` がキャッシュにあればそのまま使用。なければ `apiClient.getDocumentUrl()` で取得して `setSignedUrl` でキャッシュ
3. 拡張子判定: `.pdf` → `PdfViewer` を選択
4. `PdfViewer` に `url`, `page=1`, `highlightText="10,000,000"`, `sourceRef={...}` を props で渡す

### ステップ 4: PdfViewer がページをレンダリング + ハイライト表示

1. `renderPage(pdfDoc, 1)` が呼ばれ、canvas に PDF 1 ページ目をラスタライズ
2. ハイライト判定:
   - `sourceRef.bbox` が存在する場合 → **方式A**: bbox 座標をオーバーレイ div に変換して配置
   - `sourceRef.bbox` が存在しない場合 → **方式B**: `highlightText` でテキストレイヤ検索
3. ハイライト div を `scrollIntoView({ behavior: 'smooth', block: 'center' })` でビューポート中央にスクロール

### ステップ 5: UIの視覚的変化

| 要素 | 変化 |
|---|---|
| FieldRow（左ペイン） | `bg-blue-100 border-l-2 border-blue-500` のアクティブスタイルが適用される |
| DocumentViewer タブ | `doc_001` のタブが青色アクティブになる |
| PdfViewer（右ペイン） | 該当ページが表示され、「資本金」の値の位置にオレンジ色のハイライト矩形が表示される |

ユーザーは左ペインの値と右ペインの原本証跡を見比べて確認 → ダブルクリックで編集、またはセクション単位で「全て確認済み」をクリックしてレビューを進める。
