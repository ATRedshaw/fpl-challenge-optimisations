import requests
import pandas as pd

def gw18_rules(
    projections: pd.DataFrame, 
    api_url: str = "https://fplchallenge.premierleague.com/api/bootstrap-static/",
    min_minutes: int = 300
) -> pd.DataFrame:
    """
    Apply Gameweek 18 'Gift Wrapped' rules to player projections.

    Calculates expected points from Big Chances Created by determining the 
    historical rate per minute for players meeting a minimum minutes threshold.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.
        api_url (str, optional): API endpoint for player data.
            Defaults to Premier League bootstrap-static.
        min_minutes (int, optional): Minimum historical minutes required to 
            calculate a valid rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    response = requests.get(api_url)
    response.raise_for_status()
    elements = response.json()["elements"]

    stats_df = pd.DataFrame(elements)[["id", "minutes", "big_chances_created"]]

    # Initialise rate to zero to handle players below the minutes threshold
    stats_df["bc_rate"] = 0.0
    
    # Calculate rate only for players with sufficient data to avoid sample size bias
    eligible_mask = stats_df["minutes"] >= min_minutes
    stats_df.loc[eligible_mask, "bc_rate"] = (
        stats_df.loc[eligible_mask, "big_chances_created"] / stats_df.loc[eligible_mask, "minutes"]
    )

    rate_mapping = stats_df.set_index("id")["bc_rate"]
    projections["temp_bc_rate"] = projections["ID"].map(rate_mapping).fillna(0).round(2)

    # Apply +6 points for every expected Big Chance Created
    # Expected Big Chances = (Historical Rate) * (Projected Minutes)
    projections["Predicted_Points"] += (projections["temp_bc_rate"] * projections["xMins"] * 6)

    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    return projections.drop(columns=["temp_bc_rate"])
