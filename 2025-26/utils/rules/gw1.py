import requests
import pandas as pd

def gw1_rules(projections: pd.DataFrame, api_url: str = "https://fplchallenge.premierleague.com/api/bootstrap-static/") -> pd.DataFrame:
    """
    Apply Gameweek 1 rules to player projections.

    Rules:
        - If a player's team_join_date is after 25th May 2025,
          double their Predicted_Points.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.
        api_url (str, optional): API endpoint for player data.
            Defaults to Premier League bootstrap-static.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    response = requests.get(api_url)
    data = response.json()["elements"]

    # Map element id to team_join_date
    id_to_join_date = {element["id"]: element["team_join_date"] for element in data}
    projections["team_join_date"] = projections["ID"].map(id_to_join_date)

    # Double points for players who joined after 25th May 2025
    projections.loc[projections["team_join_date"] > "2025-05-25", "Predicted_Points"] *= 2

    # Remove temporary column
    projections = projections.drop("team_join_date", axis=1)

    return projections
