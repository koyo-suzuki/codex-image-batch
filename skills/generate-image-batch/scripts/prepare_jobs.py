#!/usr/bin/env python3
"""Validate and normalize Codex built-in image-generation batch jobs."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VALID_MODES = {"generate", "edit"}
ASPECT_RATIO = re.compile(r"^[1-9]\d*:[1-9]\d*$")
UNSUPPORTED_API_FIELDS = {"mask", "model", "n", "output_format", "quality", "size"}


class ConfigError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def safe_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"[^\w.-]+", "-", normalized, flags=re.UNICODE)
    return normalized.strip("-")[:100] or "image"


def normalize_string_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    require(isinstance(value, list), f"{label} は文字列の配列にしてください。")
    require(all(isinstance(item, str) and item.strip() for item in value), f"{label} に空の値があります。")
    return [item.strip() for item in value]


def normalize_images(value: object, base_dir: Path, label: str) -> list[dict[str, str]]:
    if value is None:
        return []
    require(isinstance(value, list), f"{label} は画像の配列にしてください。")
    images: list[dict[str, str]] = []

    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if isinstance(item, str):
            raw_path = item
            role = "参照画像"
        else:
            require(isinstance(item, dict), f"{item_label} はパス文字列またはオブジェクトにしてください。")
            raw_path = item.get("path")
            role = item.get("role", "参照画像")

        require(isinstance(raw_path, str) and raw_path.strip(), f"{item_label}.path を指定してください。")
        require(isinstance(role, str) and role.strip(), f"{item_label}.role を文字列で指定してください。")

        image_path = (base_dir / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        require(image_path.exists(), f"参照画像が見つかりません: {image_path}")
        require(image_path.is_file(), f"参照画像がファイルではありません: {image_path}")
        require(image_path.suffix.lower() in IMAGE_EXTENSIONS, f"PNG/JPEG/WebP以外の画像です: {image_path}")
        images.append({"path": str(image_path), "role": role.strip()})

    return images


def variant_name(filename: str, index: int, variants: int) -> str:
    file_path = Path(filename)
    require(file_path.name == filename, "output_name はフォルダを含まないファイル名にしてください。")
    require(file_path.suffix.lower() == ".png", "output_name は .png にしてください。")
    if variants == 1:
        return filename
    return f"{file_path.stem}-{index:02d}.png"


def build_prompt(job: dict[str, object], images: list[dict[str, str]], variant: int, variants: int) -> str:
    lines = [
        f"Asset ID: {job['id']}",
        f"Mode: {job['mode']}",
        f"Primary request: {job['prompt'].strip()}",
    ]
    if images:
        roles = "; ".join(f"Image {index}: {image['role']}" for index, image in enumerate(images, 1))
        lines.append(f"Input images: {roles}")
    if job.get("aspect_ratio"):
        lines.append(f"Composition/framing: target aspect ratio {job['aspect_ratio']}")
    constraints = job.get("constraints", [])
    avoid = job.get("avoid", [])
    if constraints:
        lines.append(f"Constraints: {'; '.join(constraints)}")
    if avoid:
        lines.append(f"Avoid: {'; '.join(avoid)}")
    if variants > 1:
        lines.append(f"Variant: {variant} of {variants}; make this a distinct visual alternative while preserving all requirements")
    if job["mode"] == "edit":
        lines.append("Edit invariant: change only what the primary request names; preserve every other visible detail")
    return "\n".join(lines)


def normalize_config(raw: object, config_path: Path, force: bool = False) -> dict[str, object]:
    require(isinstance(raw, dict), "設定ファイルのルートはJSONオブジェクトにしてください。")
    config_path = config_path.resolve()
    defaults = raw.get("defaults", {})
    jobs = raw.get("jobs")
    require(isinstance(defaults, dict), "defaults はJSONオブジェクトにしてください。")
    require(isinstance(jobs, list) and jobs, "jobs に1件以上のジョブを指定してください。")
    old_default_fields = UNSUPPORTED_API_FIELDS.intersection(defaults)
    require(not old_default_fields, f"API版の設定項目は使えません: {', '.join(sorted(old_default_fields))}")

    parallelism = raw.get("parallelism", 10)
    require(not isinstance(parallelism, bool) and isinstance(parallelism, int) and 1 <= parallelism <= 10, "parallelism は1〜10の整数にしてください。")

    base_dir = config_path.parent
    raw_output_dir = raw.get("output_dir", "outputs")
    require(isinstance(raw_output_dir, str) and raw_output_dir.strip(), "output_dir を文字列で指定してください。")
    output_dir = (base_dir / raw_output_dir).resolve() if not Path(raw_output_dir).is_absolute() else Path(raw_output_dir).resolve()
    require(output_dir == base_dir or base_dir in output_dir.parents, "output_dir は設定ファイルと同じフォルダ配下にしてください。")

    normalized: list[dict[str, object]] = []
    ids: set[str] = set()
    output_paths: set[str] = set()

    for job_index, item in enumerate(jobs):
        label = f"jobs[{job_index}]"
        require(isinstance(item, dict), f"{label} はJSONオブジェクトにしてください。")
        job = {**defaults, **item}
        old_job_fields = UNSUPPORTED_API_FIELDS.intersection(job)
        require(not old_job_fields, f"{label} にAPI版の設定項目があります: {', '.join(sorted(old_job_fields))}")

        job_id = job.get("id")
        prompt = job.get("prompt")
        mode = job.get("mode", "generate")
        variants = job.get("variants", 1)
        aspect_ratio = job.get("aspect_ratio")

        require(isinstance(job_id, str) and job_id.strip(), f"{label}.id を指定してください。")
        require(job_id not in ids, f"{label}.id \"{job_id}\" が重複しています。")
        ids.add(job_id)
        require(isinstance(prompt, str) and prompt.strip(), f"{label}.prompt を指定してください。")
        require(mode in VALID_MODES, f"{label}.mode は generate/edit のいずれかにしてください。")
        require(not isinstance(variants, bool) and isinstance(variants, int) and 1 <= variants <= 10, f"{label}.variants は1〜10の整数にしてください。")
        if aspect_ratio is not None:
            require(isinstance(aspect_ratio, str) and ASPECT_RATIO.fullmatch(aspect_ratio), f"{label}.aspect_ratio は 1:1 や 16:9 の形式にしてください。")

        images = normalize_images(job.get("images"), base_dir, f"{label}.images")
        require(mode != "edit" or images, f"{label} は edit のため images に編集対象を指定してください。")
        constraints = normalize_string_list(job.get("constraints"), f"{label}.constraints")
        avoid = normalize_string_list(job.get("avoid"), f"{label}.avoid")

        base_output_name = job.get("output_name", f"{safe_id(job_id)}.png")
        require(isinstance(base_output_name, str) and base_output_name.strip(), f"{label}.output_name を文字列で指定してください。")

        normalized_job = {
            "id": job_id.strip(),
            "prompt": prompt.strip(),
            "mode": mode,
            "aspect_ratio": aspect_ratio,
            "constraints": constraints,
            "avoid": avoid,
        }

        for variant in range(1, variants + 1):
            output_name = variant_name(base_output_name, variant, variants)
            output_path = (output_dir / output_name).resolve()
            require(str(output_path) not in output_paths, f"出力先が重複しています: {output_path}")
            output_paths.add(str(output_path))
            exists = output_path.exists()
            variant_id = job_id.strip() if variants == 1 else f"{job_id.strip()}-{variant:02d}"
            expanded = {
                "id": variant_id,
                "source_id": job_id.strip(),
                "mode": mode,
                "images": images,
                "output_path": str(output_path),
                "status": "ready" if force or not exists else "skipped",
                "skip_reason": None if force or not exists else "output_exists",
            }
            expanded["tool_prompt"] = build_prompt(normalized_job, images, variant, variants)
            normalized.append(expanded)

    ready_jobs = [job for job in normalized if job["status"] == "ready"]
    waves = [
        [job["id"] for job in ready_jobs[offset : offset + parallelism]]
        for offset in range(0, len(ready_jobs), parallelism)
    ]

    return {
        "config": str(config_path),
        "output_dir": str(output_dir),
        "parallelism": parallelism,
        "force": force,
        "waves": waves,
        "jobs": normalized,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex内蔵画像生成用のjobs.jsonを検証・正規化します。")
    parser.add_argument("--config", default="jobs.json", help="設定JSONのパス")
    parser.add_argument("--force", action="store_true", help="既存出力をready扱いにする")
    parser.add_argument("--json", action="store_true", help="正規化結果をJSONで出力")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    try:
        require(config_path.exists(), f"設定ファイルが見つかりません: {config_path}")
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        result = normalize_config(raw, config_path, force=args.force)
    except (ConfigError, json.JSONDecodeError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    ready = sum(job["status"] == "ready" for job in result["jobs"])
    skipped = len(result["jobs"]) - ready
    print(f"設定OK: {len(result['jobs'])}件 / ready {ready} / skipped {skipped} / 並列希望 {result['parallelism']}")
    for job in result["jobs"]:
        image_count = len(job["images"])
        print(f"- {job['id']}: {job['status']} / {job['mode']} / 画像 {image_count}枚 / {job['output_path']}")
    print("画像生成は行っていません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
