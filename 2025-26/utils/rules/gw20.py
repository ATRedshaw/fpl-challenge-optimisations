import pandas as pd
import requests

def gw20_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 20 'Clean Start' rules to player projections.

    Adjusts predicted points by doubling the value of clean sheets.
    Since clean sheet probability is not explicitly in the input, this function fetches historical
    'clean_sheets' from the FPL API to estimate a per-90 rate,
    then applies that rate to the projected minutes (xMins).

    Standard scoring:
    - Goalkeeper Clean Sheet: 4 pts -> Extra 4 pts
    - Defender Clean Sheet: 4 pts -> Extra 4 pts
    - Midfielder Clean Sheet: 1 pt -> Extra 1 pt
    - Forward Clean Sheet: 0 pts -> Extra 0 pts

    Args:
        projections (pd.DataFrame): DataFrame of player projections containing
            'ID', 'xMins', 'Position', and 'Predicted_Points'.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    # Fetch bootstrap static data to get clean sheets
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    elements_df = pd.DataFrame(data['elements'])
    stats_df = elements_df[['id', 'clean_sheets', 'minutes']].copy()
    stats_df.rename(columns={'id': 'ID'}, inplace=True)

    # Merge stats into projections
    projections = projections.merge(stats_df, on='ID', how='left')

    # Calculate per-90 rates, handling division by zero
    # If minutes are 0, the rate is 0
    projections['clean_sheets_per_90'] = projections.apply(
        lambda row: (row['clean_sheets'] / row['minutes'] * 90) if row['minutes'] > 0 else 0, axis=1
    )

    # Estimate expected clean sheets for the upcoming gameweek based on xMins
    projections['estimated_clean_sheets'] = projections['clean_sheets_per_90'] * (projections['xMins'] / 90)

    # Define clean sheet points by position
    cs_points = {
        "Goalkeeper": 4,
        "Defender": 4,
        "Midfielder": 1,
        "Forward": 0
    }
    
    # Map position to clean sheet points value
    projections["cs_value"] = projections["Position"].map(cs_points).fillna(0)

    # Calculate extra points: (Estimated Clean Sheets * Clean Sheet Points)
    extra_points = projections["estimated_clean_sheets"] * projections["cs_value"]

    projections["Predicted_Points"] += extra_points
    
    # Round Predicted_Points to 2 decimal places for consistency
    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)

    # Clean up temporary columns
    cols_to_drop = [
        "clean_sheets", "minutes", "clean_sheets_per_90", 
        "estimated_clean_sheets", "cs_value"
    ]
    return projections.drop(columns=cols_to_drop, errors='ignore')
