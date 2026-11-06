"""Prepare a sanitized, original-byte ImageFolder dataset for optional Hub hosting."""

import json
from pathlib import Path
import shutil

from .cli import GAME, atomic_write, digest, read_rows, safe_file, verify, write_json
from .curation import chronology, fingerprint, groups_for


def export_dataset(root: Path, destination: Path, all_frames=False):
    root, destination = root.resolve(), destination.resolve()
    if destination == root or destination.is_relative_to(root / "frames"):
        raise ValueError("Export must not overwrite the source dataset or its images")
    if destination.exists():
        raise ValueError("Export destination already exists; choose a new version directory")
    verify(root)
    rows = read_rows(root)
    mapping = groups_for(root, rows, required=True)
    representatives = set(mapping.values())
    selected = sorted([row for row in rows if all_frames or row["id"] in representatives], key=chronology)
    metadata = []
    for row in selected:
        labels = row.get("labels", {})
        review = row.get("label_review", {})
        metadata.append({
            "file_name": Path(row["path"]).name, "frame_id": row["id"],
            "game_id": GAME, "sha256": row["sha256"],
            "width": row["width"], "height": row["height"],
            "has_subtitles": labels.get("has_subtitles"), "is_cutscene": labels.get("is_cutscene"),
            "is_representative": row["id"] in representatives,
            "similarity_group": mapping[row["id"]],
            "reviewer_type": review.get("reviewer_type"),
            "annotation_method": review.get("method"), "annotation_policy": review.get("policy_version"),
        })
    # Validate all selected paths before creating an export. No transcripts,
    # session IDs, action IDs, local source paths or browser records are copied.
    sources = [safe_file(root, row["path"]) for row in selected]
    destination.mkdir(parents=True, mode=0o700)
    try:
        images = destination / "images"
        images.mkdir(mode=0o700)
        for row, source in zip(selected, sources):
            target = images / source.name
            shutil.copyfile(source, target)
            target.chmod(0o600)
            if digest(target.read_bytes()) != row["sha256"]:
                raise ValueError("Exported image checksum mismatch")
        atomic_write(images / "metadata.jsonl", "".join(json.dumps(row, sort_keys=True) + "\n" for row in metadata))
        subtitle_count = sum(row["has_subtitles"] is True for row in metadata)
        cutscene_count = sum(row["is_cutscene"] is True for row in metadata)
        complete = sum(row["has_subtitles"] is not None and row["is_cutscene"] is not None for row in metadata)
        card = f'''---
language:
- en
pretty_name: ScummHD — Flight of the Amazon Queen
tags:
- image
- scummvm
- scummweb
- game-screenshots
- image-enhancement
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: data
    path: images/**
---

# ScummHD — Flight of the Amazon Queen

Original game captures collected from ScummWEB for visual-enhancement research.
This version contains **{len(selected)} images**, with **{complete} fully labeled**,
**{subtitle_count} showing subtitles**, and **{cutscene_count} showing story/cinematic sequences**.

## Labels

`has_subtitles` means visible spoken dialogue or narrative captions. Verb prompts,
inventory labels, signs, dialogue-choice menus and credits alone do not count.
`is_cutscene` means a scripted story/cinematic sequence, including staged encounter
shots and the ending presentation. Ordinary interactive conversations, object
examination, walking and routine room fades do not count. Unknown values are null.

Labels were reviewed by an AI agent using the original images and, for ambiguous
cases, nearby captures and recorded gameplay context. They are reviewable annotations,
not independently adjudicated ground truth. Similarity-group labels are not propagated
to unreviewed frames.

## Files and use

Images retain their original bytes and SHA-256 hashes. `images/metadata.jsonl`
provides the two labels, dimensions, similarity groups and annotation provenance.
There are no model-generated enhancements, crops, or train/validation/test assignments.
The single `data` split is a collection partition, not a training recommendation.

```python
from datasets import load_dataset
frames = load_dataset("PATH_TO_THIS_EXPORT", token=False)["data"]
```

Replace the local path with the published dataset ID after uploading to the Hub.
Browser scaling, JPEG artifacts, player controls and black borders may be present.
Preprocessing is deferred. Menus and transitions may be present in the non-cutscene
class; this is not a paired super-resolution dataset. Detailed review notes remain
in the local collection and are excluded from the upload bundle.

## Sources and rights

Captures come from an archived AgentSCUMM playthrough of Flight of the Amazon Queen
on ScummWEB and original ScummWEB catalog screenshots. Session IDs, action logs,
conversation text and local paths are excluded. The collector code is at
https://github.com/tsilva/scummhd.

Game artwork retains its respective rights. The collector's MIT license applies
to its tooling, not the game images; no separate image-data license is asserted here.
'''
        atomic_write(destination / "README.md", card)
        receipt = {"schema_version": 1, "game_id": GAME, "rows": len(metadata),
                   "fully_labeled": complete, "has_subtitles": subtitle_count, "is_cutscene": cutscene_count,
                   "selection": "all_frames" if all_frames else "representatives",
                   "source_inventory_fingerprint": fingerprint(rows),
                   "metadata_sha256": digest((images / "metadata.jsonl").read_bytes()),
                   "uploaded": False}
        write_json(destination / "export.json", receipt)
        return {**receipt, "directory": str(destination)}
    except BaseException:
        # This directory was created by this call and contains only its export.
        shutil.rmtree(destination)
        raise
