<p align="center">
  <img src="logo.png" alt="ScummHD" width="280" />
  <br />
  <!-- repo-tagline:start -->
  <strong>🖼️ Build visual datasets from ScummVM adventures 🔍</strong>
  <!-- repo-tagline:end -->
</p>

# ScummHD

ScummHD collects original game frames from [ScummWEB](https://scummweb.tsilva.eu)
for future visual-enhancement research. It starts with **Flight of the Amazon
Queen**: import existing AgentSCUMM run captures, preserve their provenance, and
review the collection before choosing training examples.

Browse the [Queen dataset on Hugging Face](https://huggingface.co/datasets/tsilva/scummhd-queen):
159 representative frames with subtitle and story/cinematic labels.

This bootstrap collects data only. It does not generate enhanced images, train a
model, or change the game renderer.

The project is now named ScummHD. The `python -m scummvision` command remains
available for existing workflows; new commands use `python -m scummhd`.

## Start a collection

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv --config-file uv.toml sync --locked
uv --config-file uv.toml run --locked python -m scummhd import-catalog
uv --config-file uv.toml run --locked python -m scummhd verify
uv --config-file uv.toml run --locked python -m scummhd dedupe
uv --config-file uv.toml run --locked python -m scummhd review
```

This downloads three original, checksum-pinned catalog screenshots. Open the
printed `review.html` path to inspect them. Files stay under Git-ignored
`data/flight-of-the-amazon-queen/`; they are not included in this repository.

To add an existing [AgentSCUMM](https://github.com/tsilva/agentscumm) run export:

```sh
uv --config-file uv.toml run --locked python -m scummhd import-run /path/to/run-export
```

Imports preserve image bytes and recorded frame/session metadata. Repeating an
import is safe; exact duplicates share storage. Images without explicit frame
provenance are recorded in quarantine for review.

The gallery lets you tag **subtitles present** and **cutscene**, filter those
labels, and browse one frame per similarity group. Unknown labels stay unknown.
Export label edits and save them with:

```sh
uv --config-file uv.toml run --locked python -m scummhd import-labels /path/to/scummvision-labels.json
uv --config-file uv.toml run --locked python -m scummhd select --subtitles no --cutscene no --diverse
```

Similarity grouping selects a diverse subset without deleting originals.
Cropping remains a later preprocessing step.

Prepare images and labels for optional Hub storage with the
[Hugging Face export guide](docs/huggingface.md). The exporter defaults to similarity
representatives, preserves original bytes, and omits private session records.

See the [dataset guide](datasets/flight-of-the-amazon-queen/README.md) for quality
limits, manifest fields, and future collection. Tooling is [MIT-licensed](LICENSE);
game artwork retains its separate rights.
