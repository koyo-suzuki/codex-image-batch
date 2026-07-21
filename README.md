# Codex Image Batch

[![CI](https://github.com/koyo-suzuki/codex-image-batch/actions/workflows/ci.yml/badge.svg)](https://github.com/koyo-suzuki/codex-image-batch/actions/workflows/ci.yml)

Codex内蔵の画像生成を使い、複数のプロンプトや参照画像をまとめて処理するCodexプラグインです。APIキーは不要で、ChatGPT/Codexの利用枠を使います。

- 1ウェーブ最大10件の画像生成・編集
- PNG/JPEG/WebPのローカル参照画像
- 同じ指示から複数案を生成
- `jobs.json`を作れるローカルUI
- 出力済み画像の自動スキップと再実行用ログ

## Codexへインストール

Codex CLIでこのマーケットプレイスを追加し、プラグインを入れます。

```bash
codex plugin marketplace add koyo-suzuki/codex-image-batch
codex plugin add codex-image-batch@codex-image-batch
```

Codexを再起動したら、制作フォルダで次のように依頼できます。

```text
$generate-image-batch で jobs.json を一括生成して
```

APIキーや従量課金APIの契約は不要です。ただし、内蔵画像生成は利用中のChatGPT/Codexプランの画像生成枠を消費します。

## UIから設定する

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

- 同時実行数を1・3・5・10から選択
- プロンプト、縦横比、案数、除外事項をカード形式で編集
- 参照画像をドラッグ＆ドロップ
- 制作フォルダへ`jobs.json`と参照画像を保存
- Codexへ渡す実行文をコピー

UIは設定ファイルを作るだけで、勝手に画像生成を開始しません。

## JSONを直接作る

```bash
cp jobs.example.json jobs.json
mkdir -p references
```

参照画像を使う場合は`jobs.references.example.json`を参考に、画像を`references/`へ置きます。その後Codexへ以下を依頼します。

```text
$generate-image-batch で jobs.json を一括生成して
```

結果は`outputs/`へ保存されます。同名画像があるジョブはスキップされます。作り直す場合は「既存画像を上書きして」と明示してください。

## jobs.json

```json
{
  "output_dir": "outputs",
  "parallelism": 10,
  "defaults": {
    "mode": "generate",
    "aspect_ratio": "1:1",
    "variants": 1
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

- `parallelism`: 1〜10。1ウェーブで開始する画像生成呼び出し数
- `mode`: `generate`または`edit`
- `images`: 参照画像または編集対象。文字列パスでも指定可能
- `role`: 各画像をどう使うか
- `variants`: 同じ指示から作る案数（1〜10）。1案を1ジョブとして数える
- `aspect_ratio`: `1:1`、`16:9`、`2:3`など。構図の指示として使う
- `constraints`: 必ず守る条件
- `avoid`: 入れてほしくない要素
- `output_name`: 任意のPNGファイル名

`parallelism: 10`はクライアント側で10件の処理をまとめて開始する設定です。実際の計算開始時刻は、画像生成サービスの混雑・利用枠・スロットリングにより前後する場合があります。

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
- 透明背景は被写体によって追加確認や後処理が必要な場合があります

ライセンスは[MIT](./LICENSE)です。
