import pandas as pd

def gw17_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 17 "Home for the Holidays" rule: double predicted points for players
    with home fixtures.

    Detection:
        - Home fixtures identified by '(H)' in the 'Opponent' column (e.g. 'Everton (H)').

    Parameters:
        projections (pd.DataFrame): DataFrame containing at minimum 'Opponent' and
            'Predicted_Points' columns.

    Returns:
        pd.DataFrame: Copy of input with 'Predicted_Points' doubled for home fixtures.
    """
    required_cols = {"Opponent", "Predicted_Points"}
    if not required_cols.issubset(projections.columns):
        missing = required_cols - set(projections.columns)
        raise ValueError(f"Missing required columns: {missing}")

    # Avoid mutating original DataFrame to preserve source projections for auditing.
    proj = projections.copy()

    # Ensure numeric predictions for safe arithmetic; preserve NaN where conversion fails.
    proj["Predicted_Points"] = pd.to_numeric(proj["Predicted_Points"], errors="coerce")

    # Robust detection of home fixtures; nai values treated as non-home.
    is_home = proj["Opponent"].astype(str).str.contains(r"\(H\)", regex=True, na=False)

    # Double points for home fixtures per challenge rules.
    proj.loc[is_home, "Predicted_Points"] *= 2

    return proj
