import pandas as pd

def gw26_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 26 rules to player projections.

    Rules:
        - Double Points for Chelsea and Leeds United players.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    rivalry_teams = ["Chelsea", "Leeds"]
    projections.loc[projections["Team"].isin(rivalry_teams), "Predicted_Points"] *= 2

    return projections
