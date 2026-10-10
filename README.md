# JingWei · 精卫

JingWei: non-invasive prediction system of retinal vascular leakage in uveitis from fundus photography or OCT.

**[Online demo](https://laleoarrow.github.io/jingwei-uveitis/) · [Installation](#installation)**

The online demo illustrates the workflow and report format without analysing images.

## Installation

Model inference runs offline. Install Python 3.12, then clone the repository:

```sh
git clone https://github.com/laleoarrow/jingwei-uveitis.git
cd jingwei-uveitis
```

macOS / Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python launch.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe launch.py
```

Open **http://127.0.0.1:8765/** and keep the service running. After installation, use `start.command` on macOS or `start.bat` on Windows to launch the application.

## Model weights

Model weights are supplied separately. In **Settings**, enter the paths to the corresponding fine-tuned RVL checkpoints:

| Input | Model | Default path |
|---|---|---|
| CFP | RETFound DINOv2 · ViT-L/14 | `weights/CFP.pth` |
| OCT | RETFound MAE · ViT-L/16 | `weights/OCT.pth` |

Absolute paths are supported. Generic pretrained checkpoints cannot substitute for the RVL classification weights. **Automatic** uses Apple MPS when available; otherwise, it uses CPU. Reference distributions are available for the study checkpoints.

## Use

1. Enter examination details before uploading an image, if required.
2. Select **CFP** or **OCT** and upload one image: JPEG, PNG, single-page TIFF or WebP (up to 20 MiB).
3. Review the RVL Score, predicted probability and classification. Select the reference cohort and choose **Generate report**.
4. Select **Print / Save PDF**. Use an up-to-date Chrome or Edge browser, A4 at 100% scale, and disable browser headers and footers.

In **Settings**, enable **Include heatmap** to add contributing-region maps to subsequent assessments. This increases processing time.

Result interpretation uses prespecified text based on the 50% classification threshold. Optional LLM interpretation requires an OpenAI-compatible API endpoint, model and key. Only the modality and model outputs are sent; images and patient details remain on the computer.

[Reference data](data/README.md) · [Report fonts](static/fonts/README.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
