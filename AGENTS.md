# JingWei web app

This repository owns the local JingWei image assessment engine, browser workbench,
clinical report layout, and the public static demo in `docs/`.

- Keep the local runtime independent of the original research repository.
- Preserve the validated image preprocessing, logits, RVL margin definition,
  classification threshold, attribution algorithms, and reference values.
- Never commit runtime settings, API keys, weights, patient images, report exports,
  per-image research records, private fonts, or virtual environments.
- `docs/` is a browser-only demonstration generated with `scripts/build_demo.py`.
  Uploaded images stay in the browser. Fixed example results must remain visibly
  labeled as illustrative in the interface and every report/printout. The reference
  curves use the bundled aggregate research data; the result marker is illustrative.
  Never present demo results as predictions about an uploaded image.
- Heatmaps use Integrated Gradients adapted from BDRV `generate_ig_heatmaps.py`
  (commit `1248f82`), with a fixed RVL logit margin, blurred reference, and
  convergence checks. The final 2026-10-13 user choice is signed pixel-level IG:
  sum RGB attributions, smooth only the display attribution with σ=1 pixel, use
  raw absolute pixel IG P99 for the symmetric red–blue scale, and apply linear
  opacity from 0 to 0.5. Keep the original model-input image unchanged in both
  original and overlay panels. Preserve raw signed values; native patch-grid
  stability diagnostics must not be described as pixel-level stability. Keep
  the web runtime independent of BDRV; provenance is in `vendor/NOTICE.md`.
- Preserve third-party attribution and license files under `vendor/`.
- Heatmaps default to off. The current checkbox applies to the next sample or
  upload immediately; snapshot it when analysis starts and send it with the
  prediction request. Save changes persists the preference across reloads.
  Changing the checkbox must not save unrelated settings or alter an ongoing run.
- Run `python -m unittest discover -s . -p 'test_*.py'` for backend changes.
  Check JavaScript syntax and the relevant browser flow for frontend changes.
- Do not modify report typography or scientific calculations as part of unrelated
  maintenance.

