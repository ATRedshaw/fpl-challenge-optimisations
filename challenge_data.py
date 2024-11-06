import requests
import pandas as pd

def get_bootstrap_static_data():
    """
    Fetches the bootstrap static data from the FPL Challenge API.

    Returns:
        dict or None: The bootstrap static data if successful, None if there was an error
    """
    url = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
    
    try:
        response = requests.get(url)
        # Raise an exception for bad status codes
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def get_current_gameweek(data):
    """
    Get the current gameweek from the bootstrap static data.
    
    Returns:
        int or None: The current gameweek number if found, None if there was an error
                    or no current gameweek exists.
    """
    
    if not data:
        return None
        
    # Find the current gameweek from the events array
    for event in data['events']:
        if event['is_current']:
            return event['id']
            
    # Return None if no current gameweek is found
    return None

def get_gameweek_data(gameweek, bootstrap_data):
    """
    Get the data for a specific gameweek from the FPL Challenge API and format it similar to projections.py
    
    Args:
        gameweek (int): The gameweek number to get data for
        bootstrap_data (dict): The bootstrap static data containing team info
        
    Returns:
        pandas.DataFrame: DataFrame containing player data with columns:
            - ID: Player ID
            - Name: Player name 
            - Team: Team name
            - Position: Player position
            - Cost: Player cost
            - Points: Actual points scored in the gameweek
    """
    url = f'https://fplchallenge.premierleague.com/api/bootstrap-event/{gameweek}/'
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        event_data = response.json()
        
        players = []
        position_map = {
            1: 'Goalkeeper',
            2: 'Defender', 
            3: 'Midfielder',
            4: 'Forward'
        }
        
        # Create team lookup dictionary from bootstrap data
        team_lookup = {team['id']: team['name'] for team in bootstrap_data['teams']}
        
        for player in event_data['elements']:
            player_data = {
                'ID': player['id'],
                'Name': f"{player['first_name']} {player['second_name']}",
                'Team': team_lookup[player['team']],
                'Position': position_map[player['element_type']],
                'Cost': player['now_cost'] / 10,
                'Points': player['event_points']
            }
            players.append(player_data)
            
        df = pd.DataFrame(players)
        df = df.sort_values(by='ID')
        df = df.reset_index(drop=True)
        return df
        
    except requests.RequestException as e:
        print(f"Error fetching gameweek data: {e}")
        return None

def update_with_gameweek_cost(df, season, gameweek):
    """
    Updates player costs in the DataFrame using historical cost data from a GitHub repository.
    
    Args:
        df (pandas.DataFrame): DataFrame containing player data
        season (str): Season identifier (e.g. '2024-25')
        gameweek (int): Gameweek number to get costs for
        
    Returns:
        pandas.DataFrame: DataFrame with updated player costs where available
    """
    # Try to get costs for specified gameweek
    cost_dict = {}
    github_url = f'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/gw{gameweek}.csv'
    
    try:
        # Add error handling and response checking
        response = requests.get(github_url)
        response.raise_for_status()
        
        # Read CSV from content rather than URL directly
        gw_costs = pd.read_csv(pd.io.common.StringIO(response.content.decode('utf-8')))
        
        if 'element' in gw_costs.columns and 'value' in gw_costs.columns:
            gw_costs = gw_costs[['element', 'value']]
            cost_dict = dict(zip(gw_costs['element'], gw_costs['value']))
        else:
            print("Required columns not found in CSV")
            raise ValueError("Missing required columns")
            
    except Exception as e:
        print(f"Error loading gameweek {gameweek}: {str(e)}")
        # If specified gameweek not found, try previous gameweeks
        for gw in range(gameweek-1, 0, -1):
            try:
                github_url = f'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/gw{gw}.csv'
                response = requests.get(github_url)
                response.raise_for_status()
                gw_costs = pd.read_csv(pd.io.common.StringIO(response.content.decode('utf-8')))
                if 'element' in gw_costs.columns and 'value' in gw_costs.columns:
                    gw_costs = gw_costs[['element', 'value']]
                    cost_dict = dict(zip(gw_costs['element'], gw_costs['value']))
                    break
            except Exception as e:
                print(f"Error loading gameweek {gw}: {str(e)}")
                cost_dict = {}
                continue

    # Update costs where available
    for idx, row in df.iterrows():
        player_id = row['ID']
        if player_id in cost_dict:
            df.at[idx, 'Cost'] = cost_dict[player_id] / 10

    return df
    
if __name__ == "__main__":
    bootstrap_data = get_bootstrap_static_data()
    current_gameweek = get_current_gameweek(bootstrap_data)
    print(f"Current Gameweek: {current_gameweek}")
    gameweek_1_data = update_with_gameweek_cost(get_gameweek_data(1, bootstrap_data), '2024-25', 1)
    gameweek_2_data = update_with_gameweek_cost(get_gameweek_data(2, bootstrap_data), '2024-25', 2)
    print(gameweek_1_data)
    print(gameweek_2_data)