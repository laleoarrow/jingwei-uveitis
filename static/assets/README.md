# Generated demonstration images

These fictional CFP and OCT images were created with the built-in image_gen tool on 11 October 2026. They are illustrative interface assets, not patient records or validated clinical acquisitions. The offline app runs model inference on these images; these outputs demonstrate the workflow and do not validate the generated anatomy. GitHub Pages uses fixed illustrative scores.

- `sample-cfp-generated.png`: synthetic colour fundus photograph.
- `sample-oct-generated.png`: synthetic macular OCT B-scan.

## CFP prompt

Use case: scientific-educational
Asset type: synthetic colour fundus photograph for the sample button in a retinal imaging software demo.
Primary request: create one highly realistic standard-field colour fundus camera image, like an unannotated clinical acquisition, not a diagram, illustration, or external photograph of an eye.
Subject: a single plausible human posterior retinal pole, approximately 45-degree field. A pale peach optic disc nasal to the darker macula, a subtle central cup, branching red retinal arterioles and darker venules radiating from the disc with natural superior and inferior arcades, a vessel-free foveal centre. Fine orange-red retinal texture, gentle illumination variation, small realistic optical softness and sensor noise. Avoid exaggerated pathology; the purpose is workflow demonstration, with no implied diagnostic label.
Composition: square raster, retinal circular field nearly fills frame, thin black corners outside the optical field, macula and disc both visible; natural fundus-camera perspective. Authentic muted clinical colours and exposure, no glossy rendering or artistic depth of field.
Constraints: generated fictional anatomy, not an actual patient record. No text, no identifiers, no labels, no logos, no border, no arrows, no heatmap, no duplicated optic discs, no impossible vessel mesh. The surrounding UI will identify the asset as AI-generated and all scores as illustrative.

## OCT prompt

Use case: scientific-educational
Asset type: synthetic grayscale retinal OCT B-scan for the sample button in a retinal imaging software demo.
Primary request: create one highly realistic unannotated macula-centred optical coherence tomography B-scan, resembling the retinal cross-section exported from a clinical spectral-domain OCT scanner, not a diagram or artistic landscape.
Subject: retinal layers spanning the entire image horizontally, dark vitreous above, a natural shallow central foveal depression, alternating finely textured hyperreflective and hyporeflective retinal bands, narrow bright outer retinal/RPE bands following a gently curved contour, granular choroid beneath with subtle signal attenuation into black. Realistic OCT speckle throughout the tissue and faint noise in the vitreous; natural modest shadows beneath vessels. Typical non-pathological macular anatomy, no exaggerated cysts or holes. The asset conveys acquisition appearance, not a disease label.
Composition: square clinical crop, no scanner interface or fundus inset. Retinal tissue occupies the middle third, vitreous approximately upper third, choroidal signal fading below. Horizontal scan geometry, plausible layer thickness, imperfect low-contrast clinical texture rather than perfectly smooth lines.
Constraints: monochrome black and grey only; generated fictional anatomy, not an actual patient record. No text, identifiers, measurements, calipers, colour, arrows, logos, borders, segmentation lines or heatmap. The UI will identify the asset as AI-generated and all scores as illustrative.

