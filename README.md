<p align="center">
  <!-- repo-tagline:start -->
  <strong>🖼️ Build visual datasets from ScummVM adventures 🔍</strong>
  <!-- repo-tagline:end -->
</p>

# SCUMMvision

SCUMMvision collects original game frames from [ScummWEB](https://scummweb.tsilva.eu)
for future visual-enhancement research. It starts with **Flight of the Amazon
Queen**: import existing AgentSCUMM run captures, preserve their provenance, and
review the collection before choosing training examples.

This bootstrap collects data only. It does not generate enhanced images, train a
model, or change the game renderer.

## Start a collection

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv --config-file uv.toml sync --locked
uv --config-file uv.toml run --locked python -m scummvision import-catalog
uv --config-file uv.toml run --locked python -m scummvision verify
uv --config-file uv.toml run --locked python -m scummvision dedupe
uv --config-file uv.toml run --locked python -m scummvision review
```

This downloads three original, checksum-pinned catalog screenshots. Open the
printed `review.html` path to inspect them. Files stay under Git-ignored
`data/flight-of-the-amazon-queen/`; they are not included in this repository.

To add an existing [AgentSCUMM](https://github.com/tsilva/agentscumm) run export:

```sh
uv --config-file uv.toml run --locked python -m scummvision import-run /path/to/run-export
```

Imports preserve image bytes and recorded frame/session metadata. Repeating an
import is safe; exact duplicates share storage. Images without explicit frame
provenance are recorded in quarantine for review.

The gallery lets you tag **subtitles present** and **cutscene**, filter those
labels, and browse one frame per similarity group. Unknown labels stay unknown.
Export label edits and save them with:

```sh
uv --config-file uv.toml run --locked python -m scummvision import-labels /path/to/scummvision-labels.json
uv --config-file uv.toml run --locked python -m scummvision select --subtitles no --cutscene no --diverse
```

Similarity grouping selects a diverse subset without deleting originals.
Cropping remains a later preprocessing step.

See the [dataset guide](datasets/flight-of-the-amazon-queen/README.md) for quality
limits, manifest fields, and future collection. Tooling is [MIT-licensed](LICENSE);
game artwork retains its separate rights.
