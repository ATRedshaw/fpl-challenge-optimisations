import requests

def gw1_rules(projections, api_url='https://fplchallenge.premierleague.com/api/bootstrap-static/'):
    response = requests.get(api_url)
    data = response.json()['elements']

    # Create a dictionary: id -> team_join_date
    id_to_join_date = {element['id']: element['team_join_date'] for element in data}

    # Map the dictionary to the 'ID' column
    projections['team_join_date'] = projections['ID'].map(id_to_join_date)

    # If player's team_join_date is more recent than 25th May (i.e. > then), then double their Predicted_Points
    projections.loc[projections['team_join_date'] > '2025-05-25', 'Predicted_Points'] *= 2

    # Drop the team_join_date column
    projections = projections.drop('team_join_date', axis=1)

    return projections