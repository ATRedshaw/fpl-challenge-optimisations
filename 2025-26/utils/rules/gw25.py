import pandas as pd

def gw25_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 25 rules to player projections.

    Rules:
        - Double Points for Brighton and Crystal Palace players.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    rivalry_teams = ["Brighton", "Crystal Palace"]
    projections.loc[projections["Team"].isin(rivalry_teams), "Predicted_Points"] *= 2

    return projections
