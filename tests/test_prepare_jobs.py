import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/generate-image-batch/scripts/prepare_jobs.py"
SPEC = importlib.util.spec_from_file_location("prepare_jobs", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PrepareJobsTest(unittest.TestCase):
    def test_one_job_creates_one_output_and_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "jobs.json"
            raw = {
                "parallelism": 2,
                "jobs": [
                    {
                        "id": "商品 写真",
                        "prompt": "白背景の商品写真",
                        "aspect_ratio": "2:3",
                        "avoid": ["文字"],
                    }
                ],
            }
            result = MODULE.normalize_config(raw, config)
            self.assertEqual([job["id"] for job in result["jobs"]], ["商品 写真"])
            self.assertTrue(result["jobs"][0]["output_path"].endswith("商品-写真.png"))
            self.assertIn("target aspect ratio 2:3", result["jobs"][0]["tool_prompt"])

    def test_rejects_variants_with_job_split_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {"jobs": [{"id": "sample", "prompt": "sample", "variants": 2}]}
            with self.assertRaisesRegex(MODULE.ConfigError, "プロンプトごとに jobs を分けて"):
                MODULE.normalize_config(raw, config)

    def test_edit_requires_image(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            with self.assertRaisesRegex(MODULE.ConfigError, "編集対象"):
                MODULE.normalize_config({"jobs": [{"id": "edit", "prompt": "背景変更", "mode": "edit"}]}, config)

    def test_reference_image_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "reference.png"
            image.write_bytes(b"test")
            config = root / "jobs.json"
            raw = {
                "jobs": [
                    {
                        "id": "poster",
                        "prompt": "広告画像",
                        "images": [{"path": "reference.png", "role": "商品参照"}],
                    }
                ]
            }
            result = MODULE.normalize_config(raw, config)
            self.assertEqual(result["jobs"][0]["images"][0]["path"], str(image.resolve()))
            self.assertIn("Image 1: 商品参照", result["jobs"][0]["tool_prompt"])

    def test_existing_output_is_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "outputs"
            output.mkdir()
            (output / "sample.png").write_bytes(b"existing")
            config = root / "jobs.json"
            raw = {"jobs": [{"id": "sample", "prompt": "sample"}]}
            result = MODULE.normalize_config(raw, config)
            forced = MODULE.normalize_config(raw, config, force=True)
            self.assertEqual(result["jobs"][0]["status"], "skipped")
            self.assertEqual(forced["jobs"][0]["status"], "ready")

    def test_rejects_old_api_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {"defaults": {"model": "gpt-image-2"}, "jobs": [{"id": "sample", "prompt": "sample"}]}
            with self.assertRaisesRegex(MODULE.ConfigError, "API版"):
                MODULE.normalize_config(raw, config)

    def test_output_directory_must_stay_under_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {"output_dir": "../outside", "jobs": [{"id": "sample", "prompt": "sample"}]}
            with self.assertRaisesRegex(MODULE.ConfigError, "同じフォルダ配下"):
                MODULE.normalize_config(raw, config)

    def test_accepts_ten_parallel_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {"parallelism": 10, "jobs": [{"id": "sample", "prompt": "sample"}]}
            result = MODULE.normalize_config(raw, config)
            self.assertEqual(result["parallelism"], 10)

    def test_rejects_more_than_ten_parallel_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {"parallelism": 11, "jobs": [{"id": "sample", "prompt": "sample"}]}
            with self.assertRaisesRegex(MODULE.ConfigError, "1〜10"):
                MODULE.normalize_config(raw, config)

    def test_builds_ten_job_waves(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "jobs.json"
            raw = {
                "parallelism": 10,
                "jobs": [
                    {"id": f"sample-{index}", "prompt": "sample"}
                    for index in range(11)
                ],
            }
            result = MODULE.normalize_config(raw, config)
            self.assertEqual([len(wave) for wave in result["waves"]], [10, 1])


if __name__ == "__main__":
    unittest.main()
