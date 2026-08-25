"""Projection adjustments for GW2: Welcome Back."""

from __future__ import annotations

import pandas as pd


PROMOTED_TEAMS = frozenset({"Coventry City", "Hull City", "Ipswich Town"})


def gw2_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Double xPts for players from one of the promoted 2026/27 clubs."""
    adjusted = projections.copy()
    promoted = adjusted["Team"].isin(PROMOTED_TEAMS)
    adjusted.loc[promoted, "Predicted_Points"] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
