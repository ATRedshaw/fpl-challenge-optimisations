import pandas as pd

def gw16_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 16 "Striker Deal" rules to player projections.

    Rules:
        - Double points for Forwards priced at 7.5m or under at the deadline.
          Cost column is hardcoded to 'Cost' (deadline price, e.g. Sat 13 Dec 15:00).

    Parameters:
        projections (pd.DataFrame): DataFrame containing 'Position', 'Cost' and 'Predicted_Points' columns.

    Returns:
        pd.DataFrame: New DataFrame with updated 'Predicted_Points'.
    """
    required_cols = {"Position", "Cost", "Predicted_Points"}
    if not required_cols.issubset(projections.columns):
        missing = required_cols - set(projections.columns)
        raise ValueError(f"Missing required columns: {missing}")

    # Avoid in-place modification to preserve original projections.
    proj = projections.copy()

    # Hardcoded cost column 'Cost' to reflect deadline prices.
    is_forward = proj["Position"] == "Forward"
    is_cost_eligible = proj["Cost"] <= 7.5
    eligible = is_forward & is_cost_eligible

    proj.loc[eligible, "Predicted_Points"] *= 2

    return proj
