import pandas as pd
import soccerdata as sd
import numpy as np
from fuzzywuzzy import fuzz, process

def gw10_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Applies the Gameweek 10 'Winning Feeling' challenge rules to player projections.
    
    Rule: Double points for all Expected Winning goals. One Player per Club.
    
    The bonus is distributed probabilistically. The team's total expected bonus 
    is P(Team Win) * Bonus Value, distributed among players weighted by their 
    Expected Goals contribution (E_goals).

    Args:
        projections (pd.DataFrame): DataFrame with player FPL data. Must contain
                                    'Fuzzy' (for matching), 'Team' (team name), 
                                    'xMins' (expected minutes), and 'Predicted_Points'.

    Returns:
        pd.DataFrame: Updated DataFrame with 'Predicted_Points' reflecting the rule.
    """

    # Win probabilities (P_win)
    # Values are normalized to a 0.0 to 1.0 probability.
    GW10_WIN_PROBABILITIES = {
        'Arsenal': 0.80,
        'Aston Villa': 0.23,
        'Bournemouth': 0.17,
        'Brentford': 0.27,
        'Brighton': 0.51,
        'Burnley': 0.10,
        'Chelsea': 0.40,
        'Crystal Palace': 0.51,
        'Everton': 0.38,
        'Fulham': 0.57,
        'Leeds': 0.27,
        'Liverpool': 0.60,
        'Manchester City': 0.67,
        'Manchester Utd': 0.49,
        'Newcastle': 0.63,
        'Nott\'m Forest': 0.30,
        'Spurs': 0.36,
        'Sunderland': 0.36,
        'West Ham': 0.19,
        'Wolves': 0.22,
    }

    # Points multiplier for the 'double' points (5 extra points for a goal, total 10). 
    GW_GOAL_POINTS_EXTRA = 5 
    
    def get_player_xg_rate(season: str = "2526") -> pd.DataFrame:
        """
        Retrieves total Expected Goals (xG) and minutes played from FBref.
        
        Calculates the Expected Goals rate per 90 minutes (xG_per90).

        Args:
            season (str): The season identifier.

        Returns:
            pd.DataFrame: DataFrame with columns 'Player' and 'xG_per90'.
        """
        fbref = sd.FBref(leagues=["ENG-Premier League"], seasons=[season])
        
        # Get standard player stats for Minutes
        player_stats = fbref.read_player_season_stats(stat_type="standard")
        player_stats = player_stats.reset_index()
        minutes_data = player_stats[[("player", ""), ("Playing Time", "Min")]].copy()
        minutes_data.columns = ["Player", "Minutes"]
        
        # Get shooting player stats for xG
        shooting_stats = fbref.read_player_season_stats(stat_type="shooting")
        shooting_stats = shooting_stats.reset_index()
        
        # Access xG column
        try:
            xg_data = shooting_stats[[("player", ""), ("Expected", "xG")]].copy()
        except KeyError:
            # Fallback if the multi-index structure is different
            raise ValueError("FBref 'Expected xG' column not found.")
            
        xg_data.columns = ["Player", "Total_xG"]
            
        # Merge data
        combined_data = minutes_data.merge(xg_data, on='Player', how='left').fillna(0)
        
        # xG per 90 calculation
        combined_data['xG_per90'] = np.where(
            combined_data['Minutes'] > 0,
            (combined_data['Total_xG'] / combined_data['Minutes']) * 90,
            0
        ).round(4)
        
        return combined_data[['Player', 'xG_per90']]
    
    def find_best_match(name: str, choices: list[str], threshold: int = 50) -> tuple[str | None, int]:
        """
        Uses fuzzy string matching to find the best match for a name.

        Args:
            name (str): The name to match.
            choices (list[str]): The list of possible names.
            threshold (int): Minimum fuzzy score required for a match.

        Returns:
            tuple[str | None, int]: The best matching name and its score.
        """
        if pd.isna(name):
            return None, 0
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0
    
    # 1. Fetch and merge player xG rate
    xg_data = get_player_xg_rate()
    enhanced_projections = projections.copy()
    fbref_players = xg_data['Player'].tolist()
    enhanced_projections['fbref_xG_per90'] = 0.0
    
    # Iterate and fuzzy-match to populate xG rate
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row['Fuzzy']
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        if best_match:
            fbref_row = xg_data[xg_data['Player'] == best_match].iloc[0]
            enhanced_projections.at[idx, 'fbref_xG_per90'] = fbref_row['xG_per90']
    
    # 2. Calculate Expected Goals (E_goals)
    
    # Player Expected Goals for GW10
    enhanced_projections['E_goals'] = (
        enhanced_projections['fbref_xG_per90'] * (enhanced_projections['xMins'] / 90)
    )
    
    # Merge team win probabilities (P_win) using 'Team' column
    enhanced_projections['Win_Prob'] = enhanced_projections['Team'].map(GW10_WIN_PROBABILITIES).fillna(0.0)
    
    # Calculate the Total Expected Goals for the team
    team_total_xg = enhanced_projections.groupby('Team')['E_goals'].sum().rename('Team_Total_E_goals')
    enhanced_projections = enhanced_projections.merge(team_total_xg, on='Team', how='left')
    
    # Calculate the Team's Total Expected Bonus: P(Team Win) * Bonus Points
    # This is the maximum expected bonus the entire team can distribute.
    enhanced_projections['Team_Total_E_Bonus'] = (
        enhanced_projections['Win_Prob'] * GW_GOAL_POINTS_EXTRA
    )

    # Distribution factor: Player's E_goals / Team's Total E_goals
    # Avoid division by zero by setting factor to 0 where team total xG is 0
    enhanced_projections['distribution_factor'] = np.where(
        enhanced_projections['Team_Total_E_goals'] > 0,
        enhanced_projections['E_goals'] / enhanced_projections['Team_Total_E_goals'],
        0.0
    )

    # Apply weighted bonus: Distribution Factor * Team's Total Expected Bonus
    # This correctly distributes the P(Win) bonus based on player's expected contribution (E_goals).
    enhanced_projections['additional_xpts'] = (
        enhanced_projections['distribution_factor'] * enhanced_projections['Team_Total_E_Bonus']
    )
    
    # 4. Update Predicted Points
    enhanced_projections['Predicted_Points'] = (
        enhanced_projections['Predicted_Points'] + enhanced_projections['additional_xpts']
    ).round(2)
    
    # 5. Cleanup temporary columns
    enhanced_projections = enhanced_projections.drop(
        columns=[
            'fbref_xG_per90', 'E_goals', 'Win_Prob', 
            'Team_Total_E_goals', 'Team_Total_E_Bonus',
            'distribution_factor', 'additional_xpts'
        ], 
        errors='ignore'
    )
    
    return enhanced_projections