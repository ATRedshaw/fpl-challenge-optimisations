import pandas as pd

def gw7_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 7 rules to player projections based on clean sheet probability.

    Rules:
        - Add (Clean Sheet Probability * 4) to xpts for goalkeepers and defenders.
        - Add (Clean Sheet Probability * 1) to xpts for midfielders.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified xpts.
    """
    data = {
        "Team": [
            "Arsenal", "Aston Villa", "Man Utd", "Newcastle", "Bournemouth",
            "Man City", "Everton", "Brighton", "Crystal Palace", "Spurs",
            "Leeds", "Liverpool", "Wolves", "Fulham", "Chelsea",
            "Nott'm Forest", "Burnley", "Brentford", "Sunderland", "West Ham"
        ],
        "Clean Sheet Probability": [
            57, 44, 42, 40, 36,
            36, 35, 33, 31, 29,
            27, 24, 22, 21, 20,
            18, 17, 14, 13, 9
        ]
    }
    cs_prob_df = pd.DataFrame(data)

    # Merge projections with clean sheet probabilities
    projections = projections.merge(cs_prob_df, on="Team", how="left")

    # Apply rules based on position
    # Assuming 'Position' column exists in projections DataFrame
    # Assuming 'Predicted_Points' column exists in projections DataFrame
    projections.loc[projections["Position"].isin(["Goalkeeper", "Defender"]), "Predicted_Points"] += (
        (projections["Clean Sheet Probability"]/100) * 4
    )
    projections.loc[projections["Position"] == "Midfielder", "Predicted_Points"] += (
        (projections["Clean Sheet Probability"]/100) * 1
    )

    # Remove helper column
    projections = projections.drop(columns=["Clean Sheet Probability"])

    # Round all points to 1 decimal place
    projections["Predicted_Points"] = projections["Predicted_Points"].round(1)

    return projections