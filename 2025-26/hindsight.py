import os
import json
import requests
import pandas as pd
import yaml
import numpy as np
from collections import defaultdict
from utils.solver import FPLChallengeOptimiser
from utils.data import ensure_season_in_registry
from utils.actual import process_actual_outcome

BASE_URL = 'https://fplchallenge.premierleague.com/api'

ELEMENT_TYPE_MAP = {
    1: 'Goalkeeper',
    2: 'Defender',
    3: 'Midfielder',
    4: 'Forward',
}


def fetch_bootstrap() -> dict:
    """
    Fetch the FPL Challenge bootstrap-static payload.

    Returns:
        dict: Parsed JSON response containing elements, teams, events, etc.
    """
    response = requests.get(f'{BASE_URL}/bootstrap-static/')
    response.raise_for_status()
    return response.json()


def fetch_live(gameweek: int) -> dict:
    """
    Fetch live points data for a specific gameweek.

    Args:
        gameweek: The gameweek number to fetch.

    Returns:
        dict: Parsed JSON response containing per-element stats and points.
    """
    response = requests.get(f'{BASE_URL}/event/{gameweek}/live/')
    response.raise_for_status()
    return response.json()


def get_completed_gameweeks(events: list) -> list[int]:
    """
    Return a sorted list of gameweek IDs that are fully finished and checked.

    Args:
        events: List of event dicts from the bootstrap-static payload.

    Returns:
        list[int]: Sorted gameweek IDs where finished and data_checked are True.
    """
    return sorted(
        e['id']
        for e in events
        if e.get('finished') and e.get('data_checked')
    )


def build_player_dataframe(bootstrap: dict, live_data: dict) -> pd.DataFrame:
    """
    Construct a player DataFrame combining bootstrap metadata with actual
    points from the live endpoint.

    Args:
        bootstrap: Bootstrap-static payload (elements, teams).
        live_data: Live endpoint payload for a specific gameweek.

    Returns:
        pd.DataFrame: One row per player with ID, Name, Team, Position,
                      Cost, and Predicted_Points (actual points scored).
    """
    team_name_by_id = {t['id']: t['name'] for t in bootstrap['teams']}

    # Build a direct lookup from player ID to actual points for this GW
    live_points_by_id: dict[int, int] = {
        el['id']: el['stats']['total_points']
        for el in live_data['elements']
    }

    players = []
    for element in bootstrap['elements']:
        player_id = element['id']
        players.append({
            'ID': player_id,
            'Name': element['web_name'],
            'Team': team_name_by_id[element['team']],
            'Position': ELEMENT_TYPE_MAP[element['element_type']],
            'Cost': element['now_cost'] / 10,
            # Defaults to 0 if the player has no live entry for this GW
            'Predicted_Points': live_points_by_id.get(player_id, 0),
        })

    df = pd.DataFrame(players)
    df = df.sort_values(by='ID').reset_index(drop=True)
    return df


