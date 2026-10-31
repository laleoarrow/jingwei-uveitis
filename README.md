<h1><img src="docs/assets/jingwei-title.svg" align="top" width="220" height="40" alt="JingWei · 精卫"> <img src="docs/assets/jingwei-logo.svg" align="right" width="110" height="110" alt="JingWei bird logo in a green circular frame" /></h1>

JingWei predicts retinal vascular leakage (RVL) in uveitis from a single optical coherence tomography (OCT) or color fundus photography (CFP) image, with fundus fluorescein angiography (FFA) as the reference standard. It runs locally in a browser and provides an RVL Score, predicted probability, optional Integrated Gradients heatmaps, and printable reports.

<p align="center">
  <a href="https://github.com/laleoarrow/jingwei-uveitis/actions/workflows/checks.yml"><img align="texttop" alt="Checks" src="https://img.shields.io/github/actions/workflow/status/laleoarrow/jingwei-uveitis/checks.yml?branch=main&amp;event=push&amp;label=Checks&amp;style=for-the-badge&amp;logo=githubactions&amp;logoColor=white&amp;labelColor=334B49"></a>
  <a href="https://laleoarrow.github.io/jingwei-uveitis/"><img align="texttop" alt="Pages deployment" src="https://img.shields.io/github/deployments/laleoarrow/jingwei-uveitis/github-pages?label=Pages&amp;style=for-the-badge&amp;logo=github&amp;logoColor=white&amp;labelColor=334B49"></a>
  <a href="#3-configure-the-weights"><img align="texttop" alt="Weights download" src="https://img.shields.io/badge/Weights-Download-2D6F58?style=for-the-badge&amp;logo=pytorch&amp;logoColor=white&amp;labelColor=334B49"></a>
  <br>
  <a href="#installation"><img align="texttop" alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-2D6F58?style=for-the-badge&amp;logo=python&amp;logoColor=white&amp;labelColor=334B49"></a>
  <a href="#use"><img align="texttop" alt="Inputs OCT and CFP" src="https://img.shields.io/badge/Inputs-OCT%20%7C%20CFP-2D6F58?style=for-the-badge&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGZpbGwtcnVsZT0iZXZlbm9kZCIgZD0iTTQgM2gxNmEyIDIgMCAwIDEgMiAydjE0YTIgMiAwIDAgMS0yIDJINGEyIDIgMCAwIDEtMi0yVjVhMiAyIDAgMCAxIDItMlptMCAydjE0aDE2VjVINFptMiAxMiA0LTUgMyAzIDItMiAzIDRINlptMTEtOWEyIDIgMCAxIDEtNCAwIDIgMiAwIDAgMSA0IDBaIi8%2BPC9zdmc%2B&amp;logoColor=white&amp;labelColor=334B49"></a>
  <a href="#2-start-jingwei"><img align="texttop" alt="Platforms macOS Windows Linux" src="https://img.shields.io/badge/Platforms-macOS%20%7C%20Windows%20%7C%20Linux-2D6F58?style=for-the-badge&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0id2hpdGUiIGZpbGwtcnVsZT0iZXZlbm9kZCIgZD0iTTMgM2gxOGEyIDIgMCAwIDEgMiAydjEyYTIgMiAwIDAgMS0yIDJoLTh2Mmg0djJIN3YtMmg0di0ySDNhMiAyIDAgMCAxLTItMlY1YTIgMiAwIDAgMSAyLTJabTAgMnYxMmgxOFY1SDNaIi8%2BPC9zdmc%2B&amp;logoColor=white&amp;labelColor=334B49"></a>
</p>

<p>
  <a href="https://laleoarrow.github.io/jingwei-uveitis/">Online demo</a> · <a href="https://github.com/laleoarrow/jingwei-uveitis/releases/tag/v1.0.0">Download</a> · <a href="#installation">Installation</a> · <a href="#3-configure-the-weights">Model weights</a> · <a href="#use">Use</a>
</p>

*Paper: TBD*

The online demo uses fixed illustrative results and AI-generated samples. It does not analyze images or compute heatmaps. For model predictions, install JingWei locally using the steps below.

## Installation

### 1. Download

