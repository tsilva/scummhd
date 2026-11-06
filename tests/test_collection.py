from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from PIL import Image

from scummvision.cli import (
    GAME, dataset_writer, digest, import_catalog, import_run,
    read_rows, review, safe_file, verify, write_json,
)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "dataset"
        self.run = self.root / "source"
        (self.run / "screenshots").mkdir(parents=True)
        self.data = self.image()
        self.entry = self.screenshot(self.data)
        self.make_run([self.entry])

    def test_dependency_policy_is_portable(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        config = tomllib.loads((root / "uv.toml").read_text())
        lock = tomllib.loads((root / "uv.lock").read_text())
        self.assertEqual(config["exclude-newer"], "7 days")
        self.assertEqual(config["exclude-newer"], project["tool"]["uv"]["exclude-newer"])
        self.assertNotIn("exclude-newer-package", lock["options"])
        self.assertEqual(lock["options"]["exclude-newer-span"], "P7D")

    def image(self, compression=6):
        out = BytesIO()
        image = Image.new("RGB", (16, 12), "navy")
        image.putpixel((3, 5), (200, 120, 50))
        image.save(out, "PNG", compress_level=compression)
        return out.getvalue()

    def screenshot(self, data, frames=True):
        sha = digest(data)
        relative = f"screenshots/screenshot-{sha}.png"
        (self.run / relative).write_bytes(data)
        return {"id": "screenshot-" + sha, "path": relative,
                "sha256": sha, "bytes": len(data), "mime_type": "image/png",
                "frames": [{"id": "frame-1", "sessionId": "session-a",
                            "timestamp": "2026-11-05T10:00:00Z", "width": 16,
                            "height": 12, "actionId": "action-a", "step": 0}] if frames else []}

    def make_run(self, entries, game=GAME):
        write_json(self.run / "run.json", {"schema_version": 2, "game_id": game,
                   "run_id": "run-a", "status": "completed"})
        write_json(self.run / "screenshots/index.json", {"schema_version": 1, "screenshots": entries})

    def test_import_preserves_bytes_provenance_and_is_idempotent(self):
        before = (self.run / self.entry["path"]).read_bytes()
        first = import_run(self.run, self.output)
        manifest = (self.output / "manifest.jsonl").read_bytes()
        second = import_run(self.run, self.output)
        self.assertEqual(first, second)
        self.assertEqual(manifest, (self.output / "manifest.jsonl").read_bytes())
        row, = read_rows(self.output)
        self.assertEqual((self.output / row["path"]).read_bytes(), before)
        self.assertEqual(row["provenance"][0]["frames"], self.entry["frames"])
        self.assertFalse(row["training_eligible"])
        self.assertEqual(row["split"], "unassigned")
        self.assertNotIn(str(self.run), manifest.decode())
        self.assertTrue(verify(self.output)["verified"])

    def test_identical_images_share_storage_and_keep_frame_references(self):
        other = json.loads(json.dumps(self.entry))
        other["frames"][0]["id"] = "frame-2"
        self.make_run([self.entry, other])
        self.assertEqual(import_run(self.run, self.output)["unique_files"], 1)
        self.assertEqual(len(read_rows(self.output)[0]["provenance"]), 2)

    def test_different_encodings_of_same_pixels_remain_preserved(self):
        other = self.screenshot(self.image(compression=0))
        self.make_run([self.entry, other])
        result = import_run(self.run, self.output)
        self.assertEqual(result["unique_files"], 2)
        self.assertEqual(result["unique_pixel_images"], 1)
        self.assertEqual(result["pixel_duplicate_files"], 1)

    def test_unattributed_images_are_quarantined_without_copying(self):
        self.entry["frames"] = []
        self.make_run([self.entry])
        result = import_run(self.run, self.output)
        self.assertEqual(result["unique_files"], 0)
        self.assertEqual(result["quarantined_source_entries"], 1)
        self.assertEqual(import_run(self.run, self.output), result)
        self.assertTrue(verify(self.output)["verified"])

    def test_unknown_run_schema_is_rejected(self):
        metadata = json.loads((self.run / "run.json").read_text())
        metadata["schema_version"] = 999
        write_json(self.run / "run.json", metadata)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            import_run(self.run, self.output)

    def test_wrong_game_is_rejected_before_dataset_creation(self):
        self.make_run([self.entry], game="beneath-a-steel-sky")
        with self.assertRaisesRegex(ValueError, "not Flight"):
            import_run(self.run, self.output)
        self.assertFalse(self.output.exists())

    def test_corrupt_input_is_rejected(self):
        (self.run / self.entry["path"]).write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "checksum"):
            import_run(self.run, self.output)
        self.assertFalse((self.output / "manifest.jsonl").exists())

    def test_frame_dimensions_must_match_decoded_image(self):
        self.entry["frames"][0]["width"] = 100
        self.make_run([self.entry])
        with self.assertRaisesRegex(ValueError, "width"):
            import_run(self.run, self.output)

    def test_path_traversal_and_symlinks_are_rejected(self):
        with self.assertRaises(ValueError):
            safe_file(self.run, "../outside.png")
        with self.assertRaises(ValueError):
            safe_file(self.run, str(self.run / self.entry["path"]))
        (self.run / "link.png").symlink_to(self.run / self.entry["path"])
        with self.assertRaises(ValueError):
            safe_file(self.run, "link.png")

    def test_tampering_and_orphans_are_detected(self):
        import_run(self.run, self.output)
        (self.output / "frames/orphan.png").write_bytes(self.data)
        with self.assertRaisesRegex(ValueError, "Unindexed"):
            verify(self.output)
        (self.output / "frames/orphan.png").unlink()
        row, = read_rows(self.output)
        (self.output / row["path"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "Corrupt"):
            verify(self.output)

    def test_lock_does_not_allow_concurrent_import(self):
        with dataset_writer(self.output):
            with self.assertRaisesRegex(ValueError, "locked"):
                import_run(self.run, self.output)
        self.assertFalse((self.output / ".import.lock").exists())

    def test_review_has_local_labeling_controls_and_embedded_inventory(self):
        import_run(self.run, self.output)
        result = review(self.output)
        text = Path(result["review"]).read_text()
        self.assertIn('filter-subtitles', text)
        self.assertIn('filter-cutscene', text)
        self.assertIn(self.entry["sha256"], text)
        self.assertNotIn('<script src=', text)
        payload = text.split('<script type="application/json" id="dataset">')[1].split('</script>')[0]
        self.assertEqual(json.loads(payload)['frames'][0]['labels'], {'has_subtitles': None, 'is_cutscene': None})
        self.assertNotIn(str(self.run), text)

    def test_catalog_download_is_pinned_and_cached_on_reimport(self):
        sha = digest(self.data)
        url = f"https://scummvm-games.tsilva.eu/artwork/{sha}/shot.png"
        spec = self.root / "catalog.json"
        write_json(spec, {"schema_version": 1, "game_id": GAME, "source_id": "catalog-a",
                         "images": [{"url": url, "sha256": sha, "bytes": len(self.data),
                                     "width": 16, "height": 12, "logical_path": "/shot.png"}]})

        @contextmanager
        def response(*args, **kwargs):
            stream = BytesIO(self.data)
            stream.geturl = lambda: url
            yield stream

        with patch("scummvision.cli.urlopen", side_effect=response) as download:
            import_catalog(spec, self.output)
            import_catalog(spec, self.output)
            self.assertEqual(download.call_count, 1)
        self.assertTrue(verify(self.output)["verified"])


if __name__ == "__main__":
    unittest.main()
