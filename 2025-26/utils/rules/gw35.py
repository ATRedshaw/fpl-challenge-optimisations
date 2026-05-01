import pandas as pd
import requests


def gw35_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 35 'The Golden Boot' rules to player projections.

    All goals are worth 10 points regardless of position. In standard FPL,
    goals score 6 pts (GK/DEF), 5 pts (MID), or 4 pts (FWD), so the extra
    points awarded per goal under this challenge are:

    - Goalkeeper / Defender: +4 per goal
    - Midfielder:            +5 per goal
    - Forward:               +6 per goal

    Season-to-date goals and minutes are fetched from the FPL bootstrap API to
    derive a goals-per-90 rate, which is then scaled by projected minutes (xMins).
    Players below min_minutes are assigned a rate of 0 to avoid small-sample noise.

    Args:
        projections (pd.DataFrame): Player projections containing 'ID', 'xMins',
            'Position', and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to use a
            player's goals-per-90 rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    # Extra points per goal by position (challenge value 10 minus standard FPL value)
    EXTRA_GOAL_POINTS = {
        "Goalkeeper": 4,
        "Defender": 4,
        "Midfielder": 5,
        "Forward": 6,
    }

    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    elements_df = pd.DataFrame(data["elements"])
    stats_df = elements_df[["id", "goals_scored", "minutes"]].copy()
    stats_df.rename(columns={"id": "ID"}, inplace=True)

    projections = projections.merge(stats_df, on="ID", how="left")

    # Goals per 90 — zero out players below the minimum minutes threshold
    projections["goals_per_90"] = projections.apply(
        lambda row: (row["goals_scored"] / row["minutes"] * 90)
        if row["minutes"] >= min_minutes
        else 0,
        axis=1,
    )

    # Estimated goals for the gameweek based on projected minutes
    projections["estimated_goals"] = projections["goals_per_90"] * (projections["xMins"] / 90)

    # Extra points per goal varies by position
    projections["extra_pts_per_goal"] = projections["Position"].map(EXTRA_GOAL_POINTS).fillna(0)

    projections["Predicted_Points"] += projections["estimated_goals"] * projections["extra_pts_per_goal"]
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    return projections.drop(
        columns=["goals_scored", "minutes", "goals_per_90", "estimated_goals", "extra_pts_per_goal"],
        errors="ignore",
    )
