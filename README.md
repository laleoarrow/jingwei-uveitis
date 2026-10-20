# JingWei · 精卫 <img src="docs/assets/jingwei-logo.svg" align="right" width="170" height="170" alt="JingWei bird logo in a green circular frame" />

[![Checks](https://img.shields.io/github/actions/workflow/status/laleoarrow/jingwei-uveitis/checks.yml?branch=main&style=for-the-badge&label=Checks&labelColor=334B49)](https://github.com/laleoarrow/jingwei-uveitis/actions/workflows/checks.yml) [![Python 3.12](https://img.shields.io/badge/Python-3.12-2E7D6A?style=for-the-badge&logo=python&logoColor=white&labelColor=334B49)](#installation) [![Inputs OCT and CFP](https://img.shields.io/badge/Inputs-OCT%20%7C%20CFP-397F73?style=for-the-badge&labelColor=334B49)](#use)

JingWei uses optical coherence tomography (OCT) or color fundus photography (CFP) images to predict retinal vascular leakage (RVL) in uveitis, as assessed by fundus fluorescein angiography (FFA).

**[Online demo](https://laleoarrow.github.io/jingwei-uveitis/) · [Installation](#installation) · [Use](#use)**

The online demo shows the workflow and report format with fixed illustrative results, without running the model or calculating heatmaps. For actual analysis, run JingWei offline as described below.

## Installation

### 1. Download

Download the [source ZIP](https://github.com/laleoarrow/jingwei-uveitis/archive/refs/heads/main.zip) and extract it. Open the extracted `jingwei-uveitis-main` folder.

### 2. Start JingWei

| System | Start |
|---|---|
| macOS (Apple silicon) | Double-click **`start.command`**. |
| Windows (64-bit x86) | Double-click **`start.bat`**. |
| Linux | Open a terminal in the extracted folder and run **`bash start.command`**. |

The launcher installs Python 3.12 and the required packages in the application folder, then opens **[JingWei](http://127.0.0.1:8765/)** in your browser. No separate Python installation is needed. Initial setup requires internet access and may take several minutes; progress appears in the terminal.

**Keep the terminal open** while using JingWei. Press **Ctrl+C** there to stop. Reopen with the same launcher to reuse the environment and saved settings.

### 3. Configure the weights

**[Download JingWei model weights](https://pan.baidu.com/s/1r7gfecgxxbtCQnV0FmZlSg?pwd=7a7c)** (Baidu Netdisk) · Access code: `7a7c`.

You can open the interface without weights, but analysis requires them.

Open **Settings**, enter the weight-file path for **OCT**, **CFP**, or both, and select **Save changes**. Keep the original filenames; quoted absolute paths are accepted. Leave unused modalities blank.

Alternatively, these default locations are recognized automatically:

| Input | File location |
|---|---|
| OCT | `weights/OCT.pth` |
| CFP | `weights/CFP.pth` |

Leave **Processing device** on **Automatic** and **Include heatmap** and **AI-assisted interpretation** unchecked for the first assessment.

### Install with LLM

Give your preferred AI assistant the following prompt in a session with terminal access:

```text
Install and launch JingWei from https://github.com/laleoarrow/jingwei-uveitis on this computer.
Follow the README and use the launcher for my operating system. Verify that the offline web app opens.
Ask me for the paths to my OCT and/or CFP weight files and configure them without renaming the files.
If I do not have weights yet, complete installation and explain how to add them later.
```

## Use

1. Select **OCT** or **CFP** in **Analysis** and enter examination details if needed.
2. Select **Browse files** to upload an image, or **Use sample** to test the setup. AI-generated samples run through the local model and require weights.
3. Wait for the **RVL Score**, **predicted probability** and **analysis time**. The first assessment may take longer as the model loads.
4. Select **Generate report**, then **Print / Save PDF**. For PDF export, choose **A4**, **100% scale**, and turn off browser **headers and footers**.

Supported images: JPEG, PNG, single-page TIFF and WebP, up to 20 MiB each.

**System status** in Settings refreshes every five seconds. It normally shows **Service: Online**, **Environment: Ready** (required packages present), and **Activity: Idle** (no task running). Active stages—analyzing, heatmap and refining—show elapsed time. Weight labels distinguish files found from models loaded; compatibility is checked when loading.

### Heatmaps

JingWei uses Integrated Gradients (IG) to show how image regions contribute to the RVL Score.

Turn on **Include heatmap** in **Settings**; it is off by default. Changes apply to the next sample or upload without saving, leaving current results unchanged. **Save changes** keeps the preference across refreshes.

Under **Contributing regions**, **Model input** shows the crop analyzed by the model, not the full upload. **Heatmap** shows the color map alone. **Overlay** places it over that crop so you can compare the colors with fundus or OCT structures.

Red shows contributions that raise the RVL Score, favoring a positive prediction; blue shows contributions that lower it. Both are relative to a blurred version of the same input, not a healthy eye. The maps explain the model’s output; they do not identify lesions.

Heatmaps take longer because they require repeated calculations. If the final checks fail, the report shows **Heatmap unavailable**; the valid prediction remains.

<details>
<summary>Technical details</summary>

Images are resized proportionally to a 256-pixel shorter side and center-cropped to 224 × 224. Captum Integrated Gradients (IG) always explains **RVL Score** (`logits[1] - logits[0]`), not probability, regardless of predicted class. The reference uses Gaussian blur, σ=16 input pixels.

Signed RGB-channel contributions are summed at each pixel rather than pooled into patches for display. Only the displayed map is smoothed (Gaussian σ=1 input pixel); neighboring positive and negative values can cancel. Colors follow the smoothed signs; raw values and the background remain unchanged.

Color limits normally use the 99th percentile of absolute, unsmoothed pixel attributions, symmetrically around zero; colors saturate beyond these limits. The −1 / 0 / +1 legend is a relative display scale, not raw units; intensities cannot be compared across images. Overlay opacity increases linearly with the absolute normalized, clipped value from 0 to 0.5; zero is transparent.

Checks assess numerical consistency and stability on the model’s native patch grid, not pixel-level stability.

</details>

### AI-assisted interpretation

In **Settings**, enable **AI-assisted interpretation**, enter the **API URL**, **Model** and **API key**, and select **Save changes**. Saved settings apply to new analyses.

The service only rephrases the positive or negative prediction sentence; the numerical sentence stays fixed. Remote services require internet access and receive only the modality, RVL Score and probability—not images or patient information. Without LLM access, the report uses a local template.

## Troubleshooting

| Problem | What to do |
|---|---|
| macOS cannot verify `start.command` | If you downloaded JingWei from this repository, open **System Settings → Privacy & Security** after the blocked launch. Under **Security**, select **Open Anyway** for `start.command`, then confirm **Open**. Double-click the launcher again. See [Apple’s instructions](https://support.apple.com/en-us/102445). |
| Installation stops during a download | Check your internet connection and run the launcher again. |
| Weights are not found | Check the file path for the selected modality in Settings and select **Save changes**. The other modality is optional. |
| The browser does not open | Keep the terminal running and open its displayed address, usually **http://127.0.0.1:8765/**, rather than opening `index.html`. |
| The app is already running | Use the existing browser page. To restart, press **Ctrl+C** in the previous terminal, then run the launcher again. |

For other problems, [open an issue](https://github.com/laleoarrow/jingwei-uveitis/issues) with your operating system and the error shown in the terminal.

[Reference data](data/README.md) · [Optional report fonts](static/fonts/README.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
