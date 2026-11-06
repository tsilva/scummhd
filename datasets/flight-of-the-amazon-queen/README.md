# Flight of the Amazon Queen frames

The first ScummHD collection contains original ScummWEB game screenshots.
It is an uncurated source collection, not a paired enhancement dataset.

## Sources

- Three original catalog screenshots, pinned in
  [the source specification](../../sources/scummweb-queen.json). Downloads use
  the immutable bucket origin directly. Generated covers and hero art are excluded.
- Existing AgentSCUMM exports containing `run.json`, `screenshots/index.json`
  and the referenced image files. Re-run `import-run` for each additional export.
  Collection never controls, interrupts, or restarts a live game.

## Local dataset

The default directory is `data/flight-of-the-amazon-queen/`. Use
`--dataset DIRECTORY` before the subcommand to select another directory.
The images, manifests, quarantine and review page stay outside Git.

`manifest.jsonl` has one record per file SHA-256, with original bytes, encoding,
dimensions, decoded-pixel hash, a 64-bit difference hash, source references,
and recorded frame/session/action IDs and timestamps. Native rendering resolution
is unknown. `sources.json` retains source/index checksums, and `quarantine.json`
lists entries excluded for missing frame provenance. No conversation text is copied.

`stats` reports the inventory; `verify` decodes and rechecks every image and its
metadata. `review` builds a local labeling gallery. Failed imports may leave unindexed files;
retry the source import before running verification. Concurrent imports are refused.

## Labels and specific subsets

Each image has `labels.has_subtitles` and `labels.is_cutscene`. Values are
`true`, `false`, or `null` for unknown. Subtitles means visible spoken dialogue or
narrative captions; inventory labels, verb prompts, signs, dialogue-choice menus
and credits alone do not count. Cutscene means a scripted story/cinematic sequence,
including staged encounter shots and the ending presentation. Ordinary interactive
conversations, object examination, walking and routine room fades do not count.
Use the surrounding sequence when a still
cannot establish this; do not assume that missing interface elements imply a cutscene.

The gallery starts from saved labels. Edits are browser-local drafts until you
export them and run `import-labels FILE`. The importer validates the image inventory,
label types, and original saved labels before applying a batch. Conflicting edits
are rejected instead of overwriting newer annotations. Rebuild the gallery with
`review` after importing labels. These labels do not establish training readiness.

Annotation batches may include a `review` object with `review_id`, `reviewer_type`
(`human`, `agent`, or `unknown`), `method`, `policy_version`, `context_checked`,
and a bounded `note`. It is retained as `label_review` in the local manifest.
Unattributed edits clear earlier reviewer provenance when they change labels.
Labels are attached only to reviewed images; similarity-group membership never
propagates them to other frames.

Use `select --subtitles no --cutscene no --diverse` for one matching image per
similarity group, or omit filters to include unknown labels. Unknown is distinct
from no. Results are written to local `selection.json`; the gallery can also export
a selection using its current filters and draft labels.

## Diversity without deleting frames

Run `dedupe` after imports. It groups frames by 64-bit difference-hash distance
and mean RGB difference between 32×24 thumbnails. Defaults are at most 8 changed
hash bits and 8 intensity levels of mean difference; adjust with `--hamming` and
`--pixel-mae`. Every member is compared against the group's representative to
avoid chains merging increasingly different scenes. The earliest recorded frame
represents each group by default. With label filters, selection chooses a matching
member even when the original representative does not match.

`diversity.json` records the algorithm, thresholds, representatives, membership
and distances. These are heuristic similarity groups, not verified room/scene
identities. No original images are deleted. Different dialogue or animation
states remain available. New imports invalidate old groups until `dedupe` runs
again. Cropping is deferred to a separate future preprocessing stage.

## Quality limits and next collection

Archived captures can contain JPEG artifacts, browser scaling, black borders,
cursors, menus, dialogue and loading screens. Byte preservation does not make a
capture lossless or native-resolution. Review images before selecting examples.

All records start with unknown subtitle/cutscene labels, `review_status: unreviewed`, `scene_id: null`,
`split: unassigned`, `target: null`, and `training_eligible: false`. Future curation
must group related scenes and sequences before splitting data; randomly splitting
nearby screenshots can leak the same backgrounds into training and evaluation.

For future sessions, prefer original lossless canvas captures with timestamps,
canvas bounds, rendering settings, game edition and engine revision recorded at
capture time. This bootstrap imports saved captures; continuous recording is not
implemented. Enhanced targets and model training remain separate future work.

Game artwork belongs to its respective rights holders. The code license grants
no rights to distribute the images or game data. No dataset license or public
dataset release is declared.

For a portable image-and-label bundle, see [Hugging Face export](../../docs/huggingface.md).
