import pandas as pd
import requests

def gw22_rules(projections: pd.DataFrame, min_minutes: int = 300) -> pd.DataFrame:
    """
    Apply Gameweek 22 'The Playmaker' rules to player projections.

    Awards +1 point for every chance created.
    Fetches historical 'big_chances_created' from the FPL API to estimate a per-90 rate,
    then applies that rate to the projected minutes (xMins).

    Challenge scoring:
    - +1 point per chance created

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
            'ID', 'xMins', 'Position', and 'Predicted_Points'.
        min_minutes (int, optional): Minimum historical minutes required to 
            calculate a valid rate. Defaults to 300.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Fetch bootstrap static data to get chance creation statistics
    url = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    elements_df = pd.DataFrame(data['elements'])
    stats_df = elements_df[['id', 'big_chances_created', 'minutes']].copy()
    stats_df.rename(columns={'id': 'ID'}, inplace=True)

    # Merge stats into projections
    projections = projections.merge(stats_df, on='ID', how='left')

    # Calculate per-90 rates, handling division by zero and minimum minutes threshold
    # If minutes are below threshold, the rate is 0 to avoid small sample size bias
    projections['chances_created_per_90'] = projections.apply(
        lambda row: (row['big_chances_created'] / row['minutes'] * 90) if row['minutes'] >= min_minutes else 0, axis=1
    )

    # Estimate expected chances created for the upcoming gameweek based on xMins
    projections['estimated_chances_created'] = projections['chances_created_per_90'] * (projections['xMins'] / 90)

    # Calculate extra points: +1 point per chance created
    extra_points = projections['estimated_chances_created'] * 1

    projections["Predicted_Points"] += extra_points
    
    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    # Clean up temporary columns
    cols_to_drop = [
        "big_chances_created", "minutes", "chances_created_per_90", 
        "estimated_chances_created"
    ]
    return projections.drop(columns=cols_to_drop, errors='ignore')
