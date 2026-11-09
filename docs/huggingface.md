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

The selected public dataset is
[`tsilva/scummhd-queen`](https://huggingface.co/datasets/tsilva/scummhd-queen).

Upload `README.md` and `images/` from the prepared directory after
reviewing its dataset card and selecting visibility. Use the repository's reviewed
Hugging Face credential route; no route is provisioned by this exporter. Do not
use raw keys, login caches, or another project's credentials. A route must also
support the actual image upload transport before publication is reported as working.
Keep export and publication receipts local.

Load the published collection without authentication:

```python
from datasets import load_dataset

frames = load_dataset("tsilva/scummhd-queen", token=False)["data"]
subset = frames.filter(
    lambda row: row["has_subtitles"] is False and row["is_cutscene"] is False
)
```

For reproducible experiments, set `revision` to a verified Hub commit. The first
159-frame version is `709fce82e1a11c446385fec17c52ddbafc6f7d1e`.

After uploading, load the exact published revision, verify row counts and labels,
and compare every image SHA-256 with the export receipt and metadata. Keep any
local copy as a cache until that verification succeeds. Deleting local originals
is a separate, explicit action. Game-art rights remain separate from the tooling's
MIT license; the exporter does not assert an image-data license.

## Credential checks and rotation

The native Infisical binding and reviewed Agent Vault service mapping are in
`AGENTS.md`. The dedicated source is the `scummhd` project's Development folder
`/agents/huggingface-queen`, secret `HF_TOKEN`; it must contain a fine-grained
Hugging Face token restricted to this dataset. Hub write permission also includes
repository settings; Agent Vault further restricts the available HTTP paths.

On the configured Mac, run the bounded read-only check:

```sh
uv --config-file uv.toml run --locked python scripts/hf_vault.py check
```

The launcher receives no real Hub key, checks the source binding, pins the proxy
CA and runs its fixed client inside an OS sandbox. It blocks direct network
connections, credential-file reads and writes outside its temporary workspace.
The outer agent and other full-access processes remain outside that boundary.
It changes no global application defaults, CA trust or shared proxy settings.

After explicitly authorized token creation/rotation, trusted administration uses
`scripts/provision_hf_credential.py --apply-from-stdin` to update both encrypted
stores. Supply the value through a private in-memory pipe; never paste it into
command arguments or a file. This helper uses the existing Infisical administrator
login and is deliberately separate from ordinary client startup. Re-run the
identity check afterward. Renew a rejected token in Infisical; do not fall back
to a cached login or another project's token.

The invalid setup key passed nine policy checks, including blocked direct
connections, protected-file reads, other repository paths and DELETE requests.
The sandboxed live check authenticated as `tsilva`. The first 159-frame upload
used the signed-in Hub file uploader; an anonymous download of its exact commit
verified all original image hashes and labels. The local CLI's LFS/Xet transfer
path remains unverified. Use the signed-in uploader for authorized uploads until
that transport has a compatible reviewed route.
