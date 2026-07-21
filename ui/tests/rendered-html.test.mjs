import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the batch image builder", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>画像一括生成ビルダー<\/title>/);
  assert.match(html, /画像一括生成ビルダー/);
  assert.match(html, /100個のプロンプトを/);
  assert.match(html, /100件のburstで一斉投入/);
  assert.match(html, /1カード＝1プロンプト＝1画像/);
  assert.match(html, /行ごとにジョブを作る/);
  assert.doesNotMatch(html, /案数/);
  assert.match(html, /制作フォルダを接続/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});
