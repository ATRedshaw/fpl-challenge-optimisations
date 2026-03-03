import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
BONUS_POINTS_FOR_90 = 6
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


def calculate_90min_probability(history: list[dict]) -> float:
    """
    Estimate the empirical probability of a player completing a full 90 minutes.

    Considers only games that have been played (team_h_score is not None) as the sample
    space. A qualifying 90-minute appearance satisfies all three conditions:
        - minutes >= 90
        - red_cards == 0
        - substitutions_off == 0

    Returns 0.0 for players with no recorded appearances, as no evidence exists
    to support a non-zero estimate.

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        float: Empirical probability in [0.0, 1.0].
    """
    appearances = [g for g in history if g.get("team_h_score") is not None]
    if not appearances:
        return 0.0

    full_90_count = sum(
        1 for g in appearances
        if g.get("minutes", 0) >= 90
        and g.get("red_cards", 0) == 0
        and g.get("substitutions_off", 0) == 0
    )

    return full_90_count / len(appearances)


def gw29_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 29 '90 Minutes' challenge rules to player projections.

    Challenge rule:
        +6 points for any player who completes 90 minutes without being
        substituted off or receiving a red card.

    Implementation:
        For each player, the season-to-date match history is retrieved
        sequentially from the FPL Challenge element summary API with a
        1-second delay between requests. The empirical probability of
        completing a full 90 minutes is computed from that history, then
        the expected bonus is calculated as::
            expected_bonus = P(completes 90 mins) * 6

        This value is added directly to Predicted_Points.

    Args:
        projections (pd.DataFrame): Player projections DataFrame. Must contain
            an 'ID' column of integer FPL element IDs and a 'Predicted_Points'
            column of floats.

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
        return calculate_90min_probability(history) * BONUS_POINTS_FOR_90

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_bonus, axis=1)
    ).round(2)

    return projections
