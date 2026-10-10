"""Optional offline exporter; the application only reads its aggregate JSON output."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import scipy
from scipy.stats import gaussian_kde

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reference import COHORTS


def summarize_group(values, label):
    values = np.asarray(values)
    group = {"label": label, "n": len(values), "min": None, "q1": None,
             "median": None, "q3": None, "max": None, "x": [], "density": []}
    if len(values):
        quantiles = np.quantile(values, [0, .25, .5, .75, 1])
        group.update(zip(("min", "q1", "median", "q3", "max"), map(float, quantiles)))
        if len(values) > 1 and np.ptp(values) > 0:
            kde = gaussian_kde(values, bw_method="scott")
            grid = np.linspace(values.min(), values.max(), 256)
            density = kde(grid)
            group.update(x=grid.tolist(), density=(density / density.max()).tolist())
        else:
            group["x"] = [float(values[0])]
            group["density"] = [1.0]
    return group


def export_bundle(source):
    source = Path(source)
    payload = source.read_bytes()
    reader = csv.DictReader(payload.decode("utf-8-sig").splitlines())
    required = {"center", "cohort", "modality", "true_label", "rvl_score"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Source CSV is missing required reference fields.")
    rows = []
    for row in reader:
        label, value = int(row["true_label"]), float(row["rvl_score"])
        if label not in (0, 1) or not np.isfinite(value):
            raise ValueError("Source CSV contains an invalid label or score.")
        rows.append({"center": row["center"], "cohort": row["cohort"],
                     "modality": row["modality"], "label": label, "value": value})
    signature = hashlib.sha256(payload).hexdigest()
    references = {}
    for modality in ("cfp", "oct"):
        references[modality] = {}
        source_modality = "fundus" if modality == "cfp" else "oct"
        for cohort, (center, cohort_label) in COHORTS.items():
            selected = [r for r in rows if r["center"] == center and r["cohort"] == cohort
                        and r["modality"] == source_modality]
            if not selected:
                raise ValueError(f"No reference data for {modality}/{cohort}.")
            groups = [summarize_group([r["value"] for r in selected if r["label"] == label], label)
                      for label in (1, 0)]
            references[modality][cohort] = {
                "modality": modality, "cohort": cohort, "cohort_label": cohort_label,
                "source": "Figure 2 · Image-level validation data",
                "source_sha256": signature, "n": len(selected), "groups": groups,
                "range": [min(r["value"] for r in selected), max(r["value"] for r in selected)],
            }
    return {
        "format_version": 1,
        "provenance": {
            "source_file": source.name, "source_sha256": signature,
            "observation_unit": "image",
            "score_definition": "logit_1 - logit_0",
            "probability_definition": "sigmoid(rvl_score)",
            "image_counts": {modality: sum(r["n"] for r in cohorts.values())
                             for modality, cohorts in references.items()},
            "kde": {"method": "scipy.stats.gaussian_kde", "bandwidth": "scott",
                    "grid_points": 256, "domain": "per-class observed minimum to maximum",
                    "normalization": "independent per-class peak = 1"},
            "numpy_version": np.__version__, "scipy_version": scipy.__version__,
        },
        "references": references,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Figure 2 reference score CSV")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/reference_distributions.json")
    args = parser.parse_args()
    bundle = export_bundle(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Exported 12 aggregate reference distributions to {args.output}")


if __name__ == "__main__":
    main()
