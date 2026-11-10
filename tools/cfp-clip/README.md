# JingWei Crop · 精卫裁剪 v1.0.0

An optional JingWei companion for cropping widefield CFP images to a macula-centred field. It runs independently on your computer.

## Start

Download the [JingWei Crop ZIP](https://github.com/laleoarrow/jingwei-uveitis/releases/download/v1.0.0/JingWei-Crop-v1.0.0.zip) and extract it. The same package supports macOS, Windows and Linux.

| System | Start |
|---|---|
| macOS | Double-click **`start.command`**. |
| Windows | Double-click **`start.bat`**. |
| Linux | Open a terminal in the extracted folder and run **`bash start.command`**. |

The launcher prepares Python 3.12 and dependencies in this tool's own folder, then opens the interface in your browser. No separate Python installation, JingWei installation or model weights are needed. First launch requires internet; manual cropping then works offline. Keep the terminal open and use **Quit tool** when finished.

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
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python build_release.py
python tests/smoke_package.py dist/JingWei-Crop-v1.0.0.zip
```

Use Python 3.12 for development. The single ZIP in `dist/` contains the application and all launchers. The **JingWei Crop packages** workflow tests it on Windows, including first-time setup and an offline restart. Attach this ZIP separately to a JingWei release. The smoke test requires internet for the first installation.

This directory is self-contained, with its own version, environment, tests and release schedule. See [AGENTS.md](AGENTS.md) for maintenance, [NOTICE.md](NOTICE.md) for provenance and [LICENSE](LICENSE) for the JingWei additions' licence.
