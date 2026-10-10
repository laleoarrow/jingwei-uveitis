# JingWei web app

This repository owns the local JingWei image assessment engine, browser workbench,
clinical report layout, and the public static demo in `docs/`.

- Keep the local runtime independent of the original research repository.
- Preserve the validated image preprocessing, logits, RVL margin definition,
  classification threshold, attribution algorithms, and reference values.
- Never commit runtime settings, API keys, weights, patient images, report exports,
  per-image research records, private fonts, or virtual environments.
- `docs/` is a browser-only demonstration. Uploaded images stay in the browser;
  its fixed results and synthetic distributions must remain visibly labeled as
  illustrative in the interface and every report/printout. Never present them as
  predictions about an uploaded image.
- Preserve third-party attribution and license files under `vendor/`.
- Run `python -m unittest discover -s . -p 'test_*.py'` for backend changes.
  Check JavaScript syntax and the relevant browser flow for frontend changes.
- Do not modify report typography or scientific calculations as part of unrelated
  maintenance.

