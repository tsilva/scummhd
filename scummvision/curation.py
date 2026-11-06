"""Conservative diversity grouping and explicit, reviewable content labels."""

from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .cli import (
    Dataset, GAME, atomic_write, dataset_writer, digest, read_json, read_rows,
    safe_file, verify, write_json,
)

FIELDS = ("has_subtitles", "is_cutscene")
UNKNOWN = dict.fromkeys(FIELDS)


def fingerprint(rows):
    return digest("\n".join(sorted(row["id"] + ":" + row["pixel_sha256"] for row in rows)).encode())


def chronology(row):
    first = min((frame.get("timestamp") or "~" for source in row["provenance"]
                 for frame in source.get("frames", [])), default="~")
    return first, row["id"]


def groups_for(root, rows, required=False):
    path = root / "diversity.json"
    if not path.exists():
        if required:
            raise ValueError("Run dedupe before requesting a diverse selection")
        return {row["id"]: row["id"] for row in rows}
    grouping = read_json(path)
    if grouping.get("dataset_fingerprint") != fingerprint(rows):
        raise ValueError("Diversity groups are stale; rerun dedupe after importing new images")
    mapping = {member["frame_id"]: group["representative"]
               for group in grouping["groups"] for member in group["members"]}
    if set(mapping) != {row["id"] for row in rows}:
        raise ValueError("Diversity groups do not cover the dataset")
    return mapping


def dedupe(root, hamming=8, pixel_mae=8.0):
    if not 0 <= hamming <= 64 or not 0 <= pixel_mae <= 255:
        raise ValueError("Hamming threshold must be 0–64 and pixel MAE must be 0–255")
    with dataset_writer(root):
        verify(root)
        rows = sorted(read_rows(root), key=chronology)
        representatives, groups = [], []
        for row in rows:
            with Image.open(safe_file(root, row["path"])) as image:
                thumbnail = image.convert("RGB").resize((32, 24), Image.Resampling.LANCZOS)
            image_hash = int(row["dhash64"], 16)
            match = None
            for index, (representative, candidate, candidate_hash) in enumerate(representatives):
                # Compare only against a group's representative to avoid chains
                # of individually similar images merging different scenes.
                if row["width"] * representative["height"] != row["height"] * representative["width"]:
                    continue
                distance = (image_hash ^ candidate_hash).bit_count()
                if distance > hamming:
                    continue
                error = sum(ImageStat.Stat(ImageChops.difference(thumbnail, candidate)).mean) / 3
                if error <= pixel_mae and (match is None or (error, distance) < match[:2]):
                    match = (error, distance, index)
            member = {"frame_id": row["id"], "hamming": 0, "pixel_mae": 0.0}
            if match is None:
                groups.append({"representative": row["id"], "members": [member]})
                representatives.append((row, thumbnail, image_hash))
            else:
                error, distance, index = match
                member.update(hamming=distance, pixel_mae=round(error, 4))
                groups[index]["members"].append(member)
        grouping = {
            "schema_version": 1, "game_id": GAME,
            "dataset_fingerprint": fingerprint(rows),
            "algorithm": "dhash64-and-rgb-thumbnail-v1",
            "parameters": {"max_hamming": hamming, "max_pixel_mae": pixel_mae,
                           "thumbnail": [32, 24], "representative": "earliest_recorded_frame"},
            "groups": groups,
            "note": "Heuristic similarity groups, not verified scene identities. Originals are retained.",
        }
        write_json(root / "diversity.json", grouping)
        return {"frames": len(rows), "representatives": len(groups),
                "similar_frames_grouped": len(rows) - len(groups),
                "originals_deleted": 0, "groups": str(root / "diversity.json")}


