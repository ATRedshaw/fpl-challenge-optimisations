import pandas as pd
import soccerdata as sd
import numpy as np
from fuzzywuzzy import fuzz, process

def gw8_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 8 rules to player projections.

    Rules:
        - 6 Additional points for every expected 'big chance scored' by a player.
        - Uses big chance xG per 90 minutes multiplied by expected minutes.
        - Matches players using fuzzy string matching.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """
    shot_data = get_shot_data_with_minutes()
    
    # Calculate big chance xG rate per 90 minutes
    shot_data['big_chance_xG_per90'] = np.where(
        shot_data['Minutes'] > 0,
        (shot_data['Total_Big_Chance_xG'] / shot_data['Minutes']) * 90,
        0
    )
    
    def find_best_match(name: str, choices: list[str], threshold: int = 50) -> tuple[str | None, int]:
        """Return the closest fuzzy match above threshold."""
        if pd.isna(name):
            return None, 0
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0
    
    enhanced_projections = projections.copy()
    fbref_players = shot_data['Player'].tolist()
    enhanced_projections['fbref_big_chance_xG_per90'] = 0.0
    
    # Match each player to fbref data and populate big chance xG rate
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row['Fuzzy']
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        if best_match:
            fbref_row = shot_data[shot_data['Player'] == best_match].iloc[0]
            enhanced_projections.at[idx, 'fbref_big_chance_xG_per90'] = fbref_row['big_chance_xG_per90']
    
    # Calculate expected big chance xG for this gameweek based on expected minutes
    enhanced_projections['expected_big_chance_xG_gw'] = (
        enhanced_projections['fbref_big_chance_xG_per90'] * (enhanced_projections['xMins'] / 90)
    )
    
    # Apply 6 points per expected big chance xG
    enhanced_projections['additional_xpts'] = enhanced_projections['expected_big_chance_xG_gw'] * 6
    
    # Exclude goalkeepers from receiving additional points
    enhanced_projections.loc[enhanced_projections['Position'] == 'Goalkeeper', 'additional_xpts'] = 0
    
    enhanced_projections['Predicted_Points'] = (
        enhanced_projections['Predicted_Points'] + enhanced_projections['additional_xpts']
    ).round(2)
    
    # Remove temporary calculation columns
    enhanced_projections = enhanced_projections.drop(
        columns=['fbref_big_chance_xG_per90', 'expected_big_chance_xG_gw', 'additional_xpts']
    )
    
    return enhanced_projections

def get_shot_data():
    """
    Gets the shot data for the season from fbref via the Soccerdata library.
    Transforms the data into player-level statistics including total shots, xG,
    goals scored, big chances, and big chances scored.
    
    Returns:
        pd.DataFrame: DataFrame with columns: player, Total_Shots, Total_xG, 
                      Total_Scored, Total_Big_Chances, Total_Big_Chances_Scored,
                      Total_Big_Chance_xG, Avg_Big_Chance_xG.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"])
    shots = fbref.read_shot_events()

    shots.columns = shots.columns.droplevel(1)

    # Remove (pen) if present from player name
    shots['player'] = shots['player'].str.replace(r'\sKATEX_INLINE_OPEN\w+KATEX_INLINE_CLOSE$', '', regex=True)
    
    # Define big chance as xG >= 0.4
    shots['is_goal'] = shots['outcome'] == 'Goal'
    shots['is_big_chance'] = shots['xG'] >= 0.4
    shots['is_big_chance_scored'] = (shots['xG'] >= 0.4) & (shots['outcome'] == 'Goal')
    shots['big_chance_xg'] = shots['xG'].where(shots['xG'] >= 0.4, 0)
    
    # Aggregate shot statistics per player
    player_stats = shots.groupby('player').agg(
        Total_Shots=('player', 'count'),
        Total_xG=('xG', 'sum'),
        Total_Scored=('is_goal', 'sum'),
        Total_Big_Chances=('is_big_chance', 'sum'),
        Total_Big_Chances_Scored=('is_big_chance_scored', 'sum'),
        Total_Big_Chance_xG=('big_chance_xg', 'sum')
    ).reset_index()
    
    player_stats['Total_xG'] = player_stats['Total_xG'].round(2)
    player_stats['Total_Big_Chance_xG'] = player_stats['Total_Big_Chance_xG'].round(2)
    player_stats['Avg_Big_Chance_xG'] = np.where(
        player_stats['Total_Big_Chances'] > 0,
        (player_stats['Total_Big_Chance_xG'] / player_stats['Total_Big_Chances']).round(2),
        0
    )

    player_stats = player_stats.rename(columns={'player': 'Player'})
    
    return player_stats

def get_minutes_played():
    """
    Gets the minutes played data for the season from fbref via the Soccerdata library.
    
    Returns:
        pd.DataFrame: DataFrame with minutes played data.
    """
    fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=["2526"])
    player_stats = fbref.read_player_season_stats(stat_type="standard")

    player_stats = player_stats.reset_index()
    # Extract only player name and minutes played columns
    player_stats = player_stats[[("player", ""), ("Playing Time", "Min")]]
    player_stats.columns = ["Player", "Minutes"]

    return player_stats

def get_shot_data_with_minutes():
    """
    Gets shot data and minutes played data, then merges them together.
    
    Returns:
        pd.DataFrame: DataFrame with shot statistics and minutes played combined.
    """
    shot_data = get_shot_data()
    minutes_data = get_minutes_played()
    
    # Merge shot statistics with minutes played on player name
    combined_data = shot_data.merge(minutes_data, on='Player', how='left')
    
    return combined_data