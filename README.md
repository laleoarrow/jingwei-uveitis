# JingWei · 精卫

JingWei: non-invasive prediction system of retinal vascular leakage in uveitis from fundus photography or OCT.

**[Online demo](https://laleoarrow.github.io/jingwei-uveitis/) · [Installation](#installation) · [Use](#use)**

The online demo shows the workflow and report format using fixed example results. Follow the steps below to analyse images offline on your computer.

**Model weights are supplied separately. Access details will be announced later.** The interface can open without them, but image analysis requires the weights.

## Installation

Complete steps 1–4 once. Internet access is needed to download the application and its dependencies.

### 1. Install Python 3.12

Choose your system:

- **macOS (Apple silicon):** install [Homebrew](https://brew.sh/) if needed, then open **Terminal** and run `brew install python@3.12`.
- **Windows (64-bit x86):** install the [Python Install Manager](https://www.python.org/downloads/), then open **PowerShell** and run `pymanager install 3.12`.
- **Ubuntu 24.04:** open **Terminal** and run `sudo apt update`, followed by `sudo apt install python3.12 python3.12-venv`.

Check with `python3.12 --version` on macOS/Linux, or `py -3.12 --version` on Windows. It should show **Python 3.12.x**.

### 2. Download and install JingWei

Download the [source ZIP](https://github.com/laleoarrow/jingwei-uveitis/archive/refs/heads/main.zip) and extract it into **Downloads**. The folder should be named `jingwei-uveitis-main` and contain `launch.py` and `requirements.txt`.

Run the commands for your system, one line at a time. If you saved the folder elsewhere, change the first line to its location. These commands create a separate Python environment inside the project.

<details open>
<summary><strong>macOS — Terminal</strong></summary>

```sh
cd ~/Downloads/jingwei-uveitis-main
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

</details>

<details>
<summary><strong>Windows — PowerShell</strong></summary>

```powershell
cd "$HOME\Downloads\jingwei-uveitis-main"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

</details>

<details>
<summary><strong>Linux — Terminal</strong></summary>

```sh
cd ~/Downloads/jingwei-uveitis-main
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

</details>

Installation may take several minutes. When complete, the last command should print **`No broken requirements found.`**

### 3. Add the model weights

After receiving the weight files, create a folder named `weights` beside `launch.py` and place the files there:

| Input | File location |
|---|---|
| CFP | `weights/CFP.pth` |
| OCT | `weights/OCT.pth` |

If the supplied files have different names, enter their actual paths in Settings. **Both files are needed to save Settings in the current version.**

If you are still waiting for the weights, you can continue to step 4 to open the interface and complete configuration later.

### 4. Start and configure the app

From the same project folder, run:

**macOS / Linux**

```sh
.venv/bin/python launch.py
```

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe launch.py
```

The browser should open **http://127.0.0.1:8765/**. If it does not, enter that address in Chrome or Edge. **Keep the terminal window open** while using the app.

In the webpage, open **Settings**:

1. Set the **CFP** path to `weights/CFP.pth` and the **OCT** path to `weights/OCT.pth`. Full file paths also work; enter them without quotation marks.
2. Leave **Processing device** on **Automatic**. It uses Apple MPS when available, otherwise CPU.
3. Leave **Include heatmap** and **Use LLM** unchecked for the first run. The institution name is optional.
4. Select **Save changes**. The message **“Saved for the next analysis.”** confirms that settings were saved.

## Use

### 5. Run an assessment and generate a report

1. Return to **Analysis** and select **CFP** or **OCT**.
2. Select **Use sample** to check the setup with an AI-generated example, or select **Browse files** to upload your image. Enter examination details before uploading if required.
3. Wait for the **RVL Score**, **predicted probability** and **analysis time** to appear. The first run can take longer while the model loads.
4. Select **Generate report**, then **Print / Save PDF**. In the print dialog, choose **Save as PDF**, **A4**, **100% scale**, and turn off browser **headers and footers**.

Supported images: JPEG, PNG, single-page TIFF and WebP, up to 20 MiB each. **Use sample** runs actual analysis in the offline app and requires the configured weights.

Optional settings apply to the next assessment:

- **Include heatmap:** adds contributing-region maps to the report and takes longer to compute.
- **Use LLM:** enter your service's **API URL**, **Model** and **API key**, then save. Without LLM access, the report uses threshold-based interpretation automatically. A remote LLM requires network access; only the modality, score and probability are sent, not images or examination details.

## Reopen or stop

After the first installation, double-click **`start.command`** on macOS or **`start.bat`** on Windows. On Linux, use the launch command in step 4. Packages and saved settings do not need to be installed or entered again.

Press **Ctrl+C** in the terminal to stop the app. Closing the browser tab alone does not stop it.

## If something does not work

- **Python or a file cannot be found:** check the Python version and confirm that the terminal is in the folder containing `launch.py`.
- **Weights not found / settings will not save:** check that both weight files are present and their paths are correct.
- **The webpage will not open:** keep the launch command running and use the HTTP address it prints, rather than opening `index.html` directly. If port `8765` is occupied, append `--port 8766` to the launch command and use `http://127.0.0.1:8766/`.

The app has been exercised on Apple silicon macOS, with automated tests on Ubuntu. A complete Windows setup has not yet been verified.

[Reference data](data/README.md) · [Optional report fonts](static/fonts/README.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
