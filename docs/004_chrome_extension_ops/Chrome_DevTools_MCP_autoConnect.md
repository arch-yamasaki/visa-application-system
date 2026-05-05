# Chrome DevTools MCP autoConnect

既存Chromeのログイン状態を使って、CodexからChrome DevTools MCPを動かすための最小メモ。

## 初回だけやること

Chrome側は基本一回だけでよい。

1. 普段使っているChromeで `chrome://inspect/#remote-debugging` を開く。
2. `Allow remote debugging for this browser instance` をONにする。
3. `Server running at: 127.0.0.1:9222` が出ていればOK。

Chrome更新後、プロファイル変更後、またはMCPが既存タブを見つけられないときだけ再確認する。

## Codex設定

`~/.codex/config.toml` の `chrome-devtools` MCPを `--autoConnect` 付きで起動する。

```toml
[mcp_servers.chrome-devtools]
command = "npx"
args = ["-y", "chrome-devtools-mcp@latest", "--autoConnect"]
```

設定変更後はCodex/MCPを再起動する。

## 毎回の確認

MCPの `list_pages` で普段のChromeタブが見えればOK。

`chrome://inspect/#remote-debugging` や入管オンラインシステムの既存タブが見えない場合は、MCP専用プロファイルを見ている可能性がある。

## 注意

- `chrome://inspect/#remote-debugging` をONにしただけでは足りない。MCP側にも `--autoConnect` が必要。
- `http://127.0.0.1:9222/json/version` が `404` でも、それだけで失敗とは判断しない。
- 既存Chromeに接続するとCookieやログイン状態を扱えるので、信頼できるローカル環境だけで使う。

## 入管QAの禁止操作

Chrome DevTools MCP、手動QA、Chrome拡張QAのいずれでも、最終送信系は絶対に押さない。

- `申込む`
- `送信`
- `確定`
- 申請の最終送信
- 本番申請番号を発行・更新する可能性がある操作

詳しくは [QA Policy](../../visa_application_app/QA_POLICY.md) を見る。

## 参考

- https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session
- https://github.com/ChromeDevTools/chrome-devtools-mcp
