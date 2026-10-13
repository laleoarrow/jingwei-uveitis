# JingWei · 精卫

JingWei uses color fundus photography (CFP) or OCT images to predict FFA-assessed retinal vascular leakage (RVL) in uveitis.

**[Online demo](https://laleoarrow.github.io/jingwei-uveitis/) · [Installation](#installation) · [Use](#use)**

The online demo illustrates the workflow and report format; it does not analyse images. Follow the steps below to run JingWei offline on your computer.

## Installation

### 1. Download

Download the [source ZIP](https://github.com/laleoarrow/jingwei-uveitis/archive/refs/heads/main.zip) and extract it. Open the extracted `jingwei-uveitis-main` folder.

### 2. Start JingWei

| System | Start |
|---|---|
| macOS (Apple silicon) | Double-click **`start.command`**. |
| Windows (64-bit x86) | Double-click **`start.bat`**. |
| Linux | Open a terminal in the extracted folder and run **`bash start.command`**. |

The launcher installs Python 3.12 and the required packages in the application folder, then opens **[JingWei](http://127.0.0.1:8765/)** in your browser. You do not need to install Python separately. The first installation needs internet access and may take several minutes; progress appears in the terminal window.

**Keep the terminal window open** while using JingWei. To stop, press **Ctrl+C** in that window. To reopen, run the same launcher; it reuses the installed environment and saved settings.

### 3. Configure the weights

**[Download JingWei model weights](https://pan.baidu.com/s/1r7gfecgxxbtCQnV0FmZlSg?pwd=7a7c)** (Baidu Netdisk) · Access code: `7a7c`.

You can open the interface without weights, but image analysis requires them.

After downloading the weights, open **Settings**, enter the file path for **CFP**, **OCT**, or both, and select **Save changes**. Keep the original filenames; you can paste an absolute path, including one copied with quotation marks. Leave an unused modality blank.

Alternatively, these default locations are recognised automatically:

| Input | File location |
|---|---|
| CFP | `weights/CFP.pth` |
| OCT | `weights/OCT.pth` |

Leave **Processing device** on **Automatic** and **Include heatmap** and **AI-assisted interpretation** unchecked for the first assessment.

### Install with LLM

Give your preferred AI assistant the following prompt in a session with terminal access:

```text
Install and launch JingWei from https://github.com/laleoarrow/jingwei-uveitis on this computer.
Follow the README and use the launcher for my operating system. Verify that the offline web app opens.
Ask me for the paths to my CFP and/or OCT weight files and configure them without renaming the files.
If I do not have weights yet, complete installation and explain how to add them later.
```

## Use

1. Select **CFP** or **OCT** in **Analysis** and enter examination details if needed.
2. Select **Browse files** to upload an image, or **Use sample** to check the setup with an AI-generated example. The offline sample runs actual analysis and requires the weights.
3. Wait for the **RVL Score**, **predicted probability** and **analysis time**. The first assessment can take longer while the model loads.
4. Select **Generate report**, then **Print / Save PDF**. For PDF export, choose **A4**, **100% scale**, and turn off browser **headers and footers**.

Supported images: JPEG, PNG, single-page TIFF and WebP, up to 20 MiB each.

**System status** in Settings refreshes every five seconds. It shows service connectivity, available dependencies and the current processing stage. Weight labels distinguish files found from a model actually loaded. Dependency checks confirm that packages are present; model compatibility is checked when the weights load.

Optional settings apply to the next assessment:

- **Include heatmap** applies immediately to the next sample or upload; **Save changes** remembers the preference across reloads. It adds signed pixel-level Integrated Gradients maps and overlays to the report and takes longer to compute. Red and blue show contributions that increase and decrease the RVL Score relative to a blurred version of the same image; zero is transparent in the overlay. These maps explain model attribution, not lesion location. If the attribution fails its convergence check, the report marks the heatmap unavailable. The online demo does not calculate heatmaps.
- **AI-assisted interpretation** rephrases the positive or negative prediction statement through your configured service. Enter its **API URL**, **Model** and **API key** in Settings. A remote service requires internet access and receives only the modality, RVL Score and predicted probability—not images or examination details. Without LLM access, the report uses threshold-based interpretation.

### IG display

IG explains the fixed logit margin `logits[1] - logits[0]` against a blurred reference. The displayed pixel map sums signed RGB-channel attributions, retaining both signs. For display only, the attribution map receives Gaussian smoothing with σ=1 pixel. Its symmetric red–blue scale uses the 99th percentile of the absolute **raw**, unsmoothed pixel map; values outside that range saturate. The −1 / 0 / +1 legend is a relative display scale, not raw IG units, and intensities are not comparable between images.

Overlay opacity increases linearly with the absolute normalized display value, from zero at zero attribution to a maximum of 0.5. Both the original panel and overlay base use the unchanged model-input image; smoothing applies only to the attribution map. Raw signed values remain available in the attribution data. Reported map-stability diagnostics refer to the native patch grid, not pixel-level stability; convergence does not establish precise lesion localization.

## Troubleshooting

| Problem | What to do |
|---|---|
| macOS cannot verify `start.command` | If you downloaded JingWei from this repository, open **System Settings → Privacy & Security** after the blocked launch. Under **Security**, select **Open Anyway** for `start.command`, then confirm **Open**. You can then double-click the launcher as usual. See [Apple’s instructions](https://support.apple.com/en-us/102445). |
| Installation stops during a download | Check your internet connection and run the launcher again. |
| Weights are not found | Check the file path for the selected modality in Settings and select **Save changes**. The other modality is optional. |
| The browser does not open | Keep the terminal running and open the address printed there, usually **http://127.0.0.1:8765/**. Open the app through this address rather than `index.html`. |
| The app is already running | Use the existing browser page. To restart it, stop the previous terminal with **Ctrl+C**, then run the launcher again. |

For other problems, [open an issue](https://github.com/laleoarrow/jingwei-uveitis/issues) with your operating system and the error shown in the terminal.

[Reference data](data/README.md) · [Optional report fonts](static/fonts/README.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
