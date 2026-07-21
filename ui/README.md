# Codex Image Batch UI

`jobs.json`と参照画像をブラウザ上で準備するローカルUIです。画像生成そのものは行いません。

## 起動

Node.js 22.13以上が必要です。

```bash
npm ci
npm run dev
```

表示されたローカルURLをChromeまたはEdgeで開いてください。フォルダへ直接保存する機能はFile System Access APIを使うため、Chrome系ブラウザを推奨します。

## テスト

```bash
npm test
npm run lint
```

詳しい使い方とCodexプラグインの導入方法は、リポジトリ直下の`README.md`を参照してください。
