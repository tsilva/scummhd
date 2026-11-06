# ScummHD brand assets

The Pixel Lens badge pairs an emerald adventure landscape under a cream
magnifying glass with the ScummHD wordmark. The text-free magnifier is the
small-icon variant. Both use transparent backgrounds.

- `sources/` preserves untouched native ImageGen PNGs. The tool did not identify
  the exact model or snapshot.
- `logo/logo-1024.png` and `icon/icon-1024.png` are square exports.
- The root `logo.png` is the README export with an even 24 px transparent margin.
- `web-seo/` contains 16/32/48 px favicons, a multiframe ICO, touch/install icons,
  and a 1200 × 630 social preview. These are reusable exports, not an assertion
  that the collector is an installable web application.
- `manifest.json` records dimensions; `provenance.json` records source evidence,
  SHA-256 fingerprints and export lineage.

For deterministic exports, clear only source alpha values below 8 in a working
copy, trim transparent bounds, and use the `private-skills_create-image-assets`
derivation workflow with the `web-seo` target. Preserve the original sources.
Center the social logo on `#15181c`. Recheck dimensions, ICO frames, fingerprints,
and readability on white, off-white, dark and transparent backgrounds after edits.
