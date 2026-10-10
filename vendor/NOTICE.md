# Bundled scientific implementation

These files were extracted from the local BDRV project on 2026-10-10 to make
JingWei independent of its former parent directory. The source project is
provenance only; it is not read at runtime.

- `models_vit.py`: `code/RETFound/models_vit.py` in BDRV. Original source SHA-256:
  `9de484e23477b823eecdb582d5755b7a93a1965329e3d29797653b712bdf75dd`.
  Only `VisionTransformer`, `RETFound_mae`, and `RETFound_dinov2` are retained;
  their definition bodies are unchanged. Unused model families and imports are
  excluded. The DINOv2 constructor keeps `pretrained=False`; weights are supplied
  locally and never downloaded by this module.
- `architecture_cam.py`: `code/visualization/generate_architecture_test_heatmaps.py`
  in BDRV. Original source SHA-256:
  `ed23120ae9923c9af1cc7108e06786bd771062d45c771aa46c2af6c2ccae7a1b`.
  `LogitMarginTarget`, `ArchitectureCAM`, and their helper definitions are
  unchanged. Batch-generation CLI and reporting metadata are excluded.

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

`architecture_cam.py` is extracted from the local BDRV implementation described
above. Its source file and directory did not specify a license. This notice
does not assign it a license or imply that the RETFound license covers it.
Algorithm names describe the implemented methods; they do not imply that code
from a similarly named third-party package was copied. The application does not
vendor or require `pytorch-grad-cam`.

The external `timm`, `torch`, and other installed packages retain their own
distributions and licenses; they are dependencies rather than copied source
in this directory. No affiliation with or endorsement by the upstream projects
is implied.
