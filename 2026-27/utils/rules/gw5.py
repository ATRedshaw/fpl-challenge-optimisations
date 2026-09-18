"""Projection adjustment for GW5: The Shield."""

from __future__ import annotations

import pandas as pd

DEFCON_POINTS = 10


def gw5_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Replace standard defensive-contribution xPts with the GW5 award."""
    adjusted = projections.copy()
    adjusted["Predicted_Points"] = (
        adjusted["Predicted_Points"]
        - adjusted["Defcon_xPts"].fillna(0)
        + adjusted["Defcon"].fillna(0) * DEFCON_POINTS
    ).round(2)
    return adjusted
