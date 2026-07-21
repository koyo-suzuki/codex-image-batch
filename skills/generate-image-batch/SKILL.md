---
name: generate-image-batch
description: Generate or edit up to 10 independent image prompts concurrently from jobs.json using Codex built-in image generation without an API key, with optional local reference images and project output paths. One job always means one prompt and one output image. Use when the user asks to batch-generate, 一括生成, parallelize, or process multiple image prompts inside ChatGPT/Codex subscription limits. Do not use for direct OpenAI API or CLI image generation.
---

# Generate Image Batch

Use Codex built-in `image_gen` once per normalized job. Never request `OPENAI_API_KEY`, call the Image API, or run the fallback image CLI.

Core contract: one object in `jobs` equals one prompt, one image-generation call, and one output image. To create ten different images, write ten job objects with ten prompts. Do not use or invent a `variants`/案数 layer.

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
5. Inspect every local input image with `view_image` before generation. Treat Image 1 as the edit target when `mode` is `edit`; treat all images as references when `mode` is `generate`.
6. Call the built-in `image_gen` tool exactly once per ready job, using the bounded parallel workflow below:
   - Omit both image inclusion arguments when `images` is empty.
   - Pass `referenced_image_paths` containing all normalized image paths when images are present.
   - Never pass both `referenced_image_paths` and conversation-image inclusion.
7. Generate several distinct jobs with separate calls. Do not use one multi-subject image as a substitute for multiple requested assets.
8. Copy the generated file from its returned `$CODEX_HOME/generated_images/...` path to the exact `output_path`. Create the output directory if needed. Do not overwrite unless `--force` was authorized.
9. Inspect each saved result. Check subject, composition, text, constraints, and avoid items. Retry only with one targeted prompt change when the output materially violates the job.
10. Write `run-<timestamp>.json` in the output directory with each job ID, final prompt, output path, and completed/failed/skipped status.
11. Report all saved paths and note that built-in subscription image generation was used.

## Parallel execution

- Respect normalized `parallelism` from 1 through 10. Every job is one independent prompt and one call.
- Prefer one `functions.exec` orchestration call per wave. Inside it, start one `tools.image_gen__imagegen(...)` promise per job and await the wave with `Promise.allSettled`. This uses image-generation calls directly and is not limited by collaboration-agent slots.
- Start the orchestration source with `// @exec: {"yield_time_ms": 120000, "max_output_tokens": 12000}`. If it yields a running cell ID, resume it with `functions.wait` using `yield_time_ms: 120000` until complete.
- For a new image, pass only `{prompt}`. For a job with local inputs, pass `{prompt, referenced_image_paths}`. Never pass both `referenced_image_paths` and `num_last_images_to_include`.
- Emit a small result record for every promise and forward successful results with `generatedImage(result)`. Preserve the input order so results can be mapped back to exact `output_path` values.
- Use waves of `jobs.slice(offset, offset + parallelism)`. Do not start more than 10 image-generation promises in one wave.
- The configured value is requested client concurrency. The image service can still queue or throttle requests; describe that distinction instead of claiming guaranteed simultaneous GPU execution.
- If nested image-generation orchestration is unavailable, fall back to direct image-generation calls, report the actual concurrency used, and never switch to an API-key path.
- Keep file copying, manifest writing, and final inspection in the parent task to avoid write conflicts.
- Never claim parallel execution unless the calls were started before the wave was awaited.

Minimal orchestration shape for one prepared `wave`:

```js
const settled = await Promise.allSettled(wave.map(({ id, prompt, paths }) =>
  tools.image_gen__imagegen(paths.length
    ? { prompt, referenced_image_paths: paths }
    : { prompt })
));
settled.forEach((entry, index) => {
  if (entry.status === "fulfilled") {
    text(JSON.stringify({ id: wave[index].id, ok: true, output_hint: entry.value.output_hint }));
    generatedImage(entry.value);
  } else {
    text(JSON.stringify({ id: wave[index].id, ok: false, error: String(entry.reason) }));
  }
});
```

## Built-in constraints

- Treat `aspect_ratio` as prompt guidance; the built-in tool does not expose an exact output-size parameter.
- Use one built-in call per job. Ten jobs with `parallelism: 10` start ten calls in the same wave.
- Do not support masks in this workflow. Use a clear edit prompt and invariants instead.
- For a transparent-background request, follow the built-in-first chroma-key workflow from the system `imagegen` skill. Ask before any API/CLI fallback.
- If built-in image generation is unavailable or fails, report that fact. Do not silently switch to an API-key path.
- Built-in image generation consumes the user's ChatGPT/Codex usage limits. Do not create unrequested extra jobs.

## Run record

For each job, keep `id`, `tool_prompt`, `output_path`, the returned generated-image path, status, and any error. The run manifest must make partial failures retryable without regenerating successful outputs.
