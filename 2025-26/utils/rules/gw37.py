import pandas as pd
import requests


def gw37_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 37 'The Golden Glove' rules to player projections.

    Two changes apply, both exclusively to goalkeepers:

    1. **Saves bonus:** 4 points per 3 saves instead of the standard 1, giving
       +3 extra points per 3 saves (i.e. +1 extra point per save).
    2. **Clean sheet bonus:** Goalkeeper clean sheets are worth 10 points instead
       of the standard 6, giving +4 extra points per clean sheet.

    Season-to-date saves, clean sheets, and minutes are fetched from the FPL
    bootstrap API. Saves-per-90 and clean-sheets-per-90 rates are derived and
    scaled by projected minutes (xMins). Goalkeepers below min_minutes are
    assigned a rate of 0 to avoid small-sample noise.

    Args:
        projections (pd.DataFrame): Player projections containing 'ID', 'xMins',
            'Position', and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to use a
            goalkeeper's saves-per-90 rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    # Standard FPL: 1 pt per 3 saves. Challenge: 4 pts per 3 saves. Extra: +3 per 3 saves.
    EXTRA_POINTS_PER_SAVE = 1  # 3 extra pts / 3 saves

    # Standard GK clean sheet: 6 pts. Challenge: 10 pts. Extra: +4.
    EXTRA_CS_POINTS = 4

    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    elements_df = pd.DataFrame(data["elements"])
    stats_df = elements_df[["id", "saves", "clean_sheets", "minutes"]].copy()
    stats_df.rename(columns={"id": "ID"}, inplace=True)

    projections = projections.merge(stats_df, on="ID", how="left")

    is_gk = projections["Position"] == "Goalkeeper"

    # Saves per 90 — only for goalkeepers above the minutes threshold
    projections["saves_per_90"] = 0.0
    projections.loc[is_gk, "saves_per_90"] = projections[is_gk].apply(
        lambda row: (row["saves"] / row["minutes"] * 90)
        if row["minutes"] >= min_minutes
        else 0.0,
        axis=1,
    )

    # Clean sheets per 90 — only for goalkeepers above the minutes threshold
    projections["cs_per_90"] = 0.0
    projections.loc[is_gk, "cs_per_90"] = projections[is_gk].apply(
        lambda row: (row["clean_sheets"] / row["minutes"] * 90)
        if row["minutes"] >= min_minutes
        else 0.0,
        axis=1,
    )

    # Estimated saves and clean sheets for the gameweek based on projected minutes
    projections["estimated_saves"] = projections["saves_per_90"] * (projections["xMins"] / 90)
    projections["estimated_cs"] = projections["cs_per_90"] * (projections["xMins"] / 90)

    # Saves bonus: +1 extra point per estimated save (goalkeepers only)
    projections.loc[is_gk, "Predicted_Points"] += (
        projections.loc[is_gk, "estimated_saves"] * EXTRA_POINTS_PER_SAVE
    )

    # Clean sheet bonus: +4 extra points per expected clean sheet (goalkeepers only)
    projections.loc[is_gk, "Predicted_Points"] += (
        projections.loc[is_gk, "estimated_cs"] * EXTRA_CS_POINTS
    )

    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    return projections.drop(
        columns=["saves", "clean_sheets", "minutes", "saves_per_90", "cs_per_90", "estimated_saves", "estimated_cs"],
        errors="ignore",
    )
