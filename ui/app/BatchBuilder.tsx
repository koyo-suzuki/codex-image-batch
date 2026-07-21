"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";

type LocalFileHandle = {
  getFile(): Promise<File>;
  createWritable(): Promise<{ write(data: Blob | string): Promise<void>; close(): Promise<void> }>;
};

type LocalDirectoryHandle = {
  name: string;
  getFileHandle(name: string, options?: { create?: boolean }): Promise<LocalFileHandle>;
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<LocalDirectoryHandle>;
};

declare global {
  interface Window {
    showDirectoryPicker?: () => Promise<LocalDirectoryHandle>;
  }
}

type ImageRef = {
  key: string;
  path: string;
  role: string;
  preview?: string;
  file?: File;
};

type Job = {
  key: string;
  id: string;
  mode: "generate" | "edit";
  prompt: string;
  aspectRatio: string;
  outputName: string;
  constraints: string;
  avoid: string;
  images: ImageRef[];
};

const ratios = ["1:1", "3:2", "2:3", "16:9", "9:16"];

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function newJob(index: number): Job {
  return {
    key: uid(),
    id: `image-${index}`,
    mode: "generate",
    prompt: "",
    aspectRatio: "1:1",
    outputName: "",
    constraints: "",
    avoid: "文字、ロゴ、透かし",
    images: [],
  };
}

const initialJobs: Job[] = [newJob(1)];

function splitList(value: string) {
  return value
    .split(/[、,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function safeFilename(value: string) {
  return value.normalize("NFKC").replace(/[^\p{Letter}\p{Number}._-]+/gu, "-").replace(/^-+|-+$/g, "") || "image";
}

function toUiJobs(raw: unknown): Job[] {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { jobs?: unknown }).jobs)) {
    throw new Error("jobs配列が見つかりません");
  }

  const rawJobs = (raw as { jobs: Array<Record<string, unknown>> }).jobs;
  if (rawJobs.some((item) => Object.hasOwn(item, "variants"))) {
    throw new Error("案数は廃止しました。1プロンプトごとに1件のjobへ分けてください");
  }

  return rawJobs.map((item, index) => ({
    key: uid(),
    id: typeof item.id === "string" ? item.id : `image-${index + 1}`,
    mode: item.mode === "edit" ? "edit" : "generate",
    prompt: typeof item.prompt === "string" ? item.prompt : "",
    aspectRatio: typeof item.aspect_ratio === "string" ? item.aspect_ratio : "1:1",
    outputName: typeof item.output_name === "string" ? item.output_name : "",
    constraints: Array.isArray(item.constraints) ? item.constraints.join("、") : "",
    avoid: Array.isArray(item.avoid) ? item.avoid.join("、") : "",
    images: Array.isArray(item.images)
      ? item.images.map((image) => {
          const normalized = typeof image === "string" ? { path: image, role: "参照画像" } : (image as { path?: string; role?: string });
          return {
            key: uid(),
            path: normalized.path ?? "",
            role: normalized.role ?? "参照画像",
          };
        })
      : [],
  }));
}

