import pandas as pd
# No API calls needed as the necessary data (Position, Cost) is in the projections DataFrame.

def gw14_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 14 "Value Creators" rules to player projections.

    Rules:
        - Double Points for Midfielders priced at 7m or under.

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
                                    'Position', 'Cost', and 'Predicted_Points' columns.

    Returns:
        pd.DataFrame: Updated DataFrame with modified 'Predicted_Points'.
    """

    # Define the criteria for the bonus
    is_midfielder = projections["Position"] == "Midfielder"
    is_cost_eligible = projections["Cost"] <= 7.0

    # Combine criteria to find the players who should have their points doubled
    players_to_double = is_midfielder & is_cost_eligible

    # Apply the double points multiplier
    projections.loc[players_to_double, "Predicted_Points"] *= 2

    return projections