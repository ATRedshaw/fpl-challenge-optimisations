import pandas as pd
import os
import json
from collections import defaultdict
import numpy as np


SEASONS_REGISTRY = os.path.join('site', 'data', 'seasons.json')


def ensure_season_in_registry(season: str) -> None:
    """
    Guarantee that a season is present in site/data/seasons.json.

    Reads the existing registry, appends the season if absent, sorts the list
    chronologically and writes it back. A missing registry file is created
    automatically.

    Args:
        season: Season string in YYYY-YY format (e.g. '2025-26').
    """
    os.makedirs(os.path.dirname(SEASONS_REGISTRY), exist_ok=True)

    if os.path.exists(SEASONS_REGISTRY):
        with open(SEASONS_REGISTRY, 'r', encoding='utf-8') as f:
            raw = f.read().strip()
        seasons: list[str] = json.loads(raw) if raw else []
    else:
        seasons = []

    if season not in seasons:
        seasons.append(season)
        seasons.sort()
        with open(SEASONS_REGISTRY, 'w', encoding='utf-8') as f:
            json.dump(seasons, f, indent=4, ensure_ascii=False)
        print(f"Season {season} added to {SEASONS_REGISTRY}")


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
    
    def convert_player(player: dict) -> dict:
        result = {}
        for k, v in player.items():
            if isinstance(v, np.integer):
                result[k] = int(v)
            elif isinstance(v, np.floating):
                result[k] = float(v)
            else:
                result[k] = v
        return result
    
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

    # Mirror to the site data directory for the frontend
    site_path = os.path.join('site', 'data', season, 'predicted_optimal.json')
    os.makedirs(os.path.dirname(site_path), exist_ok=True)
    with open(site_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Optimal prediction mirrored to {site_path}")

    ensure_season_in_registry(season)
   