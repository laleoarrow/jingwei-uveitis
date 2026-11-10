# Independent companion: JingWei Crop

This directory is a self-contained optional application. It is not a module of
the main JingWei application. It must keep working when copied outside this
repository.

- Limit JingWei Crop work to this subtree and its dedicated
  `.github/workflows/cfp-clip.yml`. Update the main README only when its short
  download pointer needs changing.
- Do not import, load, or modify the parent app's code, settings, dependencies,
  models, launchers, assets, demo or runtime data. Assets here are independent
  copies; never add runtime paths back to the parent directory.
- Use this directory's `.venv`, requirements, tests and `build_release.py`.
  Run `python -m unittest discover -s tests` from this directory, JavaScript
  syntax checks, and the browser crop/export flow for relevant changes.
- Preserve the supplied circular crop geometry and its pixel-level tests.
  Point 1 is the optic-disc landmark; point 2 is the macular centre. The radius
  is 1.5 times their distance. This is not calibrated field-of-view conversion.
- Keep its version independent of JingWei. Release only separate JingWei Crop
  attachments; never add this tool or its requirements to the main app ZIP.
- Exclude temporary images, environments, builds and archives from Git.
  Do not add `__init__.py` to this directory or `tests/`: main-app unittest
  discovery must not start importing the optional tool.
