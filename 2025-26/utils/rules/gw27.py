import pandas as pd

def gw27_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 27 rules to player projections.

    Rules:
        - Double points for Nottingham Forest and Liverpool players.
        - Note: Constraints for budget and max players per club must be handled by the optimiser.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Target teams for the 'Old Foes' challenge multiplier
    rivalry_teams = ["Nott'm Forest", "Liverpool"]
    projections.loc[projections["Team"].isin(rivalry_teams), "Predicted_Points"] *= 2

    return projections
