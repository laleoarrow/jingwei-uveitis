# JingWei CFP Crop

An optional JingWei companion for cropping widefield CFP images to a macula-centred field. It runs independently on your computer.

## Start

Download the separate **JingWei-CFP-Crop** attachment from [JingWei Releases](https://github.com/laleoarrow/jingwei-uveitis/releases), extract it, and open **JingWei CFP Crop.app** (macOS) or **JingWei-CFP-Crop.exe** (Windows). These standalone packages include Python. The interface opens in your browser; use **Quit tool** when finished.

For the source package, install Python 3.10–3.13, then double-click `start.command` on macOS or `start.bat` on Windows; on Linux, run `bash start.command`. First launch installs Pillow into this tool's own `.venv` and requires internet. Subsequent use is offline.

## Crop

1. Choose a folder or individual images. Folder import reads only the top level.
2. Click **1 · Optic disc**, then **2 · Macular centre**.
3. Review the circle and preview, then select **Keep crop & next**.
4. Select **Export crops** to download the retained crops as a ZIP. Extract it to obtain the `<folder>_clip` directory with the original filenames.

The second point is the centre; the radius is **1.5 × the disc–macula distance**. The crop uses the original image resolution, clips at the image boundary and fills outside the circle with black.

Select **Export crops** before closing to save your work. Each session starts a new image set; original files are preserved.

**Keys:** Enter keeps the crop and advances; ← / → navigate; Backspace clears the points. The controls also work with a mouse.

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
