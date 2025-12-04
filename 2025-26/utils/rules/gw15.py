import pandas as pd

def gw15_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 15 "Big Save" rules to player projections.

    Rules:
        - Double Points for Defenders priced at 5m or under.

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
                                    'Position', 'Cost', and 'Predicted_Points' columns.

    Returns:
        pd.DataFrame: Updated DataFrame with modified 'Predicted_Points'.
    """

    # Define the criteria for the bonus
    is_defender_or_goalkeeper = (projections["Position"] == "Defender") | (projections["Position"] == "Goalkeeper")
    is_cost_eligible = projections["Cost"] <= 5.0

    # Combine criteria to find the players who should have their points doubled
    players_to_double = is_defender_or_goalkeeper & is_cost_eligible

    # Apply the double points multiplier
    projections.loc[players_to_double, "Predicted_Points"] *= 2

    return projections