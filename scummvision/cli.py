"""Collect original screenshots; never generate training targets or play games."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image

GAME = "flight-of-the-amazon-queen"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = ROOT / "data" / GAME
DEFAULT_SOURCE = ROOT / "sources" / "scummweb-queen.json"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def image_info(data: bytes):
    with Image.open(BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Only PNG, JPEG and WebP captures are supported")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Animated images must be imported as explicit frames")
        image.load()
        canonical = image.convert("RGBA")
        width, height = image.size
        pixel_hash = digest(f"{width}x{height}:RGBA:".encode() + canonical.tobytes())
        gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = gray.tobytes()
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
        return {
            "width": width, "height": height,
            "mime_type": Image.MIME[image.format],
            "extension": {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format],
            "pixel_sha256": pixel_hash, "dhash64": f"{bits:016x}",
        }


def read_rows(root: Path):
    path = root / "manifest.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Manifest contains duplicate IDs")
    return rows


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Image paths must be relative and cannot traverse parents")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Image path escapes its source root or is a symlink")
    if not candidate.is_file():
        raise ValueError(f"Missing source image: {relative}")
    return candidate


def bounded_read(path: Path) -> bytes:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 32 MiB collection limit")
    return path.read_bytes()


@contextmanager
def dataset_writer(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root / ".import.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Dataset is locked; check the active collector before removing .import.lock") from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


class Dataset:
    def __init__(self, root: Path):
        self.root = root
        self.rows = {row["id"]: row for row in read_rows(root)}
        for row in self.rows.values():
            row.setdefault("labels", {"has_subtitles": None, "is_cutscene": None})
        self.sources = read_json(root / "sources.json") if (root / "sources.json").exists() else {}
        self.quarantine = read_json(root / "quarantine.json") if (root / "quarantine.json").exists() else []

    def add(self, data: bytes, expected: dict, provenance: dict):
        sha = digest(data)
        if not HASH.fullmatch(str(expected.get("sha256", ""))) or sha != expected["sha256"]:
            raise ValueError("Image checksum mismatch")
        if len(data) != expected["bytes"]:
            raise ValueError("Image byte count mismatch")
        info = image_info(data)
        for field in ("width", "height", "mime_type"):
            if expected.get(field) is not None and info[field] != expected[field]:
                raise ValueError(f"Image {field} disagrees with source metadata")
        for frame in provenance.get("frames", []):
            for field in ("width", "height"):
                if frame.get(field) is not None and frame[field] != info[field]:
                    raise ValueError(f"Frame {field} disagrees with decoded image")
        frame_id = f"frame-{sha}"
        destination = self.root / "frames" / (sha + info.pop("extension"))
        destination.parent.mkdir(exist_ok=True, mode=0o700)
        if destination.exists():
            if destination.is_symlink() or digest(bounded_read(destination)) != sha:
                raise ValueError("Existing dataset image is corrupt or linked")
        else:
            with destination.open("xb") as stream:
                stream.write(data)
            destination.chmod(0o600)
        row = self.rows.setdefault(frame_id, {
            "schema_version": 1, "id": frame_id, "game_id": GAME,
            "path": destination.relative_to(self.root).as_posix(),
            "sha256": sha, "bytes": len(data), **info,
            "original_capture": True, "native_resolution": None,
            "review_status": "unreviewed", "scene_id": None,
            "split": "unassigned", "target": None, "training_eligible": False,
            "labels": {"has_subtitles": None, "is_cutscene": None},
            "provenance": [],
        })
        if provenance not in row["provenance"]:
            row["provenance"].append(provenance)

    def save(self):
        rows = sorted(self.rows.values(), key=lambda row: row["id"])
        atomic_write(self.root / "manifest.jsonl", "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        write_json(self.root / "sources.json", self.sources)
        write_json(self.root / "quarantine.json", self.quarantine)
        summary = summarize(rows, self.sources, self.quarantine)
        write_json(self.root / "summary.json", summary)
        return summary


def summarize(rows, sources, quarantine):
    pixel_counts = Counter(row["pixel_sha256"] for row in rows)
    return {
        "schema_version": 1, "game_id": GAME,
        "unique_files": len(rows), "unique_pixel_images": len(pixel_counts),
        "pixel_duplicate_files": sum(count - 1 for count in pixel_counts.values()),
        "bytes": sum(row["bytes"] for row in rows), "sources": len(sources),
        "quarantined_source_entries": len(quarantine),
        "dimensions": dict(Counter(f'{row["width"]}x{row["height"]}' for row in rows)),
        "encodings": dict(Counter(row["mime_type"] for row in rows)),
        "review_status": dict(Counter(row["review_status"] for row in rows)),
        "splits": dict(Counter(row["split"] for row in rows)),
        "paired_targets": sum(row["target"] is not None for row in rows),
        "training_eligible": sum(row["training_eligible"] for row in rows),
        "labels": {
            field: dict(Counter("unknown" if row.get("labels", {}).get(field) is None
                                else "yes" if row["labels"][field] else "no" for row in rows))
            for field in ("has_subtitles", "is_cutscene")
        },
    }


def import_run(run: Path, output: Path):
    run = run.resolve()
    manifest_path, index_path = run / "run.json", run / "screenshots" / "index.json"
    metadata, index = read_json(manifest_path), read_json(index_path)
    if metadata.get("schema_version") not in {1, 2} or index.get("schema_version") != 1:
        raise ValueError("Unsupported AgentSCUMM run/index schema")
    if metadata.get("game_id") != GAME:
        raise ValueError("Run is not Flight of the Amazon Queen")
    if not isinstance(metadata.get("run_id"), str) or not metadata["run_id"]:
        raise ValueError("Run has no stable run ID")
    source_id = "agentscumm:" + metadata["run_id"]
    with dataset_writer(output):
        dataset = Dataset(output)
        snapshot = {"run_sha256": digest(manifest_path.read_bytes()), "index_sha256": digest(index_path.read_bytes())}
        source = dataset.sources.setdefault(source_id, {
            "source_type": "agentscumm_run", "run_id": metadata["run_id"],
            "game_id": GAME, "snapshots": [],
            "note": "Conversation checkout revision does not establish the deployed game revision.",
        })
        if snapshot not in source["snapshots"]:
            source["snapshots"].append(snapshot)
        source["run_status"] = metadata.get("status", "unknown")
        source["run_schema_version"] = metadata["schema_version"]
        source["started_at"] = metadata.get("started_at")
        source["recorded_through"] = metadata.get("recorded_through")
        for entry in index["screenshots"]:
            frames = entry.get("frames", [])
            if not frames or any(not frame.get("id") or not frame.get("sessionId") for frame in frames):
                rejected = {"source_id": source_id, "screenshot_id": entry["id"],
                            "sha256": entry["sha256"], "reason": "missing_explicit_frame_provenance"}
                if rejected not in dataset.quarantine:
                    dataset.quarantine.append(rejected)
                continue
            data = bounded_read(safe_file(run, entry["path"]))
            preserved_frames = [{key: frame.get(key) for key in
                                 ("id", "sessionId", "timestamp", "actionId", "step", "width", "height")}
                                for frame in frames]
            dataset.add(data, entry, {
                "source_id": source_id, "source_type": "agentscumm_run",
                "screenshot_id": entry["id"], "source_path": entry["path"],
                "capture_group": source_id, "frames": preserved_frames,
            })
        return dataset.save()


def import_catalog(spec_path: Path, output: Path):
    spec = read_json(spec_path)
    if spec.get("schema_version") != 1 or spec.get("game_id") != GAME:
        raise ValueError("Unsupported catalog source or game")
    with dataset_writer(output):
        dataset = Dataset(output)
        source_id = spec["source_id"]
        dataset.sources[source_id] = spec
        for entry in spec["images"]:
            url = urlparse(entry["url"])
            if url.scheme != "https" or url.hostname != "scummvm-games.tsilva.eu" or url.username or url.password or url.port:
                raise ValueError("Catalog images must use the reviewed HTTPS bucket origin")
            if not HASH.fullmatch(entry["sha256"]) or f'/artwork/{entry["sha256"]}/' not in url.path:
                raise ValueError("Catalog URL is not content-addressed")
            cached = [row for row in dataset.rows.values() if row["sha256"] == entry["sha256"]]
            if cached:
                data = bounded_read(safe_file(output, cached[0]["path"]))
            else:
                request = Request(entry["url"], headers={"User-Agent": "SCUMMvision/0.1 dataset collector"})
                with urlopen(request, timeout=30) as response:
                    if response.geturl() != entry["url"]:
                        raise ValueError("Pinned catalog downloads cannot redirect")
                    data = response.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("Catalog image exceeds 32 MiB")
            dataset.add(data, entry, {
                "source_id": source_id, "source_type": "scummweb_catalog",
                "source_url": entry["url"], "logical_path": entry["logical_path"],
                "capture_group": source_id, "frames": [],
            })
        return dataset.save()


def verify(output: Path):
    rows = read_rows(output)
    if not (output / "manifest.jsonl").is_file():
        raise ValueError("Dataset manifest does not exist; import a source first")
    sources, quarantine = read_json(output / "sources.json"), read_json(output / "quarantine.json")
    expected_paths = set()
    for row in rows:
        data = bounded_read(safe_file(output, row["path"]))
        if digest(data) != row["sha256"] or len(data) != row["bytes"] or row["id"] != "frame-" + row["sha256"]:
            raise ValueError(f'Corrupt image or identity: {row["id"]}')
        info = image_info(data)
        for key in ("width", "height", "mime_type", "pixel_sha256", "dhash64"):
            if info[key] != row[key]:
                raise ValueError(f'Image metadata mismatch: {row["id"]}/{key}')
        if row["game_id"] != GAME or row["schema_version"] != 1:
            raise ValueError("Manifest game or schema mismatch")
        if not row["provenance"] or any(p["source_id"] not in sources for p in row["provenance"]):
            raise ValueError("Missing source provenance")
        if row["training_eligible"] or row["target"] is not None or row["split"] != "unassigned":
            raise ValueError("Collection-only dataset unexpectedly contains training assignments")
        labels = row.get("labels", {"has_subtitles": None, "is_cutscene": None})
        if set(labels) != {"has_subtitles", "is_cutscene"} or any(value is not None and type(value) is not bool for value in labels.values()):
            raise ValueError("Invalid subtitle/cutscene labels")
        expected_paths.add(row["path"])
    frames_directory = output / "frames"
    actual_paths = {p.relative_to(output).as_posix() for p in frames_directory.iterdir() if p.is_file()} if frames_directory.exists() else set()
    if actual_paths != expected_paths:
        raise ValueError("Unindexed images found; finish/retry the interrupted import before verification")
    summary = summarize(rows, sources, quarantine)
    if summary != read_json(output / "summary.json"):
        raise ValueError("Summary does not match the manifest")
    return {"verified": True, **summary}


def review(output: Path):
    from .curation import review_gallery
    return review_gallery(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Local dataset directory (default: data/flight-of-the-amazon-queen)")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("import-run", help="Import an existing AgentSCUMM run without touching a live game")
    run.add_argument("run", type=Path, help="Directory containing run.json and screenshots/index.json")
    catalog = commands.add_parser("import-catalog", help="Fetch only the three pinned original ScummWEB catalog screenshots")
    catalog.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    commands.add_parser("verify", help="Recheck image bytes, metadata, provenance and inventory")
    commands.add_parser("stats", help="Summarize the current local manifest")
    commands.add_parser("review", help="Write a local gallery with labels, filters and diversity selection")
    dedupe = commands.add_parser("dedupe", help="Group similar frames without deleting originals")
    dedupe.add_argument("--hamming", type=int, default=8)
    dedupe.add_argument("--pixel-mae", type=float, default=8.0)
    labels = commands.add_parser("import-labels", help="Apply reviewed labels exported by the gallery")
    labels.add_argument("labels", type=Path)
    select = commands.add_parser("select", help="Export a filtered set, optionally one frame per similarity group")
    select.add_argument("--subtitles", choices=["yes", "no", "unknown"])
    select.add_argument("--cutscene", choices=["yes", "no", "unknown"])
    select.add_argument("--diverse", action="store_true")
    select.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        output = args.dataset.resolve()
        if args.command == "import-run":
            result = import_run(args.run, output)
        elif args.command == "import-catalog":
            result = import_catalog(args.source, output)
        elif args.command == "verify":
            result = verify(output)
        elif args.command == "review":
            result = review(output)
        elif args.command == "dedupe":
            from .curation import dedupe
            result = dedupe(output, args.hamming, args.pixel_mae)
        elif args.command == "import-labels":
            from .curation import import_labels
            result = import_labels(output, args.labels)
        elif args.command == "select":
            from .curation import select_frames
            result = select_frames(output, args.subtitles, args.cutscene, args.diverse, args.output)
        else:
            result = summarize(read_rows(output), read_json(output / "sources.json"), read_json(output / "quarantine.json"))
    except (ValueError, OSError, KeyError, TypeError, Image.DecompressionBombError) as error:
        parser.exit(1, f"scummvision: {error}\n")
    print(json.dumps(result, indent=2))
    return 0
