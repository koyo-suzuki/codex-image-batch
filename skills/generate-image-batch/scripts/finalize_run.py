#!/usr/bin/env python3
"""Save generated images and write a retryable batch run manifest."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


class FinalizeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizeError(message)


def decode_results(encoded: str) -> list[dict[str, object]]:
    try:
        raw = base64.b64decode(encoded, validate=True).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalizeError("生成結果データを読み取れません。") from error
    require(isinstance(payload, list), "生成結果は配列にしてください。")
    require(all(isinstance(item, dict) for item in payload), "生成結果の各項目はオブジェクトにしてください。")
    return payload


def finalize_results(
    results: list[dict[str, object]],
    output_dir: Path,
    *,
    force: bool = False,
    timestamp: str | None = None,
) -> dict[str, object]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    finalized: list[dict[str, object]] = []

    for item in results:
        record = dict(item)
        job_id = record.get("id")
        status = record.get("status")
        output_path_raw = record.get("output_path")
        require(isinstance(job_id, str) and job_id, "生成結果にidがありません。")
        require(status in {"completed", "failed", "skipped"}, f"{job_id}: statusが不正です。")
        require(isinstance(output_path_raw, str) and output_path_raw, f"{job_id}: output_pathがありません。")

        output_path = Path(output_path_raw).resolve()
        require(output_path == output_dir or output_dir in output_path.parents, f"{job_id}: output_pathが出力フォルダ外です。")

        if status == "completed":
            source_raw = record.get("generated_image_path")
            require(isinstance(source_raw, str) and source_raw, f"{job_id}: 生成画像パスがありません。")
            source_path = Path(source_raw).resolve()
            require(source_path.is_file(), f"{job_id}: 生成画像が見つかりません: {source_path}")
            require(source_path.suffix.lower() == ".png", f"{job_id}: 生成画像はPNGではありません。")
            if output_path.exists() and not force:
                record["status"] = "failed"
                record["error"] = "output_exists_during_finalize"
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, output_path)

        finalized.append(record)

    run_timestamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_path = output_dir / f"run-{run_timestamp}.json"
    manifest = {
        "dispatch_strategy": "burst",
        "requested_count": len(finalized),
        "completed": sum(item["status"] == "completed" for item in finalized),
        "failed": sum(item["status"] == "failed" for item in finalized),
        "skipped": sum(item["status"] == "skipped" for item in finalized),
        "jobs": finalized,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest_path": str(manifest_path), **manifest}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成画像をoutputsへ保存し、実行記録を作成します。")
    parser.add_argument("--results-base64", required=True, help="UTF-8 JSON配列をbase64化した生成結果")
    parser.add_argument("--output-dir", required=True, help="画像と実行記録の保存先")
    parser.add_argument("--force", action="store_true", help="既存画像を上書きする")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = finalize_results(
            decode_results(args.results_base64),
            Path(args.output_dir),
            force=args.force,
        )
    except (FinalizeError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