export function BatchBuilder() {
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [parallelism, setParallelism] = useState(10);
  const [bulkPrompts, setBulkPrompts] = useState("");
  const [directory, setDirectory] = useState<LocalDirectoryHandle | null>(null);
  const [notice, setNotice] = useState("まずは内容を整えて、制作フォルダへ保存します");
  const [busy, setBusy] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);

  const outputCount = jobs.length;
  const waves = Math.max(1, Math.ceil(outputCount / parallelism));

  function updateJob(key: string, patch: Partial<Job>) {
    setJobs((current) => current.map((job) => (job.key === key ? { ...job, ...patch } : job)));
  }

  function validate() {
    const ids = new Set<string>();
    for (const [index, job] of jobs.entries()) {
      if (!job.id.trim()) throw new Error(`${index + 1}件目のIDが空です`);
      if (ids.has(job.id.trim())) throw new Error(`ID「${job.id}」が重複しています`);
      ids.add(job.id.trim());
      if (!job.prompt.trim()) throw new Error(`「${job.id}」のプロンプトが空です`);
      if (job.mode === "edit" && job.images.length === 0) throw new Error(`「${job.id}」の編集対象画像がありません`);
    }
  }

  function prepareTenJobs() {
    setJobs((current) => {
      if (current.length >= 10) return current;
      return [
        ...current,
        ...Array.from({ length: 10 - current.length }, (_, index) => newJob(current.length + index + 1)),
      ];
    });
    setNotice("10個のプロンプト入力欄を用意しました。1欄から1画像を生成します");
  }

  function applyBulkPrompts() {
    const prompts = bulkPrompts.split(/\n+/).map((value) => value.trim()).filter(Boolean);
    if (!prompts.length) {
      setNotice("プロンプトを1行に1件ずつ入力してください");
      return;
    }
    setJobs(prompts.map((prompt, index) => ({ ...newJob(index + 1), prompt })));
    setNotice(`${prompts.length}個のプロンプトを${prompts.length}件のジョブに変換しました`);
  }

  async function connectFolder() {
    if (!window.showDirectoryPicker) {
      setNotice("このブラウザはフォルダ接続に未対応です。JSONダウンロードを利用できます");
      return;
    }
    try {
      const handle = await window.showDirectoryPicker();
      setDirectory(handle);
      setNotice(`「${handle.name}」へ接続しました`);
      try {
        const fileHandle = await handle.getFileHandle("jobs.json");
        const file = await fileHandle.getFile();
        const raw = JSON.parse(await file.text());
        setJobs(toUiJobs(raw));
        const value = (raw as { parallelism?: unknown }).parallelism;
        if (typeof value === "number" && value >= 1 && value <= 10) setParallelism(value);
        setNotice(`「${handle.name}」の jobs.json を読み込みました`);
      } catch {
        setNotice(`「${handle.name}」へ接続しました。新しい jobs.json を作成できます`);
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") setNotice("フォルダ接続に失敗しました");
    }
  }

  async function addFiles(jobKey: string, files: FileList | File[]) {
    const accepted = Array.from(files).filter((file) => /image\/(png|jpeg|webp)/.test(file.type));
    if (!accepted.length) {
      setNotice("PNG・JPEG・WebP画像を選んでください");
      return;
    }
    const additions = accepted.map((file) => ({
      key: uid(),
      path: `references/${file.name}`,
      role: "参照画像",
      preview: URL.createObjectURL(file),
      file,
    }));
    setJobs((current) => current.map((job) => (job.key === jobKey ? { ...job, images: [...job.images, ...additions] } : job)));
    setNotice(`${accepted.length}枚の画像を追加しました`);
  }

  async function buildConfig(saveImages: boolean) {
    validate();
    const references = saveImages && directory ? await directory.getDirectoryHandle("references", { create: true }) : null;
    const normalizedJobs = [];

    for (const job of jobs) {
      const images = [];
      for (const [index, image] of job.images.entries()) {
        let imagePath = image.path;
        if (references && image.file) {
          const extension = image.file.name.includes(".") ? `.${image.file.name.split(".").pop()}` : ".png";
          const filename = `${safeFilename(job.id)}-${String(index + 1).padStart(2, "0")}${extension.toLowerCase()}`;
          const handle = await references.getFileHandle(filename, { create: true });
          const writable = await handle.createWritable();
          await writable.write(image.file);
          await writable.close();
          imagePath = `references/${filename}`;
        }
        images.push({ path: imagePath, role: image.role || "参照画像" });
      }

      normalizedJobs.push({
        id: job.id.trim(),
        mode: job.mode,
        prompt: job.prompt.trim(),
        aspect_ratio: job.aspectRatio,
        ...(job.outputName.trim() ? { output_name: job.outputName.trim() } : {}),
        ...(images.length ? { images } : {}),
        ...(splitList(job.constraints).length ? { constraints: splitList(job.constraints) } : {}),
        ...(splitList(job.avoid).length ? { avoid: splitList(job.avoid) } : {}),
      });
    }

    return { output_dir: "outputs", parallelism, jobs: normalizedJobs };
  }

  async function saveConfig() {
    setBusy(true);
    try {
      const config = await buildConfig(Boolean(directory));
      const content = `${JSON.stringify(config, null, 2)}\n`;
      if (directory) {
        const handle = await directory.getFileHandle("jobs.json", { create: true });
        const writable = await handle.createWritable();
        await writable.write(content);
        await writable.close();
        setNotice("jobs.json と参照画像を保存しました");
      } else {
        const blob = new Blob([content], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "jobs.json";
        link.click();
        URL.revokeObjectURL(link.href);
        setNotice("jobs.json をダウンロードしました。画像は references/ へ置いてください");
      }
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function importConfig(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const raw = JSON.parse(await file.text());
      setJobs(toUiJobs(raw));
      const value = (raw as { parallelism?: unknown }).parallelism;
      if (typeof value === "number" && value >= 1 && value <= 10) setParallelism(value);
      setNotice(`${file.name} を読み込みました`);
    } catch (error) {
      setNotice(`読み込み失敗: ${(error as Error).message}`);
    }
    event.target.value = "";
  }

  async function copyCommand() {
    await navigator.clipboard.writeText("$generate-image-batch で jobs.json の各プロンプトを最大10件並列で生成して");
    setNotice("Codexへの実行文をコピーしました");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark">IMG</span>
          <div>
            <p className="eyebrow">CODEX IMAGE QUEUE</p>
            <h1>画像一括生成ビルダー</h1>
          </div>
        </div>
        <div className={`connection ${directory ? "is-connected" : ""}`}>
          <span className="connection-dot" />
          {directory ? `${directory.name} に接続中` : "フォルダ未接続"}
        </div>
      </header>

      <section className="overview-card">
        <div className="overview-copy">
          <p className="section-kicker">BATCH OVERVIEW</p>
          <h2>10個のプロンプトを、<br />10件のジョブとして同時開始。</h2>
          <p>1プロンプト＝1画像です。最大10個ずつCodex内蔵の画像生成をまとめて呼び出し、11個目以降は次のウェーブへ送ります。</p>
        </div>
        <div className="metrics">
          <div className="metric"><strong>{jobs.length}</strong><span>プロンプト</span></div>
          <div className="metric accent"><strong>{outputCount}</strong><span>実行ジョブ</span></div>
          <div className="metric"><strong>{waves}</strong><span>実行ウェーブ</span></div>
        </div>
        <div className="parallel-control">
          <div>
            <label htmlFor="parallelism">同時実行数</label>
            <p>1〜10件。おすすめは10</p>
          </div>
          <div className="segmented" id="parallelism">
            {[1, 3, 5, 10].map((value) => (
              <button key={value} className={parallelism === value ? "active" : ""} onClick={() => setParallelism(value)}>{value}</button>
            ))}
          </div>
        </div>
      </section>

      <section className="actionbar" aria-label="設定操作">
        <button className="button primary" onClick={connectFolder}>制作フォルダを接続</button>
        <button className="button" onClick={prepareTenJobs}>10件の入力欄を用意</button>
        <button className="button" onClick={() => importRef.current?.click()}>JSONを読み込む</button>
        <input ref={importRef} type="file" accept="application/json,.json" hidden onChange={importConfig} />
        <span className="action-spacer" />
        <button className="button" onClick={copyCommand}>実行文をコピー</button>
        <button className="button save" disabled={busy} onClick={saveConfig}>{busy ? "保存中…" : directory ? "フォルダへ保存" : "JSONを保存"}</button>
      </section>

      <section className="bulk-entry">
        <div className="bulk-copy">
          <p className="section-kicker">QUICK INPUT</p>
          <h2>プロンプトをまとめて貼る</h2>
          <p>1行が1プロンプト、1画像になります。10行なら10件を同じウェーブで開始します。</p>
        </div>
        <div className="bulk-field">
          <textarea
            value={bulkPrompts}
            onChange={(event) => setBulkPrompts(event.target.value)}
            placeholder={"白背景の商品写真\n夜のネオン街を歩く白猫\n海辺に建つ未来的なホテル"}
          />
          <button className="button primary" onClick={applyBulkPrompts}>行ごとにジョブを作る</button>
        </div>
      </section>

      <section className="jobs-section">
        <div className="section-heading">
          <div><p className="section-kicker">PROMPT JOBS</p><h2>1カード＝1プロンプト＝1画像</h2></div>
          <div className="section-actions">
            <button className="add-button" onClick={prepareTenJobs}>10件まで追加</button>
            <button className="add-button" onClick={() => setJobs((current) => [...current, newJob(current.length + 1)])}>＋ 1件追加</button>
          </div>
        </div>

        <div className="job-list">
          {jobs.map((job, index) => (
            <article className="job-card" key={job.key}>
              <div className="job-index">{String(index + 1).padStart(2, "0")}</div>
              <div className="job-content">
                <div className="job-header">
                  <div className="mode-switch">
                    <button className={job.mode === "generate" ? "active" : ""} onClick={() => updateJob(job.key, { mode: "generate" })}>新規生成</button>
                    <button className={job.mode === "edit" ? "active" : ""} onClick={() => updateJob(job.key, { mode: "edit" })}>画像編集</button>
                  </div>
                  <div className="job-actions">
                    <button aria-label="複製" onClick={() => setJobs((current) => [...current.slice(0, index + 1), { ...job, key: uid(), id: `${job.id}-copy`, images: job.images.map((image) => ({ ...image, key: uid() })) }, ...current.slice(index + 1)])}>複製</button>
                    <button aria-label="削除" disabled={jobs.length === 1} onClick={() => setJobs((current) => current.filter((item) => item.key !== job.key))}>削除</button>
                  </div>
                </div>

                <div className="form-grid compact-grid">
                  <label><span>ファイルID</span><input value={job.id} onChange={(event) => updateJob(job.key, { id: event.target.value })} placeholder="product-poster" /></label>
                  <label><span>出力名 <small>任意</small></span><input value={job.outputName} onChange={(event) => updateJob(job.key, { outputName: event.target.value })} placeholder={`${safeFilename(job.id)}.png`} /></label>
                </div>

                <label className="prompt-field"><span>この1画像のプロンプト</span><textarea value={job.prompt} onChange={(event) => updateJob(job.key, { prompt: event.target.value })} placeholder="何を、どんな構図・雰囲気で作るかを書いてください" /></label>

                <div className="ratio-row">
                  <span>縦横比</span>
                  <div className="ratio-options">
                    {ratios.map((ratio) => <button key={ratio} className={job.aspectRatio === ratio ? "active" : ""} onClick={() => updateJob(job.key, { aspectRatio: ratio })}>{ratio}</button>)}
                  </div>
                </div>

                <div className="form-grid">
                  <label><span>必ず守ること</span><input value={job.constraints} onChange={(event) => updateJob(job.key, { constraints: event.target.value })} placeholder="商品形状を保つ、人物を変えない" /></label>
                  <label><span>入れないもの</span><input value={job.avoid} onChange={(event) => updateJob(job.key, { avoid: event.target.value })} placeholder="文字、ロゴ、透かし" /></label>
                </div>

                <div className="reference-block">
                  <div className="reference-heading"><div><span>参照画像</span><small>{job.mode === "edit" ? "1枚目を編集対象として扱います" : "商品・人物・スタイルの参考に使います"}</small></div><span className="image-count">{job.images.length}枚</span></div>
                  <label
                    className="drop-zone"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); void addFiles(job.key, event.dataTransfer.files); }}
                  >
                    <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={(event) => event.target.files && void addFiles(job.key, event.target.files)} />
                    <strong>画像をここへドロップ</strong><span>またはクリックして選択</span>
                  </label>
                  {job.images.length > 0 && <div className="image-list">
                    {job.images.map((image, imageIndex) => (
                      <div className="image-item" key={image.key}>
                        {/* eslint-disable-next-line @next/next/no-img-element -- Blob previews are local-only. */}
                        {image.preview ? <img src={image.preview} alt="" /> : <div className="image-placeholder">IMG</div>}
                        <div><strong>{image.path.split("/").pop()}</strong><input value={image.role} onChange={(event) => updateJob(job.key, { images: job.images.map((item) => item.key === image.key ? { ...item, role: event.target.value } : item) })} placeholder={imageIndex === 0 && job.mode === "edit" ? "編集対象" : "参照画像の役割"} /></div>
                        <button aria-label="画像を削除" onClick={() => updateJob(job.key, { images: job.images.filter((item) => item.key !== image.key) })}>×</button>
                      </div>
                    ))}
                  </div>}
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer className="sticky-footer">
        <div className="notice"><span />{notice}</div>
        <div className="footer-summary"><strong>{outputCount}枚</strong><span>を最大{parallelism}並列・{waves}ウェーブで処理</span></div>
        <button className="button save" disabled={busy} onClick={saveConfig}>{directory ? "保存して準備完了" : "jobs.jsonを保存"}</button>
      </footer>
    </main>
  );
}
