# Codex Image Batch

[![CI](https://github.com/koyo-suzuki/codex-image-batch/actions/workflows/ci.yml/badge.svg)](https://github.com/koyo-suzuki/codex-image-batch/actions/workflows/ci.yml)

Codex内蔵の画像生成を使い、複数のプロンプトや参照画像をまとめて処理するCodexプラグインです。APIキーは不要で、ChatGPT/Codexの利用枠を使います。

**1ジョブ＝1プロンプト＝1画像**です。100個の異なるプロンプトを`jobs`へ入れると、100件分の呼び出しを待機前に作成するburst方式で一斉投入します。

- 1ウェーブ最大100件の画像生成・編集
- PNG/JPEG/WebPのローカル参照画像
- 100個の異なるプロンプトを1つのburstで一斉投入
- `jobs.json`を作れるローカルUI
- 1件ごとの完了通知、出力済み画像の自動スキップ、再実行用ログ

## Codexへインストール

Codex CLIでこのマーケットプレイスを追加し、プラグインを入れます。

```bash
codex plugin marketplace add koyo-suzuki/codex-image-batch
codex plugin add codex-image-batch@codex-image-batch
```

Codexを再起動したら、制作フォルダで次のように依頼できます。

```text
$generate-image-batch で jobs.json を最大100件のburstで一斉開始して
```

APIキーや従量課金APIの契約は不要です。ただし、内蔵画像生成は利用中のChatGPT/Codexプランの画像生成枠を消費します。100件をクライアント側から一斉投入しても、画像サービス側の混雑・利用枠・速度制限によって実際の計算は待ち行列になる場合があります。

## UIから設定する

画面ごとの詳しい操作、参照画像の追加、保存許可、実行、再生成、トラブル対処は[Web UI 使い方ガイド](./docs/WEB_UI_GUIDE.md)を参照してください。

UIも使う場合はリポジトリを取得します。

```bash
git clone https://github.com/koyo-suzuki/codex-image-batch.git
cd codex-image-batch
```

macOSでは`start-ui.command`をダブルクリックします。ターミナルから開く場合:

```bash
./start-ui.command
```

Windows/Linuxでは:

```bash
cd ui
npm ci
npm run dev
```

ブラウザで以下を設定できます。

- 一斉投入数を10・25・50・100から選択
- 最大100個のプロンプトを1行ずつまとめて貼り付け
- プロンプト、縦横比、除外事項をカード形式で編集
- 参照画像をドラッグ＆ドロップ
- 制作フォルダへ`jobs.json`と参照画像を保存
- Codexへ渡す実行文をコピー

UIは設定ファイルを作るだけで、勝手に画像生成を開始しません。

最短手順は次のとおりです。

1. 「制作フォルダを接続」で、画像を保存したいフォルダを選ぶ
2. 「プロンプトをまとめて貼る」へ、1行に1プロンプトずつ入力
3. 「行ごとにジョブを作る」を押す
4. 「保存して準備完了」を押し、Chromeの確認が出たら「変更を保存」を押す
5. `jobs.json と参照画像を保存しました`と表示されたことを確認する
6. Codexへ`$generate-image-batch で jobs.json の各プロンプトを最大100件のburstで一斉開始して`と送る

## JSONを直接作る

```bash
cp jobs.example.json jobs.json
mkdir -p references
```

参照画像を使う場合は`jobs.references.example.json`を参考に、画像を`references/`へ置きます。その後Codexへ以下を依頼します。

```text
$generate-image-batch で jobs.json を最大100件のburstで一斉開始して
```

結果は`outputs/`へ保存されます。同名画像があるジョブはスキップされます。作り直す場合は「既存画像を上書きして」と明示してください。

## jobs.json

```json
{
  "output_dir": "outputs",
  "parallelism": 100,
  "defaults": {
    "mode": "generate",
    "aspect_ratio": "1:1"
  },
  "jobs": [
    {
      "id": "new-image",
      "prompt": "新規画像の指示",
      "avoid": ["文字", "ロゴ", "透かし"]
    },
    {
      "id": "with-references",
      "prompt": "参照画像の商品を使った縦長広告ビジュアル",
      "images": [
        { "path": "references/product.png", "role": "商品の外観を保つ参照画像" },
        { "path": "references/logo.png", "role": "ロゴの参照画像" }
      ],
      "aspect_ratio": "2:3"
    },
    {
      "id": "background-edit",
      "mode": "edit",
      "prompt": "背景だけを明るい青空に変更する",
      "images": [{ "path": "references/source.png", "role": "編集対象" }],
      "constraints": ["人物・服装・構図は変更しない"]
    }
  ]
}
```

主な設定:

- `parallelism`: 1〜100。1ウェーブで待機前に作成する画像生成呼び出し数
- `mode`: `generate`または`edit`
- `images`: 参照画像または編集対象。文字列パスでも指定可能
- `role`: 各画像をどう使うか
- `aspect_ratio`: `1:1`、`16:9`、`2:3`など。構図の指示として使う
- `constraints`: 必ず守る条件
- `avoid`: 入れてほしくない要素
- `output_name`: 任意のPNGファイル名

`parallelism: 100`では、100件分の画像生成Promiseを先にすべて作成してから完了待ちに入ります。実行記録の`dispatched_at_ms`でクライアント側の投入時刻を確認できます。実際の計算開始時刻は、画像生成サービスの混雑・利用枠・スロットリングにより前後する場合があります。

OpenAIの公式案内では、大量バッチにはImage APIが推奨されています。このプラグインの100件burstはAPIキー不要の内蔵生成を使うため、100件のリクエスト投入はできますが、100件のGPU計算開始を保証するものではありません。

同じプロンプトから複数案を作る`variants`設定はありません。別の画像として実行したい指示は、それぞれ独立したjobとして追加してください。

## 設定だけ確認する

```bash
python3 skills/generate-image-batch/scripts/prepare_jobs.py --config jobs.json
```

このコマンドは画像を生成せず、設定、参照画像、出力先だけを確認します。

## 開発・テスト

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_release.py
cd ui
npm ci
npm test
```

画像生成の実テストは利用枠を消費するため、自動テストには含めていません。

## 制限

- 内蔵画像生成にはAPIのような厳密なサイズ・品質パラメータがないため、縦横比などはプロンプトで指定します
- マスク画像による範囲指定は扱いません。編集対象と変更箇所を文章で指定してください
- 完全な無人APIバッチではなく、Codexタスク内でジョブを処理します
- 100件burstはクライアント側の一斉投入です。サービス側での同時計算数は保証されません
- 透明背景は被写体によって追加確認や後処理が必要な場合があります

ライセンスは[MIT](./LICENSE)です。
