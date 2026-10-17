"""Projection adjustment for GW7: Away Days."""

from __future__ import annotations

import pandas as pd


def gw7_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Double xPts for players in away matches."""
    adjusted = projections.copy()
    away_player = adjusted["Fixture_Projections"].apply(
        lambda fixtures: any(not fixture["Is_Home"] for fixture in fixtures)
    )
    adjusted.loc[away_player, "Predicted_Points"] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