def checked_labels(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError("Labels require has_subtitles and is_cutscene")
    if any(item is not None and type(item) is not bool for item in value.values()):
        raise ValueError("Labels must be true, false or null (unknown)")
    return value


def import_labels(root, path):
    batch = read_json(path)
    if batch.get("schema_version") != 1 or batch.get("game_id") != GAME:
        raise ValueError("Unsupported annotation file or game")
    with dataset_writer(root):
        dataset = Dataset(root)
        if batch.get("dataset_fingerprint") != fingerprint(dataset.rows.values()):
            raise ValueError("Annotations belong to a different image inventory")
        seen, changes = set(), []
        for annotation in batch["annotations"]:
            frame_id = annotation["frame_id"]
            if frame_id in seen or frame_id not in dataset.rows:
                raise ValueError("Duplicate or unknown annotation frame ID")
            seen.add(frame_id)
            labels = checked_labels(annotation["labels"])
            baseline = checked_labels(annotation["base_labels"])
            row = dataset.rows[frame_id]
            if row["labels"] != baseline and row["labels"] != labels:
                raise ValueError("Annotations conflict with newer saved labels; rebuild the gallery")
            if row["labels"] != labels:
                changes.append((row, labels))
        timestamp = datetime.now(timezone.utc).isoformat()
        for row, labels in changes:
            row["labels"] = labels.copy()
            row["labels_updated_at"] = timestamp
            known = sum(value is not None for value in labels.values())
            row["review_status"] = "labeled" if known == 2 else "partially_labeled" if known else "unreviewed"
        dataset.save()
        return {"updated_frames": len(changes), "annotations": len(seen)}


def selected_rows(rows, mapping, subtitles=None, cutscene=None, diverse=False):
    choices = {"yes": True, "no": False, "unknown": None}
    seen, selected = set(), []
    for row in sorted(rows, key=chronology):
        labels = row.get("labels", UNKNOWN)
        if subtitles is not None and labels["has_subtitles"] != choices[subtitles]:
            continue
        if cutscene is not None and labels["is_cutscene"] != choices[cutscene]:
            continue
        # Filter first: a group's original representative may not match labels.
        group = mapping[row["id"]]
        if diverse and group in seen:
            continue
        seen.add(group)
        selected.append({"frame_id": row["id"], "path": row["path"],
                         "sha256": row["sha256"], "labels": labels, "similarity_group": group})
    return selected


def select_frames(root, subtitles=None, cutscene=None, diverse=False, output=None):
    verify(root)
    rows = read_rows(root)
    mapping = groups_for(root, rows, required=diverse)
    selected = selected_rows(rows, mapping, subtitles, cutscene, diverse)
    document = {"schema_version": 1, "game_id": GAME, "dataset_fingerprint": fingerprint(rows),
                "filters": {"has_subtitles": subtitles, "is_cutscene": cutscene, "diverse": diverse},
                "path_base": "dataset_root", "frames": selected}
    destination = output or root / "selection.json"
    if destination.suffix != ".json":
        raise ValueError("Selection output must be a JSON file")
    if destination.exists():
        existing = read_json(destination)
        if not isinstance(existing, dict) or existing.get("path_base") != "dataset_root" or "frames" not in existing:
            raise ValueError("Selection output cannot overwrite existing source files or dataset metadata")
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, document)
    return {"selected_frames": len(selected), "selection": str(destination)}


def review_gallery(root):
    verify(root)
    rows = sorted(read_rows(root), key=chronology)
    mapping = groups_for(root, rows)
    data = []
    for row in rows:
        data.append({"id": row["id"], "path": row["path"], "width": row["width"],
                     "height": row["height"], "labels": row.get("labels", UNKNOWN),
                     "group": mapping[row["id"]]})
    # Escape '<' so even hostile metadata cannot terminate the JSON script tag.
    payload = json.dumps({"schema_version": 1, "game_id": GAME,
                          "dataset_fingerprint": fingerprint(rows), "frames": data}).replace("<", "\\u003c")
    template = Path(__file__).with_name("review.html").read_text()
    document = template.replace("__DATASET_JSON__", payload)
    with dataset_writer(root):
        atomic_write(root / "review.html", document)
    return {"review": str(root / "review.html"), "frames": len(rows),
            "similarity_groups": len(set(mapping.values()))}
