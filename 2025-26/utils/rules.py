import requests
import pandas as pd
import soccerdata as sd
from fuzzywuzzy import fuzz, process
from scipy.stats import poisson

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

def gw2_rules(projections):
    promoted_teams = ['Sunderland', 'Leeds', 'Burnley']
    projections.loc[projections['Team'].isin(promoted_teams), 'Predicted_Points'] *= 2
    return projections

def gw3_rules(projections):
    leagues = 'ENG-Premier League'
    season = '25-26'
    
    # Create an FBref scraper instance
    fbref = sd.FBref(leagues=leagues, seasons=season)
    
    # Read the 'defense' and 'misc' player stats tables
    df_defense = fbref.read_player_season_stats(stat_type='defense')
    df_misc = fbref.read_player_season_stats(stat_type='misc')
    
    # Reset the multi-index to make all index levels regular columns
    df_defense_reset = df_defense.reset_index()
    df_misc_reset = df_misc.reset_index()
    
    # Flatten the column names for easier access
    df_defense_reset.columns = ['_'.join(col).strip('_') for col in df_defense_reset.columns]
    df_misc_reset.columns = ['_'.join(col).strip('_') for col in df_misc_reset.columns]
    
    # Now extract the columns we need - adjust based on the actual flattened column names
    # We'll need to find the exact column names from the flattened structure
    defense_cols = ['league', 'season', 'team', 'player']
    
    # Find the correct column names for our stats
    for col in df_defense_reset.columns:
        if '90s' in col:
            defense_cols.append(col)
        elif 'TklW' in col:
            defense_cols.append(col)
        elif col == 'Int' or 'Int_' in col:
            defense_cols.append(col) 
        elif 'Blocks' in col and 'Blocks' in col:
            defense_cols.append(col)
        elif col == 'Clr' or 'Clr_' in col:
            defense_cols.append(col)
    
    df_defense_filtered = df_defense_reset[defense_cols]
    
    # For misc DataFrame
    misc_cols = ['league', 'season', 'team', 'player']
    for col in df_misc_reset.columns:
        if 'Recov' in col:
            misc_cols.append(col)
    
    df_misc_filtered = df_misc_reset[misc_cols]
    
    # Merge the DataFrames
    result_df = pd.merge(
        df_defense_filtered, 
        df_misc_filtered, 
        on=['league', 'season', 'team', 'player'], 
        how='inner'
    )
    
    # Rename columns to simple names
    column_mapping = {}
    for col in result_df.columns:
        if '90s' in col:
            column_mapping[col] = '90s'
        elif 'TklW' in col:
            column_mapping[col] = 'TklW'
        elif 'Int' in col and col not in ['league', 'season', 'team', 'player']:
            column_mapping[col] = 'Int'
        elif 'Blocks_Blocks' in col:
            column_mapping[col] = 'Blocks'  
        elif 'Clr' in col:
            column_mapping[col] = 'Clr'
        elif 'Recov' in col:
            column_mapping[col] = 'Recov'
    
    result_df = result_df.rename(columns=column_mapping)
    
    # Keep only the final columns you want
    final_columns = ['player', '90s', 'TklW', 'Int', 'Recov', 'Blocks', 'Clr']
    filtered_df = result_df[final_columns]
    
    # Fuzzy matching function
    def find_best_match(name, choices, threshold=50):
        """Find the best fuzzy match for a name in a list of choices"""
        if pd.isna(name):
            return None, 0
        
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0
    
    # Create a copy of projections to avoid modifying the original
    enhanced_projections = projections.copy()
    
    # Get list of FBRef player names
    fbref_players = filtered_df['player'].tolist()
    
    # Initialize new columns with NaN
    for col in ['90s', 'TklW', 'Int', 'Recov', 'Blocks', 'Clr']:
        enhanced_projections[f'fbref_{col}'] = None
    
    # Perform fuzzy matching for each player in projections
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row['Fuzzy']
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        
        if best_match:
            # Find the corresponding row in filtered_df
            fbref_row = filtered_df[filtered_df['player'] == best_match].iloc[0]
            
            # Add the FBRef stats to the projections
            enhanced_projections.at[idx, 'fbref_90s'] = fbref_row['90s']
            enhanced_projections.at[idx, 'fbref_TklW'] = fbref_row['TklW']
            enhanced_projections.at[idx, 'fbref_Int'] = fbref_row['Int']
            enhanced_projections.at[idx, 'fbref_Recov'] = fbref_row['Recov']
            enhanced_projections.at[idx, 'fbref_Blocks'] = fbref_row['Blocks']
            enhanced_projections.at[idx, 'fbref_Clr'] = fbref_row['Clr']
    
    # After the matching loop, ensure any remaining NaN values are set to 0
    fbref_stat_columns = ['fbref_90s', 'fbref_TklW', 'fbref_Int', 'fbref_Recov', 'fbref_Blocks', 'fbref_Clr']
    enhanced_projections[fbref_stat_columns] = enhanced_projections[fbref_stat_columns].fillna(0)

    # Calculate defensive actions per 90 based on position
    def calculate_defensive_actions(row):
        if row['Position'] == 'Goalkeeper':
            return 0
        
        # Avoid division by zero
        if row['fbref_90s'] == 0:
            return 0
        
        if row['fbref_90s'] <= 0.15:
            return 0
        
        # Calculate per-90 rates for each stat
        tackles_per_90 = row['fbref_TklW'] / row['fbref_90s']
        int_per_90 = row['fbref_Int'] / row['fbref_90s']
        clr_per_90 = row['fbref_Clr'] / row['fbref_90s']
        blocks_per_90 = row['fbref_Blocks'] / row['fbref_90s']
        
        if row['Position'] == 'Defender':
            # CBIT for defenders
            return tackles_per_90 + int_per_90 + clr_per_90 + blocks_per_90
        else:  # Midfielder or Forward
            # CBIRT for midfielders and forwards
            recov_per_90 = row['fbref_Recov'] / row['fbref_90s']
            return tackles_per_90 + int_per_90 + clr_per_90 + blocks_per_90 + recov_per_90

    # Apply the calculation
    enhanced_projections['defensive_actions_per_90'] = enhanced_projections.apply(calculate_defensive_actions, axis=1)

    # Drop all fbref columns
    fbref_columns = [col for col in enhanced_projections.columns if col.startswith('fbref_')]
    enhanced_projections = enhanced_projections.drop(columns=fbref_columns)

    # Calculate expected defensive actions based on expected minutes
    enhanced_projections['expected_defensive_actions'] = (
        enhanced_projections['defensive_actions_per_90'] * 
        (enhanced_projections['xMins'] / 90)
    )
    
    # Define a function to calculate the probability of reaching the threshold and the resulting xpts
    def calculate_challenge_xpts(row):
        """
        Calculates the expected defensive contribution points (xDCpts) for a player
        using a Poisson distribution.
        """
        # The expected number of defensive actions is the lambda for our Poisson distribution
        lambda_val = row['expected_defensive_actions']

        # If a player is not expected to play or has no defensive actions, return 0
        if lambda_val <= 0:
            return 0

        position = row['Position']
        
        # Defenders need to reach a threshold of 10 CBIT
        if position == 'Defender':
            # The probability of reaching the threshold is 1 - CDF(threshold - 1)
            # P(X >= 10) = 1 - P(X <= 9)
            prob_reaching_threshold = 1 - poisson.cdf(9, lambda_val)
        
        # Midfielders and Forwards need to reach a threshold of 12 CBIRT
        elif position in ['Midfielder', 'Forward']:
            # P(X >= 12) = 1 - P(X <= 11)
            prob_reaching_threshold = 1 - poisson.cdf(11, lambda_val)
            
        else:
            # Goalkeepers do not earn points from this rule
            prob_reaching_threshold = 0

        # The challenge awards 10 points for meeting the threshold
        expected_points = prob_reaching_threshold * 10
        return expected_points

    # Apply the function to the DataFrame to calculate expected defensive contribution points
    enhanced_projections['xDCpts'] = enhanced_projections.apply(calculate_challenge_xpts, axis=1)

    # Overwrite the 'Predicted_Points' column with the new total challenge points
    if 'Predicted_Points' in enhanced_projections.columns:
        enhanced_projections['Predicted_Points'] = round(enhanced_projections['Predicted_Points'] + enhanced_projections['xDCpts'], 1)
    else:
        # If 'Predicted_Points' doesn't exist, create it from the defensive points
        enhanced_projections['Predicted_Points'] = enhanced_projections['xDCpts']

    # Clean up intermediate columns before returning the final dataframe
    columns_to_drop = ['defensive_actions_per_90', 'expected_defensive_actions', 'xDCpts']
    enhanced_projections = enhanced_projections.drop(columns=columns_to_drop)

    return enhanced_projections