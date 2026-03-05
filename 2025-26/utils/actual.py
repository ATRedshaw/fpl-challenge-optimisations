import os
import json
from pathlib import Path

import requests
import yaml

from utils.data import ensure_season_in_registry

BASE_URL = 'https://fplchallenge.premierleague.com/api'


def fetch_entry_picks(gameweek: int, entry_id: int) -> dict:
    """
    Fetch picks and entry history for a specific gameweek.

    Args:
        gameweek:  Gameweek number to fetch.
        entry_id:  FPL Challenge team ID.

    Returns:
        dict: Parsed JSON response containing entry_history and picks.
    """
    response = requests.get(f'{BASE_URL}/entry/{entry_id}/event/{gameweek}/picks/')
    response.raise_for_status()
    return response.json()


def build_actual_outcome_for_gw(
    predicted_players: dict,
    live_data: dict,
    entry_history: dict,
) -> dict:
    """
    Build actual outcome data for a single gameweek.

    Cross-references the predicted squad with live points data and combines
    it with rank information extracted from the entry history.

    Args:
        predicted_players: Players dict from predicted_optimal.json (position -> list).
        live_data:         Parsed live endpoint payload for the gameweek.
        entry_history:     entry_history block from the picks endpoint response.

    Returns:
        dict: Outcome data keyed by Players, Ranks, Total_Cost, and Total_Points.
    """
    live_points_by_id: dict[int, int] = {
        el['id']: el['stats']['total_points']
        for el in live_data['elements']
    }

    outcome_players: dict[str, list] = {}
    for position, players in predicted_players.items():
        outcome_players[position] = []
        for player in players:
            player_id = player['ID']
            actual_points = live_points_by_id.get(player_id, 0)
            is_captain = player.get('Captain', False)
            multiplier = 2 if is_captain else 1

            outcome_players[position].append({
                'ID': player_id,
                'Name': player['Name'],
                'Team': player['Team'],
                'Cost': player['Cost'],
                'Points': actual_points * multiplier,
                'Captain': is_captain,
            })

    ranks: dict = {
        'rank': entry_history.get('rank'),
        'overall_rank': entry_history.get('overall_rank'),
        'percentile_rank': entry_history.get('percentile_rank'),
    }

    total_cost = sum(
        p['Cost'] for pos_players in outcome_players.values() for p in pos_players
    )
    total_points = sum(
        p['Points'] for pos_players in outcome_players.values() for p in pos_players
    )

    return {
        'Players': outcome_players,
        'Ranks': ranks,
        'Total_Cost': round(total_cost, 1),
        'Total_Points': round(total_points, 2),
    }


def save_actual_outcome(
    season: str,
    gameweek: int,
    outcome: dict,
    output_path: str,
    total_players: int | None = None,
) -> None:
    """
    Persist the actual outcome for a gameweek and mirror it to the site directory.

    total_players is written as a single top-level key after all gameweek entries
    rather than being nested inside any individual gameweek's Ranks dict.

    Args:
        season:        Season directory string (e.g. '2025-26').
        gameweek:      Gameweek number being saved.
        outcome:       Outcome data dict for the gameweek.
        output_path:   Absolute path to the target JSON file.
        total_players: Total competition entries; persisted at the top level.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            all_gameweeks: dict = json.load(f)
    else:
        all_gameweeks = {}

    # Preserve existing top-level total_players unless a new value is supplied
    existing_total: int | None = all_gameweeks.pop('total_players', None)

    all_gameweeks[str(gameweek)] = outcome
    all_gameweeks = dict(
        sorted(all_gameweeks.items(), key=lambda item: int(item[0]))
    )

    resolved_total = total_players if total_players is not None else existing_total
    if resolved_total is not None:
        all_gameweeks['total_players'] = resolved_total

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Actual outcome for GW{gameweek} saved to {output_path}")

    site_path = os.path.join('site', 'data', season, 'actual_outcome.json')
    os.makedirs(os.path.dirname(site_path), exist_ok=True)
    with open(site_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Actual outcome for GW{gameweek} mirrored to {site_path}")

    ensure_season_in_registry(season)


def process_actual_outcome(
    season: str,
    gameweek: int,
    live_data: dict,
    bootstrap: dict,
    is_last_gameweek: bool = False,
) -> None:
    """
    Process and persist the actual outcome for a single gameweek.

    Loads the predicted squad from predicted_optimal.json, fetches rank data
    from the entry picks endpoint, and combines with live points before saving.

    Args:
        season:           Season directory string (e.g. '2025-26').
        gameweek:         Gameweek number to process.
        live_data:        Parsed live endpoint payload for the gameweek.
        bootstrap:        Bootstrap-static payload.
        is_last_gameweek: Whether this is the most recent completed gameweek.
    """
    predicted_path = os.path.join(season, 'data', 'lineups', 'predicted_optimal.json')
    if not os.path.exists(predicted_path):
        print(f"predicted_optimal.json not found — skipping actual outcome for GW{gameweek}.")
        return

    with open(predicted_path, 'r', encoding='utf-8') as f:
        predicted_all: dict = json.load(f)

    gw_key = str(gameweek)
    if gw_key not in predicted_all:
        print(f"No predicted lineup found for GW{gameweek} — skipping actual outcome.")
        return

    predicted_players: dict = predicted_all[gw_key]['Players']

    config_path = Path(season) / 'data' / 'config.yaml'
    with config_path.open(encoding='utf-8') as f:
        config: dict = yaml.safe_load(f)
    entry_id: int = config['team_id']

    print(f"Fetching entry picks for GW{gameweek}...")
    picks_data = fetch_entry_picks(gameweek, entry_id)
    entry_history: dict = picks_data.get('entry_history', {})

    total_players: int | None = bootstrap.get('total_players') if is_last_gameweek else None

    outcome = build_actual_outcome_for_gw(
        predicted_players=predicted_players,
        live_data=live_data,
        entry_history=entry_history,
    )

    output_path = os.path.join(season, 'data', 'lineups', 'actual_outcome.json')
    save_actual_outcome(season, gameweek, outcome, output_path, total_players=total_players)
