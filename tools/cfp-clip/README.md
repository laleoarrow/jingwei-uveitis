# JingWei CFP Crop v1.0.0

An optional JingWei companion for cropping widefield CFP images to a macula-centred field. It runs independently on your computer.

## Start

**Windows:** Download the [Windows app](https://github.com/laleoarrow/jingwei-uveitis/releases/download/v1.0.0/JingWei-CFP-Crop-v1.0.0-Windows-amd64.zip), extract it, and open **JingWei-CFP-Crop.exe**. Python is included. The interface opens in your browser; use **Quit tool** when finished.

**macOS, Linux or source use:** Download the [source package](https://github.com/laleoarrow/jingwei-uveitis/releases/download/v1.0.0/JingWei-CFP-Crop-v1.0.0-source.zip) and install Python 3.10–3.13. After extracting, double-click `start.command` on macOS or `start.bat` on Windows; on Linux, run `bash start.command`. First launch installs dependencies into this tool's own `.venv` and requires internet. Manual cropping works offline.

## Crop

1. Choose a folder or individual images. Folder import reads only the top level.
2. Click **1 · Optic disc**, then **2 · Macular centre**, or use **Auto-place points** with your API key (default model: `gpt-6-sol`).
3. Drag either point to adjust it. Zoom with **+ / −** or the mouse wheel, select **Move** to pan, and use **Fit** to see the whole image. Review the preview, then select **Keep crop & next**.
4. Select **Export crops** and choose where to save the ZIP. Wait for **ZIP saved**; browsers without a save dialog start a download instead, so check the saved file in Downloads. Extract it to obtain the `<folder>_clip` directory with the original filenames.

The second point is the centre; the radius is **1.5 × the disc–macula distance**. The crop uses the original image resolution, clips at the image boundary and fills outside the circle with black.

Each browser tab has its own image set and crops. Export before closing; closing one tab releases its workspace without affecting other tabs. Original files are preserved.

**Auto-place:** Open **API settings** and enter the base URL, key and model for a Responses API service supporting image input and strict JSON-schema output. The default URL is `https://api.openai.com/v1`; it can be changed to your provider's address. **Auto-place points** sends the current image to that service and returns two suggested points for review; it does not keep a crop automatically. The key is used only for this browser session and is not saved. API requests use your provider account.

The latest request's duration and reported token usage appear below **Auto-place points**, with input/output counts. Usage is also shown when the model's response could not supply usable points; unavailable counts are left blank.

**Keys:** Enter keeps the crop and advances; ← / → navigate; Backspace clears the points. Hold Space and drag to pan. Zoom and pan leave the original image coordinates unchanged.

**Formats:** JPEG, PNG, BMP, TIFF, GIF and WebP. EXIF orientation is applied before point selection. Multi-frame files use their first frame. Outputs retain the input extension and Pillow's default encoding; JPEG/WebP may be recompressed. No source metadata is copied to the crops.

## Development and release

```bash
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests
python build_release.py             # standalone source ZIP
python build_release.py --native    # native package on the current OS
```

Outputs are under `dist/`. Build macOS packages on macOS; use Windows or the **CFP Crop packages** workflow for the Windows package. Attach the resulting ZIPs separately to a JingWei release.

This directory is self-contained, with its own version, environment, tests and release schedule. See [AGENTS.md](AGENTS.md) for maintenance, [NOTICE.md](NOTICE.md) for provenance and [LICENSE](LICENSE) for the JingWei additions' licence.