Download the [JingWei ZIP](https://github.com/laleoarrow/jingwei-uveitis/releases/download/v1.0.0/JingWei-v1.0.0.zip) and extract it. Open the extracted `JingWei-v1.0.0` folder.

Alternatively, clone the repository:

```bash
git clone https://github.com/laleoarrow/jingwei-uveitis.git
cd jingwei-uveitis
```

### 2. Start JingWei

| System | Start |
|---|---|
| macOS (Apple silicon) | Double-click **`start.command`**. |
| Windows (64-bit x86) | Double-click **`start.bat`**. |
| Linux | Open a terminal in the application folder and run **`bash start.command`**. |

The launcher installs Python 3.12 and dependencies in the application folder, then opens **[JingWei](http://127.0.0.1:8765/)** in your browser. No separate Python installation is needed. Initial setup requires internet access and may take several minutes; progress appears in the terminal.

**Keep the terminal open** while using JingWei. Press **Ctrl+C** to stop; use the same launcher to reopen with the existing environment and settings.

### 3. Configure the weights

Model weights are downloaded separately:

| Download source | Access code |
|---|---|
| [**Zenodo**](https://zenodo.org/records/23503796) | — |
| [**Baidu Netdisk**](https://pan.baidu.com/s/1r7gfecgxxbtCQnV0FmZlSg?pwd=7a7c) | `7a7c` |

In **Settings**, enter the weight-file paths for **OCT**, **CFP**, or both, then select **Save changes**. Keep the original filenames; quoted absolute paths are accepted. Leave unused modalities blank.

For the first assessment, set **Processing device** to **Automatic** and leave **Include heatmap** and **AI-assisted interpretation** off.

<details>
<summary>Default weight-file locations</summary>

Alternatively, these default locations are recognized automatically:

| Input | File location |
|---|---|
| OCT | `weights/OCT.pth` |
| CFP | `weights/CFP.pth` |

</details>

### Install with LLM

<details>
<summary>Copy an installation prompt for your AI assistant</summary>

Give your preferred AI assistant the following prompt in a session with terminal access:

```text
Install and launch JingWei from https://github.com/laleoarrow/jingwei-uveitis on this computer.
Follow the README and use the launcher for my operating system. Verify that the offline web app opens.
Ask me for the paths to my OCT and/or CFP weight files and configure them without renaming the files.
If I do not have weights yet, complete installation and explain how to add them later.
```

</details>

## Use

1. Select **OCT** or **CFP** in **Analysis** and enter examination details if needed.
2. Select **Browse files** to upload an image, or **Use sample** to test the setup. AI-generated samples run through the local model and require weights.
3. Wait for the **RVL Score**, **predicted probability** and **analysis time**. The first assessment may take longer as the model loads.
4. Select **Generate report**, then **Print / Save PDF**. For PDF export, choose **A4**, **100% scale**, and turn off browser **headers and footers**.

Supported images: JPEG, PNG, single-page TIFF and WebP, up to 20 MiB each.

### Heatmaps

JingWei uses Integrated Gradients (IG) to show how image regions contribute to the RVL Score.

1. In **Settings**, turn on **Include heatmap**; it is off by default.
2. Return to **Analysis** and upload an image or select **Use sample**.
3. Select **Generate report** to view **Contributing regions**.

The switch applies to the next sample or upload without saving. **Save changes** retains the preference across refreshes. Existing results are unchanged.

The report shows three views under **Contributing regions**:

| View | Contents |
|---|---|
| **Model input** | The crop analyzed by the model. |
| **Heatmap** | The contribution map alone. |
| **Overlay** | The contribution map over the model input. |

Red indicates contributions that increase the RVL Score; blue indicates contributions that decrease it. The reference is a blurred version of the same image, not a healthy eye. These maps explain the model’s output; they do not identify lesions.

Heatmaps add processing time. If the checks fail, the report shows **Heatmap unavailable** and retains the prediction.

### AI-assisted interpretation

This optional service rephrases the positive or negative prediction statement in the report. Numerical results remain fixed.

1. In **Settings**, enable **AI-assisted interpretation**.
2. Enter an OpenAI-compatible **API URL** (e.g. `https://api.example.com/v1`), **Model** and **API key**.
3. Select **Save changes**, then run a new analysis to apply the saved settings.

Remote services require internet access and receive only the modality, RVL Score and probability. Images and patient information are not sent. If the service is unavailable, the report uses a local template.

## Troubleshooting

| Problem | What to do |
|---|---|
| macOS cannot verify `start.command` | If you downloaded JingWei from this repository, open **System Settings → Privacy & Security** after the blocked launch. Under **Security**, select **Open Anyway** for `start.command`, then confirm **Open**. Double-click the launcher again. See [Apple’s instructions](https://support.apple.com/en-us/102445). |
| Installation stops during a download | Check your internet connection and run the launcher again. |
| Weights are not found | Check the file path for the selected modality in Settings and select **Save changes**. The other modality is optional. |
| The browser does not open | Keep the terminal running and open its displayed address, usually **http://127.0.0.1:8765/**, rather than opening `index.html`. |
| The app is already running | Use the existing browser page. To restart, press **Ctrl+C** in the previous terminal, then run the launcher again. |

For other problems, [open an issue](https://github.com/laleoarrow/jingwei-uveitis/issues) with your operating system and the error shown in the terminal.

<details>
<summary>Checking system status</summary>

**System status** in Settings refreshes every five seconds. It normally shows **Service: Online**, **Environment: Ready** (required packages present), and **Activity: Idle** (no task running). Active stages (analyzing, heatmap and refining) show elapsed time. Weight labels distinguish files found from models loaded; compatibility is checked when loading.

</details>

## License

The JingWei application source code is available under the
Creative Commons Attribution–NonCommercial 4.0 International
licence (CC BY-NC 4.0). It may be used, modified, and redistributed
for non-commercial purposes with appropriate attribution.

[Reference data](data/README.md) · [Optional report fonts](static/fonts/README.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
