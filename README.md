# JingWei · 精卫

JingWei: non-invasive prediction system of retinal vascular leakage in uveitis from fundus photography or OCT.

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

**Model weights are supplied separately. Access details will be announced later.** You can open the interface without weights, but image analysis requires them.

Once you receive the files, open **Settings**, enter the file path for **CFP**, **OCT**, or both, and select **Save changes**. Keep the original filenames; you can paste an absolute path, including one copied with quotation marks. Leave an unused modality blank.

Alternatively, these default locations are recognised automatically:

| Input | File location |
|---|---|
| CFP | `weights/CFP.pth` |
| OCT | `weights/OCT.pth` |

Leave **Processing device** on **Automatic** and **Include heatmap** and **Use LLM** unchecked for the first assessment.

## Use

1. Select **CFP** or **OCT** in **Analysis** and enter examination details if needed.
2. Select **Browse files** to upload an image, or **Use sample** to check the setup with an AI-generated example. The offline sample runs actual analysis and requires the weights.
3. Wait for the **RVL Score**, **predicted probability** and **analysis time**. The first assessment can take longer while the model loads.
4. Select **Generate report**, then **Print / Save PDF**. For PDF export, choose **A4**, **100% scale**, and turn off browser **headers and footers**.

Supported images: JPEG, PNG, single-page TIFF and WebP, up to 20 MiB each.

Optional settings apply to the next assessment:

- **Include heatmap** adds contributing-region maps to the report and takes longer to compute.
- **Use LLM** adds interpretation through your configured service. Enter its **API URL**, **Model** and **API key** in Settings. A remote service requires internet access and receives only the modality, score and probability—not images or examination details. Without LLM access, the report uses threshold-based interpretation.

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
