import pandas as pd
import soccerdata as sd
import numpy as np
from scipy.stats import binom
from fuzzywuzzy import fuzz, process

def gw12_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 12 rules: +6 points for >= 90% pass completion 
    (min 30 passes attempted).

    Methodology:
        - Calculates historical pass completion rate (p) and attempts per 90.
        - Derives expected pass attempts (n) based on projected minutes (xMins).
        - Models the probability of achieving >= 90% accuracy using the 
          Binomial Survival Function (1 - CDF).
        - Adds Expected Points (xPts) = 6 * Probability.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    passing_data = get_passing_data_with_minutes()
    
    # Helper to find matches
    def find_best_match(name: str, choices: list[str], threshold: int = 50) -> tuple[str | None, int]:
        if pd.isna(name):
            return None, 0
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0

    enhanced_projections = projections.copy()
    fbref_players = passing_data['Player'].tolist()
    
    # Initialize mapping columns
    enhanced_projections['hist_completion_rate'] = 0.0
    enhanced_projections['hist_att_per_90'] = 0.0

    # Map FBRef data to projections
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row.get('Fuzzy', row.get('Player')) # Fallback to Player if Fuzzy missing
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        
        if best_match:
            stats = passing_data[passing_data['Player'] == best_match].iloc[0]
            enhanced_projections.at[idx, 'hist_completion_rate'] = stats['Completion_Rate']
            enhanced_projections.at[idx, 'hist_att_per_90'] = stats['Att_Per_90']

    # Calculate expected attempts for the specific gameweek
    enhanced_projections['expected_att_gw'] = (
        enhanced_projections['hist_att_per_90'] * (enhanced_projections['xMins'] / 90)
    )

    def calculate_challenge_probability(row):
        n = row['expected_att_gw']
        p = row['hist_completion_rate']
        
        # Rule constraint: Minimum 30 passes attempted
        # If expected attempts are significantly below 30, probability approaches 0
        if n < 30:
            return 0.0
            
        # Calculate required successes (k) to hit 90%
        k_target = np.ceil(0.90 * n)
        
        # Binomial Survival Function: P(X >= k) given n trials and probability p
        # We use integer casting for n as binomial is discrete
        prob = binom.sf(k_target - 1, int(n), p)
        return prob

    # Apply probability model
    enhanced_projections['challenge_prob'] = enhanced_projections.apply(
        calculate_challenge_probability, axis=1
    )
    
    # Calculate and apply expected points
    enhanced_projections['possession_xpts'] = enhanced_projections['challenge_prob'] * 6
    
    enhanced_projections['Predicted_Points'] = (
        enhanced_projections['Predicted_Points'] + enhanced_projections['possession_xpts']
    ).round(2)

    # Cleanup
    drop_cols = [
        'hist_completion_rate', 'hist_att_per_90', 
        'expected_att_gw', 'challenge_prob', 'possession_xpts'
    ]
    enhanced_projections = enhanced_projections.drop(columns=drop_cols)

    return enhanced_projections

def get_passing_data():
    """
    Fetches passing statistics from FBRef via Soccerdata.
    
    Returns:
        pd.DataFrame: DataFrame with 'Player', 'Total_Att', 'Total_Cmp'.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"])
    
    # Stat type 'passing' returns MultiIndex columns (Total, Short, Medium, Long)
    passing = fbref.read_player_season_stats(stat_type="passing")
    
    # Flatten columns or extract specific tuples
    # Standard structure: ('Total', 'Cmp'), ('Total', 'Att')
    passing = passing.loc[:, [('Total', 'Cmp'), ('Total', 'Att')]]
    passing.columns = ['Total_Cmp', 'Total_Att']
    
    passing = passing.reset_index()
    
    # Clean player names
    passing['player'] = passing['player'].str.replace(r'\s\(pen\)$', '', regex=True)
    passing = passing.rename(columns={'player': 'Player'})
    
    return passing

def get_minutes_played():
    """
    Fetches minutes played data from FBRef.
    
    Returns:
        pd.DataFrame: DataFrame with 'Player' and 'Minutes'.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"])
    stats = fbref.read_player_season_stats(stat_type="standard")
    
    stats = stats.reset_index()
    stats = stats[[("player", ""), ("Playing Time", "Min")]]
    stats.columns = ["Player", "Minutes"]
    
    # Clean player names
    stats['Player'] = stats['Player'].str.replace(r'\s\(pen\)$', '', regex=True)
    
    return stats

def get_passing_data_with_minutes():
    """
    Merges passing data with minutes to calculate per-90 rates and completion %.
    
    Returns:
        pd.DataFrame: merged data with 'Att_Per_90' and 'Completion_Rate'.
    """
    passing = get_passing_data()
    minutes = get_minutes_played()
    
    combined = passing.merge(minutes, on='Player', how='left')
    combined['Minutes'] = combined['Minutes'].fillna(0)
    
    # Calculate Completions % (p)
    # Use a small epsilon or fillna to handle 0 attempts
    combined['Completion_Rate'] = np.where(
        combined['Total_Att'] > 0,
        combined['Total_Cmp'] / combined['Total_Att'],
        0.0
    )
    
    # Calculate Attempts Per 90 (lambda)
    combined['Att_Per_90'] = np.where(
        combined['Minutes'] > 0,
        (combined['Total_Att'] / combined['Minutes']) * 90,
        0.0
    )
    
    return combined