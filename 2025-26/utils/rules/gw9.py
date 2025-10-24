import requests
import pandas as pd

def gw9_rules(projections: pd.DataFrame, api_url: str = "https://fplchallenge.premierleague.com/api/bootstrap-static/") -> pd.DataFrame:
    """
    Apply Gameweek 9 rules to player projections.

    Rules:
        - Players who have been at their club for 5+ seasons earn double points.
        - One Player per Club.
        - Unlimited Budget.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.
        api_url (str, optional): API endpoint for player data.
            Defaults to Premier League bootstrap-static.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    response = requests.get(api_url)
    data = response.json()["elements"]

    # Create a mapping of player IDs to their join date and team ID
    id_to_join_date = {p["id"]: p["team_join_date"] for p in data}
    id_to_team = {p["id"]: p["team"] for p in data}

    projections["team_join_date"] = projections["ID"].map(id_to_join_date)
    projections["TeamID"] = projections["ID"].map(id_to_team)

    # Convert join date to datetime objects
    projections["team_join_date"] = pd.to_datetime(projections["team_join_date"])

    # 5+ seasons means they must have joined before the 2020-21 season.
    # Cutoff date is roughly start of that season.
    cutoff_date = pd.to_datetime("2020-08-01")

    # Filter for players who meet the 5+ season criteria
    long_serving_players = projections[projections["team_join_date"] <= cutoff_date].copy()

    # Find the longest serving player for each team
    longest_serving_per_team = long_serving_players.loc[
        long_serving_players.groupby("TeamID")["team_join_date"].idxmin()
    ]

    # Get the IDs of these players
    player_ids_to_double = longest_serving_per_team["ID"].tolist()

    # Double their points
    projections.loc[projections["ID"].isin(player_ids_to_double), "Predicted_Points"] *= 2

    # Clean up temporary columns
    projections = projections.drop(columns=["team_join_date", "TeamID"])

    return projections
