"""Projection adjustments for GW4: Derby Day."""

from __future__ import annotations

import pandas as pd

MANCHESTER_TEAMS = frozenset({"Man City", "Man Utd"})


def gw4_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Double xPts for Manchester City and Manchester United players."""
    adjusted = projections.copy()
    manchester_player = adjusted["Team"].isin(MANCHESTER_TEAMS)
    adjusted.loc[manchester_player, "Predicted_Points"] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
