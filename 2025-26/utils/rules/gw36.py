import pandas as pd
import requests


def gw36_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 36 'The Playmaker' rules to player projections.

    All assists are worth 10 points. Standard FPL awards 3 points per assist
    regardless of position, so the extra points per assist under this challenge
    is +7 for all players.

    Season-to-date assists and minutes are fetched from the FPL bootstrap API to
    derive an assists-per-90 rate, which is then scaled by projected minutes (xMins).
    Players below min_minutes are assigned a rate of 0 to avoid small-sample noise.

    Args:
        projections (pd.DataFrame): Player projections containing 'ID', 'xMins',
            and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to use a
            player's assists-per-90 rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    # All positions receive the same bonus: challenge value 10 minus standard FPL value 3
    EXTRA_ASSIST_POINTS = 7

    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    elements_df = pd.DataFrame(data["elements"])
    stats_df = elements_df[["id", "assists", "minutes"]].copy()
    stats_df.rename(columns={"id": "ID"}, inplace=True)

    projections = projections.merge(stats_df, on="ID", how="left")

    # Assists per 90 — zero out players below the minimum minutes threshold
    projections["assists_per_90"] = projections.apply(
        lambda row: (row["assists"] / row["minutes"] * 90)
        if row["minutes"] >= min_minutes
        else 0,
        axis=1,
    )

    # Estimated assists for the gameweek based on projected minutes
    projections["estimated_assists"] = projections["assists_per_90"] * (projections["xMins"] / 90)

    projections["Predicted_Points"] += projections["estimated_assists"] * EXTRA_ASSIST_POINTS
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    return projections.drop(
        columns=["assists", "minutes", "assists_per_90", "estimated_assists"],
        errors="ignore",
    )
