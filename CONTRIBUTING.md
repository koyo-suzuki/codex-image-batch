# Contributing

IssueやPull Requestを歓迎します。変更前に次を確認してください。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_release.py
cd ui
npm ci
npm test
```

画像生成の実テストは利用枠を消費するため、通常のCIでは行いません。実行した場合は、生成件数と実際に使った並列数をPull Requestへ記載してください。
