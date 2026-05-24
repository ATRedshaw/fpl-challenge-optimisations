import pandas as pd


def gw38_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 38 'Final Victory' rules to player projections.

    Every player on a winning team earns +8 points. The expected bonus for
    each player is their team's win probability multiplied by 8.

    Win probabilities are taken from Leg 1 match odds for GW38 fixtures
    (Sun, 24 May 2026).

    Args:
        projections (pd.DataFrame): Player projections containing 'Team' and
            'Predicted_Points' columns.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    WIN_BONUS = 8

    # Win probabilities per team (home win % / away win % from match odds via ELO model)
    win_probabilities = {
        "Man City":        0.51,
        "Aston Villa":     0.24,
        "Crystal Palace":  0.15,
        "Arsenal":         0.61,
        "Brighton":        0.37,
        "Man Utd":         0.35,
        "Liverpool":       0.53,
        "Brentford":       0.23,
        "Nott'm Forest":   0.35,
        "Bournemouth":     0.35,
        "Fulham":          0.36,
        "Newcastle":       0.35,
        "Spurs":           0.37,
        "Everton":         0.34,
        "West Ham":        0.35,
        "Leeds":           0.37,
        "Sunderland":      0.28,
        "Chelsea":         0.44,
        "Burnley":         0.39,
        "Wolves":          0.31,
    }

    projections["Predicted_Points"] += (
        projections["Team"].map(win_probabilities).fillna(0) * WIN_BONUS
    )
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    return projections
