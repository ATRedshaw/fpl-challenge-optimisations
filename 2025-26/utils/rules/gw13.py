import pandas as pd
import soccerdata as sd
import numpy as np
from fuzzywuzzy import fuzz, process

def gw13_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 13 rules: +1 point for every ball recovery.

    Methodology:
        - Calculates historical recoveries per 90 minutes from FBRef 'misc' data.
        - Derives expected recoveries for the specific gameweek based on 
          projected minutes (xMins).
        - Since the rule is linear (+1 pt per recovery), Expected Points (xPts) 
          is directly equal to the Expected Recoveries.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    recovery_data = get_recovery_data_with_minutes()
    
    # Helper to find matches
    def find_best_match(name: str, choices: list[str], threshold: int = 50) -> tuple[str | None, int]:
        if pd.isna(name):
            return None, 0
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0

    enhanced_projections = projections.copy()
    fbref_players = recovery_data['Player'].tolist()
    
    # Initialize mapping column
    enhanced_projections['hist_recov_per_90'] = 0.0

    # Map FBRef data to projections
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row.get('Fuzzy', row.get('Player'))
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        
        if best_match:
            stats = recovery_data[recovery_data['Player'] == best_match].iloc[0]
            enhanced_projections.at[idx, 'hist_recov_per_90'] = stats['Recov_Per_90']

    # Calculate expected recoveries for the specific gameweek
    # Formula: (Recoveries/90) * (xMins/90) * 90 -> (Recoveries/90) * xMins
    enhanced_projections['expected_recov_gw'] = (
        enhanced_projections['hist_recov_per_90'] * (enhanced_projections['xMins'] / 90)
    )

    # Calculate and apply expected points
    # Rule: +1 point per recovery
    enhanced_projections['recovery_xpts'] = enhanced_projections['expected_recov_gw'] * 1.0
    
    enhanced_projections['Predicted_Points'] = (
        enhanced_projections['Predicted_Points'] + enhanced_projections['recovery_xpts']
    ).round(2)

    # Cleanup
    drop_cols = ['hist_recov_per_90', 'expected_recov_gw', 'recovery_xpts']
    enhanced_projections = enhanced_projections.drop(columns=drop_cols)

    return enhanced_projections

def get_recovery_data():
    """
    Fetches miscellaneous statistics (including recoveries) from FBRef via Soccerdata.
    
    Returns:
        pd.DataFrame: DataFrame with 'Player' and 'Recov'.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"], no_cache=True)
    
    # Stat type 'misc' contains the 'Recov' column under 'Performance'
    misc = fbref.read_player_season_stats(stat_type="misc")
    
    # Extract specific column: ('Performance', 'Recov')
    # Use column intersection to avoid errors if structure varies slightly
    if ('Performance', 'Recov') in misc.columns:
        misc = misc.loc[:, [('Performance', 'Recov')]]
        misc.columns = ['Recov']
    else:
        # Fallback search if MultiIndex structure differs
        misc = misc.xs('Recov', level=1, axis=1, drop_level=False)
        misc.columns = ['Recov']
    
    misc = misc.reset_index()
    
    # Clean player names
    misc['player'] = misc['player'].str.replace(r'\s\(pen\)$', '', regex=True)
    misc = misc.rename(columns={'player': 'Player'})
    
    return misc

def get_minutes_played():
    """
    Fetches minutes played data from FBRef.
    
    Returns:
        pd.DataFrame: DataFrame with 'Player' and 'Minutes'.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"], no_cache=True)
    stats = fbref.read_player_season_stats(stat_type="standard")
    
    stats = stats.reset_index()
    stats = stats[[("player", ""), ("Playing Time", "Min")]]
    stats.columns = ["Player", "Minutes"]
    
    # Clean player names
    stats['Player'] = stats['Player'].str.replace(r'\s\(pen\)$', '', regex=True)
    
    return stats

def get_recovery_data_with_minutes():
    """
    Merges recovery data with minutes to calculate per-90 rates.
    
    Returns:
        pd.DataFrame: merged data with 'Recov_Per_90'.
    """
    recoveries = get_recovery_data()
    minutes = get_minutes_played()
    
    combined = recoveries.merge(minutes, on='Player', how='left')
    combined['Minutes'] = combined['Minutes'].fillna(0)
    
    # Calculate Recoveries Per 90
    combined['Recov_Per_90'] = np.where(
        combined['Minutes'] > 0,
        (combined['Recov'] / combined['Minutes']) * 90,
        0.0
    )

    return combined