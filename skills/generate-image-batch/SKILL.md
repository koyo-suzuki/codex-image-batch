---
name: generate-image-batch
description: Generate or edit up to 100 independent image prompts in a client-side burst from jobs.json using Codex built-in image generation without an API key, with optional local reference images and project output paths. One job always means one prompt and one output image. Use when the user asks to batch-generate, 一括生成, parallelize, よーいどんで開始, or process many image prompts inside ChatGPT/Codex subscription limits. Do not use for direct OpenAI API or CLI image generation.
---

# Generate Image Batch

Use Codex built-in `image_gen` once per normalized job. Never request `OPENAI_API_KEY`, call the Image API, or run the fallback image CLI.

Core contract: one object in `jobs` equals one prompt, one image-generation call, and one output image. To create one hundred different images, write one hundred job objects with one hundred prompts. Do not use or invent a `variants`/案数 layer.

## Workflow

1. Locate the requested config, defaulting to `jobs.json` in the current workspace.
   - When the user wants to prepare or edit jobs visually, run `<plugin-root>/start-ui.command` on macOS or start `<plugin-root>/ui` with `npm ci && npm run dev`; consume its saved `jobs.json` without rewriting it first.
2. Run the bundled validator:

   ```bash
   python3 <skill-dir>/scripts/prepare_jobs.py --config <config> --json
   ```

   Add `--force` only when the user explicitly requests overwriting or regeneration.
3. Stop and ask the user when the validator reports a missing or ambiguous input. Do not guess image paths or roles.
4. Skip jobs marked `skipped`. Follow the normalized `waves` order; for every ready job, use its normalized `tool_prompt`, `images`, and `output_path`.
5. Inspect local input images with `view_image` before generation. Treat Image 1 as the edit target when `mode` is `edit`; treat all images as references when `mode` is `generate`. For a large burst, inspect inputs concurrently and stop before dispatch if any input cannot be opened.
6. Call the built-in `image_gen` tool exactly once per ready job, using the burst workflow below:
   - Omit both image inclusion arguments when `images` is empty.
   - Pass `referenced_image_paths` containing all normalized image paths when images are present.
   - Never pass both `referenced_image_paths` and conversation-image inclusion.
7. Generate several distinct jobs with separate calls. Do not use one multi-subject image as a substitute for multiple requested assets.
8. Use `scripts/finalize_run.py` to copy every generated file from its returned `$CODEX_HOME/generated_images/...` path to the exact `output_path`. Do not overwrite unless `--force` was authorized.
9. Inspect each saved result. Check subject, composition, text, constraints, and avoid items. Retry only with one targeted prompt change when the output materially violates the job.
10. Let `finalize_run.py` write `run-<timestamp>.json` with each job ID, final prompt, output path, dispatch/completion timing, and completed/failed/skipped status.
11. Report all saved paths and note that built-in subscription image generation was used.

## Burst execution

- Respect normalized `parallelism` from 1 through 100. Every job is one independent prompt and one call.
- Use one `functions.exec` orchestration call for the whole run. Read and validate `jobs.json` inside that call, then process its normalized waves.
- For each wave, create every `tools.image_gen__imagegen(...)` promise with one synchronous `wave.map(...)` before awaiting anything. Only after the complete promise array exists may you call `Promise.allSettled`. This is the burst start invariant.
- Never use a sequential `for` loop that awaits one image before starting the next. Never split a 100-job wave into hidden groups of 10.
- Start the orchestration source with `// @exec: {"yield_time_ms": 120000, "max_output_tokens": 12000}`. If it yields a running cell ID, resume it with `functions.wait` using `yield_time_ms: 120000` until complete.
- For a new image, pass only `{prompt}`. For a job with local inputs, pass `{prompt, referenced_image_paths}`. Never pass both `referenced_image_paths` and `num_last_images_to_include`.
- Call `notify(...)` when the whole wave has been dispatched and whenever one job completes or fails. This makes progress visible without waiting for the slowest image.
- Emit a small result record for every promise and forward successful results with `generatedImage(result)`. Preserve the input order so results can be mapped back to exact `output_path` values.
- Use the normalized `waves`. Do not start more than 100 image-generation promises in one wave.
- The configured value is requested client concurrency. The image service can still queue or throttle requests; describe that distinction instead of claiming guaranteed simultaneous GPU execution.
- If nested image-generation orchestration is unavailable, fall back to direct image-generation calls, report the actual concurrency used, and never switch to an API-key path.
- Finalize only after every promise in the wave has settled. Use unique normalized output paths so copying cannot conflict.
- Never claim parallel execution unless the calls were started before the wave was awaited.

Use this orchestration shape. Substitute the real absolute paths for `prepareScript`, `finalizeScript`, and `configPath`:

