import pandas as pd

def gw4_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 4 rules to player projections.

    Rules:
        - If a player is playing in the Manchester derby, double their Predicted_Points.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    rivalry_teams = ["Man Utd", "Man City"]
    projections.loc[projections["Team"].isin(rivalry_teams), "Predicted_Points"] *= 2

    return projections
