"""Projection adjustment for GW3: All Out Attack."""

from __future__ import annotations

import pandas as pd

GOAL_POINTS = {
    "Goalkeeper": 10,
    "Defender": 6,
    "Midfielder": 5,
    "Forward": 4,
}
ASSIST_POINTS = 3


def gw3_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Double the projected points for goals and assists in GW3."""
    adjusted = projections.copy()
    goal_points = adjusted["Position"].map(GOAL_POINTS).fillna(4)
    adjusted["Predicted_Points"] = (
        adjusted["Predicted_Points"]
        + adjusted["Projected_Goals"].fillna(0) * goal_points
        + adjusted["Projected_Assists"].fillna(0) * ASSIST_POINTS
    ).round(2)
    return adjusted
