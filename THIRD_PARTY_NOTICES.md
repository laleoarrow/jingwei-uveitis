# Third-party materials and licensing

The JingWei repository is distributed under the Creative Commons
Attribution–NonCommercial 4.0 International licence (CC BY-NC 4.0).
Separately identified third-party materials remain subject to their original
notices and licences. See [LICENSE](LICENSE) for the repository licence.

## Bundled scientific code

`vendor/models_vit.py` contains adapted RETFound/MAE code under **CC BY-NC 4.0**.
See [vendor/NOTICE.md](vendor/NOTICE.md) for authorship, pinned upstream sources,
local modifications, and the [complete license](vendor/LICENSE.RETFound).
Noncommercial and attribution conditions apply to that component. The
separately installed Python packages retain their own license files and notices.

## Report fonts and lettering

Helvetica Neue LT Std font programs are not part of the public source or release
package. They must be provided locally under an appropriate license; a desktop
font license or an embedding flag does not by itself establish web-font
redistribution rights. See [static/fonts/README.md](static/fonts/README.md).
The report font filenames in CSS are integration points, not a license grant.

`static/jingwei-wordmark.svg` contains fixed JINGWEI lettering as vector outlines,
created locally from macOS Baskerville SemiBold; it contains no font program.
It is the project's own wording, not a Mayo Clinic logo. Clinical-report samples
were consulted for layout and typography; their logos, report pages, and patient
content are not redistributed here.

## Models, data, and runtime files

Study checkpoints, individual-level research records, patient images, and saved
patient reports are not included in the public package. Any bundled reference
distribution consists of aggregate values, not a grant to the underlying data.
Use of externally obtained weights or data remains subject to their own terms.

Local settings, including optional LLM API credentials, local fonts, virtual
environments, and model weights must remain outside Git and release archives.