```js
// @exec: {"yield_time_ms": 120000, "max_output_tokens": 12000}
const shellQuote = value => `'${String(value).replaceAll("'", "'\\''")}'`;
const toBase64 = value => {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
};
const generatedPath = hint => hint?.match(/\sas\s(.+?\.png)\sby default/)?.[1];

const preparedResult = await tools.exec_command({
  cmd: `python3 ${shellQuote(prepareScript)} --config ${shellQuote(configPath)} --json${force ? " --force" : ""}`,
  workdir: configDir,
  max_output_tokens: 200000,
  yield_time_ms: 30000,
});
if (preparedResult.exit_code !== 0) throw new Error(preparedResult.output);
const prepared = JSON.parse(preparedResult.output);
const jobById = new Map(prepared.jobs.map(job => [job.id, job]));
const records = prepared.jobs.filter(job => job.status === "skipped").map(job => ({
  id: job.id,
  tool_prompt: job.tool_prompt,
  output_path: job.output_path,
  status: "skipped",
  error: job.skip_reason,
}));

for (const ids of prepared.waves) {
  const wave = ids.map(id => jobById.get(id));
  const epoch = Date.now();
  const dispatchOffsets = [];
  const promises = wave.map((job, index) => {
    const dispatchedAtMs = Date.now() - epoch;
    dispatchOffsets[index] = dispatchedAtMs;
    const paths = job.images.map(image => image.path);
    const args = paths.length
      ? { prompt: job.tool_prompt, referenced_image_paths: paths }
      : { prompt: job.tool_prompt };
    return tools.image_gen__imagegen(args)
      .then(result => {
        const source = generatedPath(result.output_hint);
        if (!source) throw new Error("generated image path was not returned");
        generatedImage(result);
        notify(JSON.stringify({ event: "completed", id: job.id }));
        return {
          id: job.id,
          tool_prompt: job.tool_prompt,
          output_path: job.output_path,
          generated_image_path: source,
          status: "completed",
          dispatched_at_ms: dispatchedAtMs,
          completed_at_ms: Date.now() - epoch,
        };
      })
      .catch(error => {
        notify(JSON.stringify({ event: "failed", id: job.id, error: String(error) }));
        throw error;
      });
  });
  notify(JSON.stringify({ event: "wave_dispatched", count: promises.length, elapsed_ms: Date.now() - epoch }));
  const settled = await Promise.allSettled(promises);
  settled.forEach((entry, index) => {
    if (entry.status === "fulfilled") records.push(entry.value);
    else {
      const job = wave[index];
      records.push({
        id: job.id,
        tool_prompt: job.tool_prompt,
        output_path: job.output_path,
        status: "failed",
        error: String(entry.reason),
        dispatched_at_ms: dispatchOffsets[index],
        completed_at_ms: Date.now() - epoch,
      });
    }
  });
}

const encoded = toBase64(JSON.stringify(records));
const finalized = await tools.exec_command({
  cmd: `python3 ${shellQuote(finalizeScript)} --results-base64 ${encoded} --output-dir ${shellQuote(prepared.output_dir)}${force ? " --force" : ""}`,
  workdir: configDir,
  max_output_tokens: 20000,
  yield_time_ms: 30000,
});
if (finalized.exit_code !== 0) throw new Error(finalized.output);
text(finalized.output);
```

Before using this shape, define:

```js
const prepareScript = "/absolute/path/to/scripts/prepare_jobs.py";
const finalizeScript = "/absolute/path/to/scripts/finalize_run.py";
const configPath = "/absolute/path/to/jobs.json";
const configDir = "/absolute/path/to/config-folder";
const force = false;
```

The `wave_dispatched` event proves that all client promises for that wave were created before the first image-generation await. Record its `elapsed_ms`; do not describe it as provider-side GPU concurrency.

## Built-in constraints

- Treat `aspect_ratio` as prompt guidance; the built-in tool does not expose an exact output-size parameter.
- Use one built-in call per job. One hundred jobs with `parallelism: 100` create one hundred calls in the same client-side burst.
- Do not support masks in this workflow. Use a clear edit prompt and invariants instead.
- For a transparent-background request, follow the built-in-first chroma-key workflow from the system `imagegen` skill. Ask before any API/CLI fallback.
- If built-in image generation is unavailable or fails, report that fact. Do not silently switch to an API-key path.
- Built-in image generation consumes the user's ChatGPT/Codex usage limits. Do not create unrequested extra jobs.
- Official OpenAI guidance recommends the Image API for larger batches. This skill intentionally stays on built-in subscription generation, so a 100-call burst can still be queued, throttled, or partially rejected by the service.

## Run record

For each job, keep `id`, `tool_prompt`, `output_path`, the returned generated-image path, `dispatched_at_ms`, `completed_at_ms`, status, and any error. The run manifest must make partial failures retryable without regenerating successful outputs.
