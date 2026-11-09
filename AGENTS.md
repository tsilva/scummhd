# ScummHD

ScummHD owns datasets and future visual-enhancement experiments for games
running in ScummWEB/ScummVM. ScummWEB owns the game runtime; AgentSCUMM owns
gameplay controls and run archives. Do not modify those projects implicitly.

## Current scope

Collect and audit original Flight of the Amazon Queen frames. Enhancement-target
generation, model training, game modifications, and dataset publication are not
implemented or authorized merely by a collection request.

- Preserve original image bytes and SHA-256 provenance. Never label generated
  images as original captures or browser screenshots as native engine frames.
- Keep captures, manifests containing session IDs, local source paths, review
  pages, and run records under ignored `data/` or `.internal/`. Do not commit
  screenshots, transcripts, saves, game payloads, credentials, or local reports.
- Read archived AgentSCUMM exports without changing or restarting live games.
- Prefer checksum-pinned bucket-origin images over app-server proxies. Import
  only the explicitly listed original screenshots, never generated artwork.
- Keep unknown metadata explicitly unknown. Exclude records without frame
  provenance from run import and retain a quarantine record for review.
- Subtitle and cutscene labels are tri-state: yes, no, unknown. Visible verb
  prompts are not dialogue subtitles. Do not infer cutscenes from a still alone
  when surrounding interaction is needed. Preserve annotation conflict checks.
  Narrative captions count as subtitles; dialogue choices and credits alone do
  not. Ordinary conversations do not count as story/cinematic sequences. Record
  agent versus human review provenance and do not spread labels to similar frames.
- Similarity groups select diverse subsets without deleting originals. Filter
  labels before choosing representatives; keep heuristic groups separate from
  verified scenes. Cropping is deferred to later preprocessing.
- Keep all frames unassigned to train/validation/test until scene-aware curation.
  Random frame splitting leaks adjacent frames and repeated backgrounds.
- Preserve collection-only scope in documentation. Future generated targets
  require separate provenance and original-to-target alignment review.
- Work on the current branch. Before a later coding task, pull its configured
  upstream with `git pull --no-rebase`, preserving local work.
- Use HTTPS with stored `gh` Git authentication. Use the global
  `private-skills_push` workflow for authorized pushes.
- Use uv and the committed lockfile. Preserve the seven-day release cutoff and
  dependency constraints. Do not add exotic package sources without approval.
  Select `--config-file uv.toml` to keep machine-wide package exceptions out of
  the lockfile; keep its cutoff consistent with `pyproject.toml`.
- Use Brave Stable with the Agents profile through the bundled Browser runtime
  for browser interactions. Do not launch another browser as a fallback.

## Verification

```sh
uv --config-file uv.toml sync --locked
uv --config-file uv.toml run --locked python -m unittest discover -s tests -v
uv --config-file uv.toml run --locked python -m scummhd verify
```

Tests use synthetic images in temporary directories. Real captures stay local.
No service credentials are needed for the collector's public, pinned downloads.
`export-hf` prepares a local image-and-label bundle without authentication or
upload. Hub publication requires an approved destination/visibility and a reviewed
credential route for this repository. Never reuse another project's token or a
cached Hugging Face login. Keep local captures until remote transfer is verified;
removing them requires the user's explicit authorization.

## Hugging Face credentials

The approved public dataset destination is `tsilva/scummhd-queen`.
Native `.infisical.yaml` binds Secret Manager project
`72a466bb-8c3f-482f-a214-cff243afb7e4`, environment `dev`, folder
`/agents/huggingface-queen`, with source secret `HF_TOKEN`. Parse it as data;
reject scope overrides, cached Hub tokens and credentials from other projects.

The dedicated Agent Vault bundle is `local-scummhd-queen`
(`5382d359-c979-4f3d-b931-701e320d9b9a`), HTTP service `huggingface-queen`
(`f9540a22-d6bf-4bfc-9fd2-f4a04ab4c719`). It brokers a bearer credential only
to `huggingface.co`, with GET/HEAD/POST and these path prefixes:

- `/api/whoami-v2`
- `/api/datasets/tsilva/scummhd-queen/revision/main`
- `/api/datasets/tsilva/scummhd-queen/tree/main`
- `/api/datasets/tsilva/scummhd-queen/preupload/main`
- `/api/datasets/tsilva/scummhd-queen/commit/main`
- `/datasets/tsilva/scummhd-queen/resolve/main`

Use `scripts/hf_vault.py check` for the bounded identity check. This project-owned
Mac launcher pins the instance and proxy CA, uses a 30-minute native Agent Vault
session, supplies only a placeholder, and adds an explicit child OS sandbox.
It does not sandbox Codex Desktop or isolate full-access same-user processes.
Source keys are never read by ordinary checks. Trusted provisioning/rotation uses
`scripts/provision_hf_credential.py --apply-from-stdin` separately; keep its input
and responses in memory, never command arguments, files, logs or token caches.
Both the Secret Manager slot and Agent Vault copy must be refreshed together.

Fake-key identity rejection and nine sandbox/path-policy checks passed during
setup. The sandboxed live check authenticated as `tsilva`. Local CLI image upload
via LFS/Xet is unverified; do not broaden hosts, bypass the sandbox or inject the
real key to make it work.
The signed-in Hub website may be used for an explicitly authorized upload.
