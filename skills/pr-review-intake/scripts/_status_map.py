"""Provider status normalization.

Pure functions, importable. See references/normalized-schema.md §"Status
normalization" for the table this implements.
"""

_AZDO_MAP = {
    "active":   "active",
    "pending":  "pending",
    "fixed":    "resolved",
    "closed":   "resolved",
    "byDesign": "resolved",
    "wontFix":  "resolved",
    "unknown":  "active",
}


def normalize_azdo(raw: str) -> str:
    """Map an AzDO thread status to {active, pending, resolved}.

    Unknown values are conservatively treated as 'active' so an addressable
    thread is never silently dropped from intake.
    """
    return _AZDO_MAP.get(raw, "active")


def normalize_github(is_resolved: bool) -> str:
    """Map GitHub's `isResolved` boolean to normalized status.

    GitHub has no `pending` equivalent — see references/normalized-schema.md.
    """
    return "resolved" if is_resolved else "active"
