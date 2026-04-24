import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
MAX_BONUS_POINTS = 3
CHALLENGE_BONUS_VALUE = 10
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


def calculate_max_bonus_probability(history: list[dict]) -> float:
    """
    Estimate the probability that a player earns maximum bonus points (3) in a
    given appearance, based on their season-to-date match history.

    Only considers finished matches (team_h_score is not None) where the player
    featured (minutes > 0). The probability is the fraction of those appearances
    in which the player received 3 bonus points.

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        float: Estimated P(bonus == 3) per qualifying appearance; 0.0 if no
            qualifying appearances exist.
    """
    appearances = [
        g for g in history
        if g.get("team_h_score") is not None and g.get("minutes", 0) > 0
    ]
    if not appearances:
        return 0.0

    max_bonus_count = sum(1 for g in appearances if g.get("bonus", 0) == MAX_BONUS_POINTS)
    return max_bonus_count / len(appearances)


def gw34_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 34 'MVP' challenge rules to player projections.

    Challenge rules:
        Players who collect the maximum bonus points (3) earn 10 points rather
        than the standard 3.

    Implementation:
        For each player, the season-to-date match history is retrieved from the
        FPL Challenge element summary API. P(bonus == 3) is estimated as the
        fraction of finished appearances (minutes > 0) in which the player
        received 3 bonus points.

        The projections already include expected bonus points under standard
        scoring (max 3). Under this challenge, a player earning max bonus is
        worth 10 rather than 3, so the effective uplift per appearance is::

            adjustment = P(bonus == 3) * (10 - 3)
                       = P(bonus == 3) * 7

        This is scaled by projected minutes to account for the likelihood the
        player features at all::

            expected_adjustment = P(bonus == 3) * 7 * (xMins / 90)

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

    bonus_uplift = CHALLENGE_BONUS_VALUE - MAX_BONUS_POINTS  # 7

    def expected_adjustment(row: pd.Series) -> float:
        history = history_map.get(int(row["ID"]), [])
        p_max_bonus = calculate_max_bonus_probability(history)
        x_mins = float(row.get("xMins", 90))
        scale = x_mins / 90.0
        return p_max_bonus * bonus_uplift * scale

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_adjustment, axis=1)
    ).round(2)

    return projections
