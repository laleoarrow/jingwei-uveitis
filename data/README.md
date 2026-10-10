# Bundled reference distributions

`reference_distributions.json` contains 12 frozen aggregate responses: two image modalities and six validation cohorts. The application reads this file directly and needs neither the original study repository nor its CSV. No patient records, individual image rows, filenames, or source-row identifiers are included.

The observation unit is an **image**, not a patient or an eye-visit. Each class contains its image count, minimum, quartiles, maximum, and sampled density curve. Labels are `1` for RVL-positive and `0` for RVL-negative; groups retain that order.

| Cohort | CFP positive / negative | OCT positive / negative |
| --- | ---: | ---: |
| UC-FAH-CQMU | 1,943 / 962 | 5,864 / 3,704 |
| UC-FAH-CQMU, temporal validation | 247 / 124 | 376 / 262 |
| EENT-FDU | 385 / 179 | 712 / 322 |
| FAH-ZZU | 309 / 205 | 492 / 368 |
| OC-JLU2H | 49 / 0 | 11 / 0 |
| PROTON | 120 / 21 | 107 / 20 |
| **Total images** | **4,544** | **12,238** |

## Provenance and numerical definition

- Source: the retained Figure 2 export, `rvl_score_source_data.csv`.
- Source CSV SHA-256: `d6bb68a18b99aa47346a82fd37498330b1a020f75fd8fddf0d6b83e37ff73d8d`.
- RVL Score: `logit_1 - logit_0`; predicted probability: `sigmoid(RVL Score)`.
- Density: SciPy `gaussian_kde` with Scott bandwidth, evaluated at 256 equally spaced points from each class's observed minimum to maximum. Each curve is divided by its own peak. No tails are extended and no endpoint is forced to zero.
- Quantiles: NumPy's default linear quantiles at 0, 0.25, 0.5, 0.75, and 1. The response range is the union of the two observed class ranges.
- A missing class has count zero, null statistics, and empty curves. The exporter represents singleton/constant groups as one point with density 1, without inventing a KDE.
- Frozen export environment: NumPy **2.4.1**, SciPy **1.16.1**. Version information is also stored in the JSON provenance.

During migration, all 12 bundled responses were compared directly with the original application's `get_reference` responses and were **exactly equal**, including every stored floating-point value. `test_reference.py` freezes SHA-256 hashes of the original responses using canonical JSON, alongside explicit denominator, quantile, range, curve, and missing-class checks. The reference reader and these tests use only the Python standard library.

## Optional offline regeneration

The source CSV is deliberately not distributed. A maintainer with an authorized source export can run the following from the application directory, using the recorded NumPy/SciPy versions:

```sh
python scripts/export_reference.py --source /path/to/rvl_score_source_data.csv
python -S -m unittest test_reference.py -v
```

`--output /path/to/aggregate.json` selects an alternative destination for review. The exporter reads only the supplied CSV, does not modify it, and writes aggregate responses and provenance. It is not imported by the running application. Deliberate source or calculation changes require review and updated frozen-response tests; a new source hash alone does not establish compatibility with different model weights.
