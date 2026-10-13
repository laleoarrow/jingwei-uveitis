# Bundled scientific implementation

These files were extracted from the local BDRV project to make
JingWei independent of its former parent directory. The source project is
provenance only; it is not read at runtime.

- `models_vit.py`: `code/RETFound/models_vit.py` in BDRV. Original source SHA-256:
  `9de484e23477b823eecdb582d5755b7a93a1965329e3d29797653b712bdf75dd`.
  Only `VisionTransformer`, `RETFound_mae`, and `RETFound_dinov2` are retained;
  their definition bodies are unchanged. Unused model families and imports are
  excluded. The DINOv2 constructor keeps `pretrained=False`; weights are supplied
  locally and never downloaded by this module.
- `architecture_cam.py` (historical, no longer used by the application): `code/visualization/generate_architecture_test_heatmaps.py`
  in BDRV. Original source SHA-256:
  `ed23120ae9923c9af1cc7108e06786bd771062d45c771aa46c2af6c2ccae7a1b`.
  `LogitMarginTarget`, `ArchitectureCAM`, and their helper definitions are
  unchanged. Batch-generation CLI and reporting metadata are excluded.

- `integrated_gradients.py`: signed IG functions from
  `code/visualization/generate_ig_heatmaps.py` in BDRV, commit `1248f82`,
  extracted 2026-10-13. Original source SHA-256:
  `24dae6bb44905e60362c1baa16821fc1c3b993446d8040db5b0c132dccbdcd5f`.
  The Captum integration, blurred baseline, native patch aggregation, convergence
  checks and adaptive refinement are retained. Two device transports change:
  pixel attributions and endpoint scores move to CPU before conversion to float64
  (Apple MPS cannot represent float64). Model forwards and input gradients still
  run on the selected device. Dataset/checkpoint loading and CLI are excluded.
  The local pixel-map extension returns raw RGB-channel-summed attribution at the
  input resolution alongside native patch sums. Adaptive refinement accumulates
  high-order pixel attributions from all final retained leaves; integration and
  native-grid convergence criteria are unchanged. These criteria do not establish
  pixel-level stability. The application follows the source CLI's 32-to-512 step
  schedule and 8,192-evaluation refinement budget and renders only converged maps.
  OCT retains its existing single-token forward adapter.
  The local `pixel_ig_display` helper smooths signed pixel attribution with OpenCV
  Gaussian sigma 1 and reflection borders, uses symmetric raw absolute-P99 colour
  limits (raw maximum-absolute fallback for a nonzero map with P99=0), and draws
  a blue/white/red heatmap. It calls the unchanged source `signed_overlay` with
  image weight 0.5. Raw values and the RGB background are not altered. The obsolete
  positive Jet helper and maximum-normalization helper are no longer bundled.

## RETFound and MAE attribution

`models_vit.py` derives from the RETFound authors' implementation:

- [RETFound repository](https://github.com/rmaphoh/RETFound)
- [Upstream model source inspected on 2026-10-10](https://github.com/rmaphoh/RETFound/blob/ae9a9ecf37857cf47b8aa9f87cd6f710d75db287/models_vit.py)
- [Upstream license at that revision](https://github.com/rmaphoh/RETFound/blob/ae9a9ecf37857cf47b8aa9f87cd6f710d75db287/LICENSE)

RETFound distributes this source under **Creative Commons Attribution-
NonCommercial 4.0 International (CC BY-NC 4.0)**. The complete, unmodified license
text, including its warranty disclaimer, is included as [LICENSE.RETFound](LICENSE.RETFound).
Its SHA-256 is `517acfe79046fca3d989a5a6f8b55b8c3919bb442609bd9ed0e81af6e25deb3a`.
The upstream revision above records the license/source review, not the unknown
original import revision of the local BDRV copy.

The VisionTransformer implementation also derives from
[Meta's MAE model source](https://github.com/facebookresearch/mae/blob/efb2a8062c206524e35e47d04501ed4f544c0ae8/models_vit.py):
Copyright (c) Meta Platforms, Inc. and affiliates. All rights reserved.
[MAE's license](https://github.com/facebookresearch/mae/blob/efb2a8062c206524e35e47d04501ed4f544c0ae8/LICENSE)
is also CC BY-NC 4.0. Existing inline acknowledgments, including the CLS-token
implementation acknowledgment, are retained.

The local changes relative to RETFound are the offline `pretrained=False`
DINOv2 constructor and the extraction described above. The singleton dimension
in MAE patch-average pooling is retained as in RETFound; it differs from the
earlier Meta MAE implementation. No pretrained or study-trained model weights
are included in this repository. Source-code notices do not grant rights to
separately obtained weights.

## Local attribution implementation

`architecture_cam.py` and `integrated_gradients.py` are extracted from the local
BDRV implementations described above. Their source files and directories did
not specify a license. This notice does not assign them a license or imply that
the RETFound license covers them.
Algorithm names describe the implemented methods; they do not imply that code
from a similarly named third-party package was copied. The application does not
vendor or require `pytorch-grad-cam`.

IG uses the separately installed Captum package (BSD-3-Clause); its source is
not copied here. Display smoothing uses the separately installed
`opencv-python-headless` distribution; the blue/white/red heatmap uses Matplotlib.
Their included licenses apply to those distributions.

The external `captum`, `timm`, `torch`, and other installed packages retain their own
distributions and licenses; they are dependencies rather than copied source
in this directory. No affiliation with or endorsement by the upstream projects
is implied.
