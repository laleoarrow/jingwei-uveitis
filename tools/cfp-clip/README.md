# JingWei CFP Crop

An optional JingWei companion for cropping widefield CFP images to a macula-centred field. It runs independently on your computer.

## Start

Download the separate **JingWei-CFP-Crop** attachment from [JingWei Releases](https://github.com/laleoarrow/jingwei-uveitis/releases), extract it, and open **JingWei CFP Crop.app** (macOS) or **JingWei-CFP-Crop.exe** (Windows). These standalone packages include Python. The interface opens in your browser; use **Quit tool** when finished.

For the source package, install Python 3.10–3.13, then double-click `start.command` on macOS or `start.bat` on Windows; on Linux, run `bash start.command`. First launch installs dependencies into this tool's own `.venv` and requires internet. Manual cropping works offline.

## Crop

1. Choose a folder or individual images. Folder import reads only the top level.
2. Click **1 · Optic disc**, then **2 · Macular centre**, or use **Auto-place points** with your OpenAI API key (default model: `gpt-6-sol`).
3. Drag either point to adjust it. Zoom with **+ / −** or the mouse wheel, select **Move** to pan, and use **Fit** to see the whole image. Review the preview, then select **Keep crop & next**.
4. Select **Export crops** to download the retained crops as a ZIP. Extract it to obtain the `<folder>_clip` directory with the original filenames.

The second point is the centre; the radius is **1.5 × the disc–macula distance**. The crop uses the original image resolution, clips at the image boundary and fills outside the circle with black.

Select **Export crops** before closing to save your work. Each session starts a new image set; original files are preserved.

**Auto-place:** Open **API settings**, enter your key, and select **Auto-place points**. This sends the current image to OpenAI and returns two suggested points for review; it does not keep a crop automatically. The key is used only for this browser session and is not saved. API requests are billed to your OpenAI account.

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
