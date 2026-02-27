import pandas as pd


def gw28_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 28 rules to player projections.

    Rules:
        - Double points for Wolverhampton Wanderers and Aston Villa players.
        - Up to 3 players per club (enforced by the optimiser via max_per_team constraint).
        - Unlimited budget (no budget constraint applied).

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Target teams for the 'Midlands Clash' challenge multiplier
    midlands_teams = ["Wolves", "Aston Villa"]
    projections.loc[projections["Team"].isin(midlands_teams), "Predicted_Points"] *= 2

    return projections
