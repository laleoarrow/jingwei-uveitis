# JingWei · 精卫

An offline system for predicting retinal vascular leakage (RVL) in uveitis from colour fundus photography (CFP) or optical coherence tomography (OCT). Outputs include RVL scores, predicted probabilities and assessment reports.

**[Online demo](https://laleoarrow.github.io/jingwei-uveitis/) · [Installation](#offline-use)**

Offline inference requires compatible model weights. The online demo illustrates the workflow and report format without analysing images.

## Offline use

Use Python 3.12. From this directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python launch.py
```

Open **http://127.0.0.1:8765/**. Keep the process running while using the application. After installation, macOS users can double-click `start.command`; Windows users can use `start.bat`.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launch.py
```

For another port, use `python launch.py --port 8766`. `--no-browser` starts the service without opening a tab. Windows launch support is provided but has not been tested on a Windows machine.

### Model weights

Weights are **not included** or downloaded automatically. Supply the corresponding fine-tuned binary RVL checkpoints, then set their paths in Settings:

- **CFP:** RETFound DINOv2 / ViT-L/14. Default location: `weights/CFP.pth`.
- **OCT:** RETFound MAE / ViT-L/16. Default location: `weights/OCT.pth`.

You can select files elsewhere using absolute paths. A generic pretrained RETFound checkpoint does not replace these fine-tuned classification weights. Settings checks the path and device; actual model compatibility is checked during loading. CPU and Apple MPS are supported. Automatic uses MPS when available, otherwise CPU.

The app is independent of the original research repository. Model definitions, attribution code, and aggregate reference curves are included. A custom checkpoint can produce an assessment, but the historical reference distribution is shown only when its contents match the frozen study checkpoint signature.

## Workflow

1. Select CFP or OCT, then drop one image. JPEG, PNG, single-page TIFF and WebP are supported (up to 20 MiB / 40 million pixels).
2. Enter optional examination details. Assessment shows RVL Score, predicted probability, classification and elapsed analysis time.
3. Select a reference cohort and generate the report.
4. Print or save as PDF, preferably A4 at 100% scale. Modern Chromium browsers support the report's Printed timestamp and Page X of Y footer. Turn off the browser's additional header/footer to avoid duplication.

Include heatmap is off by default. Enabling it in Settings affects the next analysis and adds the Original / Heatmap / Overlay row under **Contributing regions**. Without a heatmap, the original image is positioned beside the assessment results. All contributing-region views use the same model-input crop.

### Optional result interpretation

Without an LLM, prespecified templates explain the result relative to the 50% classification threshold. You may configure an OpenAI-compatible Chat Completions endpoint, model and API key in Settings. Only the modality, RVL Score and probability are sent to that endpoint; images, patient details and filenames are not sent. Invalid or unavailable responses fall back to the prespecified template. Interpretation does not change the model output.

Settings, including an optional API key, are stored on your computer at `runtime/settings.json` with owner-only permissions. The entire runtime directory is excluded from Git. Uploaded images, patient details and results stay in memory; the application does not maintain a report history. Saved PDFs are managed by the user.

## Scientific definitions

- Input: RGB, bicubic resize to a 256-pixel short edge, 224 × 224 center crop, ImageNet normalization. The original evaluation orientation behavior is retained.
- **RVL Score = logit₁ − logit₀**; **probability = sigmoid(RVL Score)**. The classification boundary is score 0 / probability 50%.
- Model evaluation uses float32. The OCT head readout follows the original evaluated implementation. Device differences can introduce small floating-point differences.
- Attribution targets the same logit margin for both classes: CFP uses gradient-weighted attention rollout; OCT uses final-block patch activation × gradient. Only positive contributions are displayed, normalized within each image. Colors do not represent lesion severity or segmented leakage boundaries.
- The bundled reference file contains aggregate counts, quantiles, score ranges and KDE curves for each cohort and modality, without individual image/patient records. Scott-bandwidth KDE is limited to each group's observed score range. See [reference provenance](data/README.md).

This application concerns RVL model outputs in uveitis. Probability is an uncalibrated model output, not disease severity. The report provides a clinician review area and does not replace a complete FFA assessment.

## Report fonts

The offline report supports Helvetica Neue LT Std Light, Bold and Bold Condensed when appropriately licensed files are placed in `static/fonts/`. These binaries are not distributed in this repository. Without them, reports remain usable and printable with system sans-serif fonts. See [font setup](static/fonts/README.md). The website demo uses system fonts and includes no proprietary font files.

## Repository layout

```text
inference.py / attribution.py    Offline model inference and contributing regions
server.py / interpretation.py    API, settings and result interpretation
reference.py / data/            Aggregate reference distributions
vendor/                         Extracted model and attribution definitions
static/                         Offline workbench and printable report
launch.py / start.*              Offline startup
scripts/                        Demo build and offline aggregate reference export
docs/                          Public static website and demonstration
runtime/                        Settings and QA output (ignored)
weights/                        Optional model weights (ignored)
```

## Development

```sh
python -m unittest discover -s . -p 'test_*.py'
node --check static/app.js
python scripts/build_demo.py
python -m http.server 8080 --directory docs
```

The tests do not require trained checkpoints or private research data. Rebuild the demo after changing the offline workbench: the build reuses its layout and report, with a browser-only adapter for illustrative results. GitHub Pages serves only `docs/` from `main`; it never runs Python or exposes the offline application’s API. The application service binds only to loopback and is not configured as a multi-user hospital deployment.

## Licensing and acknowledgements

This is a source-available release. No separate reuse license has yet been granted for original JingWei application code. The vendored RETFound code is subject to its upstream **CC BY-NC 4.0** license and attribution requirements; model weights have their own terms. See [third-party notices](THIRD_PARTY_NOTICES.md) and [vendor provenance](vendor/NOTICE.md). This project is not affiliated with Mayo Clinic.
