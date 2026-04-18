import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
BONUS_POINTS_PER_FOUL_DRAWN = 4
BONUS_POINTS_PER_PENALTY_WON = 10
REQUEST_DELAY_SECONDS = 1.0

def fetch_player_history(player_id: int) -> list[dict]:
    """
    Fetch the season match history for a single player from the FPL Challenge API.

    Args:
        player_id (int): The player's FPL element ID.

    Returns:
        list[dict]: List of historical match records; empty list on any request failure.
    """
    url = ELEMENT_SUMMARY_URL.format(id=player_id)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("history", [])
    except requests.RequestException as exc:
        logger.warning("Failed to fetch element summary for player %d: %s", player_id, exc)
        return []


def calculate_mean_fouls_and_penalties(history: list[dict]) -> tuple[float, float]:
    """
    Calculate mean fouls drawn and penalties won per appearance from match history.

    Only considers finished matches (team_h_score is not None) where the player
    actually featured (minutes > 0), covering both starts and substitute appearances.

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        tuple[float, float]: (mean_fouls_won, mean_penalties_won) per qualifying
            appearance; both 0.0 if no qualifying appearances exist.
    """
    appearances = [
        g for g in history
        if g.get("team_h_score") is not None and g.get("minutes", 0) > 0
    ]
    if not appearances:
        return 0.0, 0.0

    n = len(appearances)
    mean_fouls = sum(g.get("fouls_won", 0) for g in appearances) / n
    mean_penalties = sum(g.get("penalties_won", 0) for g in appearances) / n
    return mean_fouls, mean_penalties



def gw33_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 33 'Unstoppable' challenge rules to player projections.

    Challenge rules:
        +4 points for each foul drawn.
        +10 points for each time fouled for a penalty.

    Implementation:
        For each player, the season-to-date match history is retrieved from the
        FPL Challenge element summary API. Mean fouls_won and penalties_won per
        appearance are computed across all finished matches where the player
        featured (minutes > 0).

        Expected bonus is scaled by projected minutes::

            fouls_rate   = mean_fouls_won * (xMins / 90)
            penalty_rate = mean_penalties_won * (xMins / 90)
            expected_bonus = fouls_rate * 4 + penalty_rate * 10

        This value is added directly to Predicted_Points.

    Args:
        projections (pd.DataFrame): Player projections DataFrame. Must contain
            an 'ID' column of integer FPL element IDs, a 'Predicted_Points'
            column of floats, and an 'xMins' column of expected minutes.

    Returns:
        pd.DataFrame: Copy of the input DataFrame with updated Predicted_Points.
    """
    player_ids: list[int] = projections["ID"].tolist()
    total = len(player_ids)
    history_map: dict[int, list[dict]] = {}

    print(f"  Fetching element summaries for {total} players ({REQUEST_DELAY_SECONDS}s delay between requests)...")

    for i, pid in enumerate(player_ids, start=1):
        history_map[pid] = fetch_player_history(pid)
        if i % 50 == 0 or i == total:
            print(f"  Progress: {i}/{total} players fetched.")
        if i < total:
            time.sleep(REQUEST_DELAY_SECONDS)

    def expected_bonus(row: pd.Series) -> float:
        history = history_map.get(int(row["ID"]), [])
        mean_fouls, mean_penalties = calculate_mean_fouls_and_penalties(history)
        x_mins = float(row.get("xMins", 90))
        scale = x_mins / 90.0
        return (mean_fouls * scale * BONUS_POINTS_PER_FOUL_DRAWN
                + mean_penalties * scale * BONUS_POINTS_PER_PENALTY_WON)

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_bonus, axis=1)
    ).round(2)

    return projections
