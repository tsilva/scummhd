# SCUMMvision

SCUMMvision owns datasets and future visual-enhancement experiments for games
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
uv --config-file uv.toml run --locked python -m scummvision verify
```

Tests use synthetic images in temporary directories. Real captures stay local.
No service credentials are needed for the collector's public, pinned downloads.
