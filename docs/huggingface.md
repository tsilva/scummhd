# Hugging Face dataset export

Keep collector code on GitHub and use a Hugging Face dataset repository for
versioned images and labels. The Hub supports ImageFolder datasets with JSONL
metadata and a browsable image column. The local review collection remains the
source until a published revision has been verified; exporting does not upload
or remove anything.

## Prepare an export

```sh
uv --config-file uv.toml run --locked python -m scummhd export-hf --output data/huggingface/queen-v1
```

Run `dedupe` first. By default the bundle contains one representative per
similarity group, original image bytes, an `images/metadata.jsonl` file, a dataset
card, and an export receipt. Choose a new version directory each time; existing
exports are not overwritten. Add `--all-frames` to include nonrepresentatives,
whose labels remain unknown unless they were separately reviewed.

Metadata includes frame hashes, dimensions, `has_subtitles`, `is_cutscene`,
`is_representative`, similarity groups, reviewer type, method and policy version.
It excludes local source paths, session/action IDs, transcripts and detailed
review notes. The two content labels are boolean or null. No label propagation,
cropping, generated targets or train/validation/test assignment is performed.

## Check the dataset locally

Install the optional loader from the committed lockfile:

```sh
uv --config-file uv.toml sync --locked --extra huggingface
```

```python
from datasets import load_dataset

frames = load_dataset("data/huggingface/queen-v1", token=False)["data"]
gameplay = frames.filter(
    lambda row: row["has_subtitles"] is False and row["is_cutscene"] is False
)
```

Loading the export directory reads its dataset-card configuration and the `data`
split. Calling the generic `imagefolder` loader without explicit data-file mapping
uses its default `train` name instead; this is only a loader default, not an
evaluation split selected by ScummHD.

## Hosting

Upload the entire prepared directory to the chosen dataset repository after
reviewing its dataset card and selecting visibility. Use the repository's reviewed
Hugging Face credential route; no route is provisioned by this exporter. Do not
use raw keys, login caches, or another project's credentials. A route must also
support the actual image upload transport before publication is reported as working.

After uploading, load the exact published revision, verify row counts and labels,
and compare every image SHA-256 with the export receipt and metadata. Keep any
local copy as a cache until that verification succeeds. Deleting local originals
is a separate, explicit action. Game-art rights remain separate from the tooling's
MIT license; the exporter does not assert an image-data license.
