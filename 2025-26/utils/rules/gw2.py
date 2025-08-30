import pandas as pd

def gw2_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 2 rules to player projections.

    Rules:
        - If a player belongs to a promoted team, double their Predicted_Points.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    promoted_teams = ["Sunderland", "Leeds", "Burnley"]
    projections.loc[projections["Team"].isin(promoted_teams), "Predicted_Points"] *= 2
    return projections
