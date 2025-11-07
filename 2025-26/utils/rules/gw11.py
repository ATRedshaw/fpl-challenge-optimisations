import requests
import pandas as pd

def gw11_rules(projections: pd.DataFrame, api_url: str = "https://fplchallenge.premierleague.com/api/bootstrap-static/") -> pd.DataFrame:
    """
    Apply Gameweek 11 rules to player projections.

    Rules:
        - All Bonus Points awarded are doubled.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.
        api_url (str, optional): API endpoint for player data.
            Defaults to Premier League bootstrap-static.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    data = requests.get(api_url).json()
    player_data = data["elements"]

    # Create dictionaries for minutes and bonus points
    minutes_dict = {str(player['id']): player['minutes'] for player in player_data}
    bonus_dict = {str(player['id']): player['bonus'] for player in player_data}
    
    # Add new columns by mapping the ID to the corresponding values
    projections['minutes'] = projections['ID'].astype(str).map(minutes_dict)
    projections['bonus'] = projections['ID'].astype(str).map(bonus_dict)
    
    def calculate_new_xpts(row):
        """
        Calculates the new Expected Points based on minutes played and bonus points.

        Args:
            row (pd.Series): A row from the DataFrame.

        Returns:
            float: The new Expected Points.
        """
        full_90s = 0 
        bonus_per_game = 0
        if row['minutes'] > 0:
            full_90s = row['minutes'] / 90
            bonus_per_game = row['bonus'] / full_90s
        
        # Predicted points already accounts for bonus, so just add it to simulate the double
        return round(row['Predicted_Points'] + bonus_per_game, 2)
    
    projections['Predicted_Points'] = projections.apply(calculate_new_xpts, axis=1)

    return projections
