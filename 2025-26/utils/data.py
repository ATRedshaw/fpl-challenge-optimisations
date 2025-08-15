import pandas as pd
import os
import json
from collections import defaultdict
import numpy as np

def save_projections(df, season, gameweek):
    projections_path = os.path.join(season, 'data', 'projections', f'gw{gameweek}.csv')
    if not os.path.exists(os.path.dirname(projections_path)):
        os.makedirs(os.path.dirname(projections_path))
    
    df.to_csv(projections_path, index=False)
    print(f"Projections saved to {projections_path}")

def save_optimal_prediction(lineup_prediction, season, gameweek):
    proceed = input(f"Save optimal prediction to {season}/data/lineups/predicted_optimal.json? (y/n): ")
    if proceed.lower() != 'y':
        return
    
    optimal_prediction_path = os.path.join(season, 'data', 'lineups', 'predicted_optimal.json')
    
    # Ensure directory exists
    if not os.path.exists(os.path.dirname(optimal_prediction_path)):
        os.makedirs(os.path.dirname(optimal_prediction_path))
    
    # Load existing data if file exists
    if os.path.exists(optimal_prediction_path):
        with open(optimal_prediction_path, 'r') as f:
            all_gameweeks = json.load(f)
    else:
        all_gameweeks = {}
    
    # Convert np.float64 to float for JSON serialization
    def convert_player(player):
        return {k: (float(v) if isinstance(v, np.float64) else v) for k, v in player.items()}
    
    converted_prediction = {pos: [convert_player(p) for p in players] 
                            for pos, players in lineup_prediction.items()}
    
    # Double points for the captain
    for pos, players in converted_prediction.items():
        for player in players:
            if player['Captain']:
                player['Predicted_Points'] *= 2
    
    # Calculate total cost and total predicted points
    total_cost = sum(player['Cost'] for players in converted_prediction.values() for player in players)
    total_points = sum(player['Predicted_Points'] for players in converted_prediction.values() for player in players)
    
    # Prepare data for this gameweek
    gw_data = {
        'Players': converted_prediction,
        'Total_Cost': round(total_cost, 1), 
        'Total_Points': round(total_points, 2)
    }
    
    # Update or add gameweek
    all_gameweeks[str(gameweek)] = gw_data
    
    # Ensure sort by gameweek
    all_gameweeks = dict(sorted(all_gameweeks.items(), key=lambda x: int(x[0])))
    
    # Save back to JSON with encoding
    with open(optimal_prediction_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Optimal prediction saved to {optimal_prediction_path}")
   