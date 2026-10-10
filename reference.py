"""Frozen aggregate reference distributions; no individual image records required."""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


SOURCE = Path(__file__).resolve().parent / "data/reference_distributions.json"
COHORTS = {
    "internal_test": ("chongqing", "UC-FAH-CQMU"),
    "prospective": ("chongqing", "UC-FAH-CQMU · Temporal validation"),
    "shanghai": ("shanghai", "EENT-FDU · External validation"),
    "zhengzhou": ("zhengzhou", "FAH-ZZU · External validation"),
    "jilin": ("jilin", "OC-JLU2H · External validation"),
    "proton": ("proton", "PROTON · External validation"),
}


@lru_cache(maxsize=2)
def _load_bundle(path, size, modified_ns):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    if bundle["format_version"] != 1:
        raise ValueError("Unsupported bundled reference data format.")
    return bundle["references"]


def get_reference(modality="cfp", cohort="internal_test"):
    if modality not in ("cfp", "oct") or cohort not in COHORTS:
        raise ValueError("Select a valid image modality and reference cohort.")
    stat = SOURCE.stat()
    references = _load_bundle(str(SOURCE), stat.st_size, stat.st_mtime_ns)
    # Callers may annotate their response without changing the cached reference.
    return deepcopy(references[modality][cohort])