def save_actual_optimal(
    lineup: defaultdict,
    season: str,
    gameweek: int,
    output_path: str,
) -> None:
    """
    Persist the hindsight-optimal lineup for a gameweek to actual_optimal.json.
    Doubles the captain's points before writing, matching the predicted_optimal
    serialisation format.

    Args:
        lineup:      Selected players keyed by position from the solver.
        season:      Season directory string (e.g. '2025-26').
        gameweek:    Gameweek number being saved.
        output_path: Absolute path to the target JSON file.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            all_gameweeks: dict = json.load(f)
    else:
        all_gameweeks = {}

    def _serialise_player(player: dict) -> dict:
        result = {}
        for k, v in player.items():
            # Rename the solver's internal key to a context-appropriate label
            out_key = 'Points' if k == 'Predicted_Points' else k
            if isinstance(v, np.integer):
                result[out_key] = int(v)
            elif isinstance(v, np.floating):
                result[out_key] = float(v)
            else:
                result[out_key] = v
        return result

    converted = {
        pos: [_serialise_player(p) for p in players]
        for pos, players in lineup.items()
    }

    # Double the captain's contribution to match the actual scoring
    for players in converted.values():
        for player in players:
            if player['Captain']:
                player['Points'] *= 2

    total_cost = sum(
        p['Cost'] for players in converted.values() for p in players
    )
    total_points = sum(
        p['Points'] for players in converted.values() for p in players
    )

    all_gameweeks[str(gameweek)] = {
        'Players': converted,
        'Total_Cost': round(total_cost, 1),
        'Total_Points': round(total_points, 2),
    }

    all_gameweeks = dict(
        sorted(all_gameweeks.items(), key=lambda item: int(item[0]))
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Actual optimal for GW{gameweek} saved to {output_path}")

    # Mirror to the site data directory for the frontend
    site_path = os.path.join('site', 'data', season, 'actual_optimal.json')
    os.makedirs(os.path.dirname(site_path), exist_ok=True)
    with open(site_path, 'w', encoding='utf-8') as f:
        json.dump(all_gameweeks, f, indent=4, ensure_ascii=False)

    print(f"Actual optimal for GW{gameweek} mirrored to {site_path}")

    ensure_season_in_registry(season)


if __name__ == '__main__':
    FILE_PATH = os.path.abspath(__file__)
    SEASON = FILE_PATH.split('/')[-2]

    constraints_path = os.path.join(SEASON, 'data', 'constraints.yaml')
    with open(constraints_path, 'r') as f:
        all_constraints: dict = yaml.safe_load(f)

    output_path = os.path.join(SEASON, 'data', 'lineups', 'actual_optimal.json')

    # Identify which gameweeks have already been processed
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            existing_data: dict = json.load(f)
        already_processed: set[int] = {int(k) for k in existing_data}
    else:
        already_processed = set()

    outcome_path = os.path.join(SEASON, 'data', 'lineups', 'actual_outcome.json')
    if os.path.exists(outcome_path):
        with open(outcome_path, 'r', encoding='utf-8') as f:
            existing_outcomes: dict = json.load(f)
        outcome_processed: set[int] = {int(k) for k in existing_outcomes}
    else:
        outcome_processed = set()

    print('Fetching bootstrap data...')
    bootstrap = fetch_bootstrap()

    completed_gameweeks = get_completed_gameweeks(bootstrap['events'])
    print(f"Completed gameweeks: {completed_gameweeks}")

    for gw in completed_gameweeks:
        optimal_done = gw in already_processed
        outcome_done = gw in outcome_processed

        if optimal_done and outcome_done:
            print(f"\nGW{gw} already processed — skipping.")
            continue

        print(f"\n{'='*50}")
        print(f"Processing GW{gw}...")
        print(f"{'='*50}")

        live_data = fetch_live(gw)

        if not optimal_done:
            constraints_key = f'GW{gw}'
            if constraints_key not in all_constraints:
                print(f"No constraints found for GW{gw} — skipping optimal solver.")
            else:
                constraints = all_constraints[constraints_key]
                projections = build_player_dataframe(bootstrap, live_data)

                solver = FPLChallengeOptimiser(gw, projections)
                solver.setup_problem(
                    f"fpl-hindsight-{SEASON.replace('-', '')}-gw{gw}"
                )

                solver.total_players_constraint(constraints['total_players'])
                solver.captain_count_constraint(constraints['captain_count'])
                solver.position_count_constraints(constraints['position_constraints'])
                solver.max_players_from_same_team_constraint(constraints['max_per_team'])

                solver.solve()
                solver.print_players_by_position()

                save_actual_optimal(solver.selected_players, SEASON, gw, output_path)

        if not outcome_done:
            is_last = gw == completed_gameweeks[-1]
            process_actual_outcome(SEASON, gw, live_data, bootstrap, is_last_gameweek=is_last)

    print('\nHindsight optimisation complete.')
