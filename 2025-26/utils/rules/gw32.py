import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
BONUS_POINTS_PER_OBOX_ATTEMPT = 4
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


def calculate_mean_obox_attempts(history: list[dict]) -> float:
    """
    Calculate the mean number of outside-the-box attempts per appearance from match history.

    Only considers finished matches (team_h_score is not None) where the player
    actually featured (minutes > 0), covering both starts and substitute appearances.

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        float: Mean attempts_obox per qualifying appearance; 0.0 if none exist.
    """
    appearances = [
        g for g in history
        if g.get("team_h_score") is not None and g.get("minutes", 0) > 0
    ]
    if not appearances:
        return 0.0

    return sum(g.get("attempts_obox", 0) for g in appearances) / len(appearances)



def gw32_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 32 'From Distance' challenge rules to player projections.

    Challenge rule:
        +4 points for each goal attempt made from outside the penalty area
        (on and off target).

    Implementation:
        For each player, the season-to-date match history is retrieved from the
        FPL Challenge element summary API. The mean attempts_obox per appearance
        is computed across all finished matches where the player featured
        (minutes > 0).

        Since the bonus is linear (4 points per attempt), expected bonus is
        simply the mean scaled by projected minutes::

            lambda = mean_obox_attempts_per_appearance * (xMins / 90)
            expected_bonus = lambda * 4

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
        mean_obox = calculate_mean_obox_attempts(history)
        x_mins = float(row.get("xMins", 90))
        scaled_mean = mean_obox * (x_mins / 90.0)
        return scaled_mean * BONUS_POINTS_PER_OBOX_ATTEMPT

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_bonus, axis=1)
    ).round(2)

    return projections
