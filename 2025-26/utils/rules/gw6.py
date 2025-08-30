import requests
import pandas as pd

def gw6_rules(projections: pd.DataFrame, api_url: str = "https://fplchallenge.premierleague.com/api/bootstrap-static/") -> pd.DataFrame:
    """
    Apply Gameweek 6 rules to player projections.

    Rules:
        - If a player's age is 23 or under, then double their Predicted_Points.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.
        api_url (str, optional): API endpoint for player data.
            Defaults to Premier League bootstrap-static.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    response = requests.get(api_url)
    data = response.json()["elements"]

    # Map element id to birth_date
    id_to_birth_date = {element["id"]: element["birth_date"] for element in data}

    # Attach birth_date to projections
    projections["player_birth_date"] = projections["ID"].map(id_to_birth_date)
    projections["player_birth_date"] = pd.to_datetime(projections["player_birth_date"], errors="coerce")

    ref_date = pd.to_datetime("2025-09-27")

    # Calculate exact age
    def calculate_age(born, ref):
        if pd.isna(born):
            return None
        return ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))

    projections["Age"] = projections["player_birth_date"].apply(lambda d: calculate_age(d, ref_date))

    # Double points for players aged 23 or under
    projections.loc[projections["Age"] <= 23, "Predicted_Points"] *= 2

    # Remove helper columns
    projections = projections.drop(columns=["player_birth_date", "Age"])

    return projections

