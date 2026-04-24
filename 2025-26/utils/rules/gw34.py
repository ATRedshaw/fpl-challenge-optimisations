import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
MAX_BONUS = 3
MAX_BONUS_EXTRA_POINTS = 7  # 10 awarded instead of 3, so uplift is +7
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


def calculate_max_bonus_rate(history: list[dict]) -> float:
    """
    Calculate the proportion of appearances in which a player earned maximum bonus points.

    Only considers finished matches (team_h_score is not None) where the player
    featured (minutes > 0).

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        float: Proportion of qualifying appearances with bonus == 3; 0.0 if none exist.
    """
    appearances = [
        g for g in history
        if g.get("team_h_score") is not None and g.get("minutes", 0) > 0
    ]
    if not appearances:
        return 0.0

    max_bonus_count = sum(1 for g in appearances if g.get("bonus", 0) == MAX_BONUS)
    return max_bonus_count / len(appearances)


def gw34_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 34 'MVP' challenge rules to player projections.

    Challenge rules:
        Players who collect the maximum bonus points (3) earn 10 points rather than 3.
        That's an uplift of +7 points on top of the standard allocation.

    Implementation:
        For each player, the season-to-date match history is retrieved from the
        FPL Challenge element summary API. The proportion of appearances where the
        player earned max bonus (bonus == 3) is computed across all finished matches
        where they featured (minutes > 0).

        Expected uplift is scaled by projected minutes::

            max_bonus_rate = count(bonus == 3) / count(appearances)
            expected_extra = max_bonus_rate * (xMins / 90) * 7

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

    def expected_extra(row: pd.Series) -> float:
        history = history_map.get(int(row["ID"]), [])
        max_bonus_rate = calculate_max_bonus_rate(history)
        x_mins = float(row.get("xMins", 90))
        scale = x_mins / 90.0
        return max_bonus_rate * scale * MAX_BONUS_EXTRA_POINTS

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_extra, axis=1)
    ).round(2)

    return projections
