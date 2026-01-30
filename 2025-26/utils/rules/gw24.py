import pandas as pd
import requests

def gw24_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 24 'The Aerial Threat' rules to player projections.

    Gameweek 24 Challenge: The Aerial Threat
    +4 Points for every Headed goal attempt (on and off target).

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
            'ID', 'xMins', 'Position', and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to 
            calculate a valid rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Fetch bootstrap static data to get total_headed_attempts statistics
    url = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    elements_df = pd.DataFrame(data['elements'])
    stats_df = elements_df[['id', 'total_headed_attempts', 'minutes']].copy()
    stats_df.rename(columns={'id': 'ID'}, inplace=True)

    # Merge stats into projections
    projections = projections.merge(stats_df, on='ID', how='left')

    # Calculate per-90 rates, handling division by zero and minimum minutes threshold
    # If minutes are below threshold, the rate is 0 to avoid small sample size bias
    projections['headed_attempts_per_90'] = projections.apply(
        lambda row: (row['total_headed_attempts'] / row['minutes'] * 90) if row['minutes'] >= min_minutes else 0, axis=1
    )

    # Estimate expected headed attempts for the upcoming gameweek based on xMins
    projections['estimated_headed_attempts'] = projections['headed_attempts_per_90'] * (projections['xMins'] / 90)

    # Calculate extra points: +4 points per headed attempt
    extra_points = projections['estimated_headed_attempts'] * 4

    projections["Predicted_Points"] += extra_points
    
    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    # Clean up temporary columns
    cols_to_drop = [
        "total_headed_attempts", "minutes", "headed_attempts_per_90", 
        "estimated_headed_attempts"
    ]
    return projections.drop(columns=cols_to_drop, errors='ignore')
