import pandas as pd
import requests

def gw21_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 21 'The Ball-Winner' rules to player projections.

    Awards +2 points for every tackle won.
    Fetches historical 'tackles' from the FPL API to estimate a per-90 rate,
    then applies that rate to the projected minutes (xMins).

    Challenge scoring:
    - +2 points per successful tackle

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
            'ID', 'xMins', 'Position', and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to 
            calculate a valid rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Fetch bootstrap static data to get tackle statistics
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    elements_df = pd.DataFrame(data['elements'])
    stats_df = elements_df[['id', 'tackles', 'minutes']].copy()
    stats_df.rename(columns={'id': 'ID'}, inplace=True)

    # Merge stats into projections
    projections = projections.merge(stats_df, on='ID', how='left')

    # Calculate per-90 rates, handling division by zero and minimum minutes threshold
    # If minutes are below threshold, the rate is 0 to avoid small sample size bias
    projections['tackles_per_90'] = projections.apply(
        lambda row: (row['tackles'] / row['minutes'] * 90) if row['minutes'] >= min_minutes else 0, axis=1
    )

    # Estimate expected tackles for the upcoming gameweek based on xMins
    projections['estimated_tackles'] = projections['tackles_per_90'] * (projections['xMins'] / 90)

    # Calculate extra points: +2 points per tackle won
    extra_points = projections['estimated_tackles'] * 2

    projections["Predicted_Points"] += extra_points
    
    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    # Clean up temporary columns
    cols_to_drop = [
        "tackles", "minutes", "tackles_per_90", 
        "estimated_tackles"
    ]
    return projections.drop(columns=cols_to_drop, errors='ignore')
