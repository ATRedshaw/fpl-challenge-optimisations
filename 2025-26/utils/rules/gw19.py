import pandas as pd
import requests

def gw19_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 19 'Double Celebration' rules to player projections.

    Adjusts predicted points by doubling the value of projected goals and assists.
    Since xG and xA are unavailable in the input, this function fetches historical
    'goals_scored' and 'assists' from the FPL API to estimate a per-90 rate,
    then applies that rate to the projected minutes (xMins).

    Standard scoring:
    - Forward Goal: 4 pts -> Extra 4 pts
    - Midfielder Goal: 5 pts -> Extra 5 pts
    - Defender/GK Goal: 6 pts -> Extra 6 pts
    - Assist (Any): 3 pts -> Extra 3 pts

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
            'ID', 'xMins', 'Position', and 'Predicted_Points'.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Fetch bootstrap static data to get goals and assists
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    elements_df = pd.DataFrame(data['elements'])
    stats_df = elements_df[['id', 'goals_scored', 'assists', 'minutes']].copy()
    stats_df.rename(columns={'id': 'ID'}, inplace=True)

    # Merge stats into projections
    projections = projections.merge(stats_df, on='ID', how='left')

    # Calculate per-90 rates, handling division by zero
    # If minutes are 0, the rate is 0
    projections['goals_per_90'] = projections.apply(
        lambda row: (row['goals_scored'] / row['minutes'] * 90) if row['minutes'] > 0 else 0, axis=1
    )
    projections['assists_per_90'] = projections.apply(
        lambda row: (row['assists'] / row['minutes'] * 90) if row['minutes'] > 0 else 0, axis=1
    )

    # Estimate expected goals and assists for the upcoming gameweek based on xMins
    projections['estimated_goals'] = projections['goals_per_90'] * (projections['xMins'] / 90)
    projections['estimated_assists'] = projections['assists_per_90'] * (projections['xMins'] / 90)

    # Define goal points by position
    goal_points = {
        "Goalkeeper": 6,
        "Defender": 6,
        "Midfielder": 5,
        "Forward": 4
    }
    
    # Map position to goal points value
    projections["goal_value"] = projections["Position"].map(goal_points).fillna(4)

    # Calculate extra points: (Estimated Goals * Goal Points) + (Estimated Assists * Assist Points)
    # Assist points are consistently 3 across all positions
    extra_points = (projections["estimated_goals"] * projections["goal_value"]) + (projections["estimated_assists"] * 3)

    projections["Predicted_Points"] += extra_points
    
    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    # Clean up temporary columns
    cols_to_drop = [
        "goals_scored", "assists", "minutes", "goals_per_90", 
        "assists_per_90", "estimated_goals", "estimated_assists", "goal_value"
    ]
    return projections.drop(columns=cols_to_drop, errors='ignore')
