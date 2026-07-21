import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/generate-image-batch/scripts/finalize_run.py"
SPEC = importlib.util.spec_from_file_location("finalize_run", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FinalizeRunTest(unittest.TestCase):
    def test_decodes_base64_results(self):
        records = [{"id": "one", "status": "failed", "output_path": "/tmp/one.png"}]
        encoded = base64.b64encode(json.dumps(records).encode()).decode()
        self.assertEqual(MODULE.decode_results(encoded), records)

    def test_copies_success_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "generated.png"
            source.write_bytes(b"png")
            output_dir = root / "outputs"
            output = output_dir / "image-1.png"
            result = MODULE.finalize_results(
                [
                    {
                        "id": "image-1",
                        "tool_prompt": "sample",
                        "status": "completed",
                        "generated_image_path": str(source),
                        "output_path": str(output),
                        "dispatched_at_ms": 0,
                        "completed_at_ms": 100,
                    }
                ],
                output_dir,
                timestamp="20260722-120000",
            )
            self.assertEqual(output.read_bytes(), b"png")
            self.assertEqual(result["completed"], 1)
            manifest = json.loads((output_dir / "run-20260722-120000.json").read_text())
            self.assertEqual(manifest["dispatch_strategy"], "burst")

    def test_does_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "generated.png"
            source.write_bytes(b"new")
            output_dir = root / "outputs"
            output_dir.mkdir()
            output = output_dir / "image-1.png"
            output.write_bytes(b"old")
            result = MODULE.finalize_results(
                [{"id": "image-1", "status": "completed", "generated_image_path": str(source), "output_path": str(output)}],
                output_dir,
                timestamp="20260722-120001",
            )
            self.assertEqual(output.read_bytes(), b"old")
            self.assertEqual(result["failed"], 1)

    def test_rejects_output_outside_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "generated.png"
            source.write_bytes(b"png")
            with self.assertRaisesRegex(MODULE.FinalizeError, "出力フォルダ外"):
                MODULE.finalize_results(
                    [{"id": "image-1", "status": "completed", "generated_image_path": str(source), "output_path": str(root / "outside.png")}],
                    root / "outputs",
                    timestamp="20260722-120002",
                )


if __name__ == "__main__":
    unittest.main()
