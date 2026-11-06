from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from scummvision.cli import GAME, digest, import_run, read_rows, verify, write_json
from scummvision.curation import dedupe, fingerprint, import_labels, select_frames


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'run'
        self.dataset = self.root / 'dataset'
        (self.source / 'screenshots').mkdir(parents=True)
        entries = []
        for index, gray in enumerate([10, 15, 20]):
            image = Image.new('RGB', (32, 24), (gray, gray, gray))
            stream = BytesIO(); image.save(stream, 'PNG'); data = stream.getvalue()
            sha = digest(data)
            path = f'screenshots/{sha}.png'
            (self.source / path).write_bytes(data)
            entries.append({'id': 'screenshot-' + sha, 'path': path, 'sha256': sha,
                            'bytes': len(data), 'mime_type': 'image/png',
                            'frames': [{'id': f'frame-{index}', 'sessionId': 'session-a',
                                        'timestamp': f'2026-11-05T10:00:0{index}Z',
                                        'width': 32, 'height': 24}]})
        write_json(self.source / 'run.json', {'schema_version': 2, 'game_id': GAME, 'run_id': 'run-a'})
        write_json(self.source / 'screenshots/index.json', {'schema_version': 1, 'screenshots': entries})
        import_run(self.source, self.dataset)
        self.rows = sorted(read_rows(self.dataset), key=lambda row: row['provenance'][0]['frames'][0]['timestamp'])

    def batch(self, annotations):
        path = self.root / 'labels.json'
        write_json(path, {'schema_version': 1, 'game_id': GAME,
                         'dataset_fingerprint': fingerprint(self.rows), 'annotations': annotations})
        return path

    def annotation(self, index, subtitles, cutscene):
        return {'frame_id': self.rows[index]['id'],
                'base_labels': {'has_subtitles': None, 'is_cutscene': None},
                'labels': {'has_subtitles': subtitles, 'is_cutscene': cutscene}}

    def test_similarity_does_not_chain_across_different_frames(self):
        before = {row['path']: (self.dataset / row['path']).read_bytes() for row in self.rows}
        result = dedupe(self.dataset, hamming=0, pixel_mae=6)
        self.assertEqual(result['representatives'], 2)
        groups = json.loads((self.dataset / 'diversity.json').read_text())['groups']
        self.assertEqual([len(group['members']) for group in groups], [2, 1])
        self.assertEqual(before, {path: (self.dataset / path).read_bytes() for path in before})
        self.assertTrue(verify(self.dataset)['verified'])

    def test_zero_threshold_preserves_visually_different_images(self):
        self.assertEqual(dedupe(self.dataset, 0, 0)['representatives'], 3)

    def test_label_roundtrip_is_idempotent_and_keeps_unknowns(self):
        labels = self.batch([self.annotation(0, True, False), self.annotation(1, False, None)])
        self.assertEqual(import_labels(self.dataset, labels)['updated_frames'], 2)
        manifest = (self.dataset / 'manifest.jsonl').read_bytes()
        self.assertEqual(import_labels(self.dataset, labels)['updated_frames'], 0)
        self.assertEqual(manifest, (self.dataset / 'manifest.jsonl').read_bytes())
        result = verify(self.dataset)
        self.assertEqual(result['labels']['has_subtitles'], {'yes': 1, 'no': 1, 'unknown': 1})
        self.assertEqual(result['labels']['is_cutscene'], {'no': 1, 'unknown': 2})

    def test_conflicting_labels_do_not_overwrite_newer_annotations(self):
        import_labels(self.dataset, self.batch([self.annotation(0, True, False)]))
        stale = self.batch([self.annotation(0, False, False)])
        before = (self.dataset / 'manifest.jsonl').read_bytes()
        with self.assertRaisesRegex(ValueError, 'conflict'):
            import_labels(self.dataset, stale)
        self.assertEqual(before, (self.dataset / 'manifest.jsonl').read_bytes())

    def test_invalid_batch_is_rejected_before_applying_any_labels(self):
        invalid = self.annotation(1, 'yes', False)
        path = self.batch([self.annotation(0, True, False), invalid])
        with self.assertRaisesRegex(ValueError, 'true, false or null'):
            import_labels(self.dataset, path)
        self.assertTrue(all(row['labels']['has_subtitles'] is None for row in read_rows(self.dataset)))

    def test_filtered_diversity_chooses_a_matching_member_not_only_the_representative(self):
        dedupe(self.dataset, 0, 6)
        import_labels(self.dataset, self.batch([self.annotation(0, False, False), self.annotation(1, True, False)]))
        result = select_frames(self.dataset, subtitles='yes', cutscene='no', diverse=True)
        selected = json.loads(Path(result['selection']).read_text())['frames']
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['frame_id'], self.rows[1]['id'])

    def test_unknown_does_not_count_as_no(self):
        result = select_frames(self.dataset, subtitles='no')
        self.assertEqual(result['selected_frames'], 0)
        result = select_frames(self.dataset, subtitles='unknown')
        self.assertEqual(result['selected_frames'], 3)

    def test_selection_cannot_overwrite_images_or_metadata(self):
        with self.assertRaisesRegex(ValueError, 'JSON'):
            select_frames(self.dataset, output=self.dataset / self.rows[0]['path'])
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            select_frames(self.dataset, output=self.dataset / 'summary.json')


if __name__ == '__main__':
    unittest.main()
