# Source and method provenance

The circular crop is adapted from the user-supplied `cfp_clip.zip`,
`cfp_clip/image_clip_tool.py` (SHA-256
`0d3555150f956e979ed4279af96bce8fb34f7e00ccb6f323327069443a3963f8`).
The archive identifies its upstream repository as
https://github.com/KKYYJZ1220/cfp_clip. Its original Git history, executables,
build outputs and environment are not included here. The supplied archive had
no separate licence file; original authorship is retained.

The original geometry is retained: point two is the circle centre; radius is
1.5 times the distance between the two points; the bounding box uses floor/ceil,
is limited to the source boundary, and pixels outside the circle are black.
New work comprises the independent browser interface, local service, validation,
tests and packaging. The main JingWei application is not imported or modified.

The manuscript's preprocessing description specifies manually identified
macular and optic-disc landmarks and a macula-centred field. Together with the
original implementation, this establishes the interface order: optic disc,
then macular centre. The factor 1.5 comes from the supplied code, not the
manuscript text. No more specific optic-disc landmark definition is inferred.

The wordmark is copied from JingWei's `static/jingwei-wordmark.svg`: fixed vector
lettering, with no font program. New JingWei material follows the repository's
CC BY-NC 4.0 licence. The launchers download uv, Python and Pillow on first
start; these components retain their own licences and distribution notices.
