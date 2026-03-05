import logging
import math
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ELEMENT_SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{id}/"
BONUS_POINTS_FOR_GOAL_THREAT = 6
GOAL_THREAT_SHOT_THRESHOLD = 3
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


def calculate_mean_shots(history: list[dict]) -> float:
    """
    Calculate the mean number of total shot attempts per appearance from match history.

    Only considers finished matches (team_h_score is not None) where the player
    actually featured (minutes > 0), covering both starts and substitute appearances.

    Args:
        history (list[dict]): Historical match records from the element summary API.

    Returns:
        float: Mean total_shots per qualifying appearance; 0.0 if none exist.
    """
    appearances = [
        g for g in history
        if g.get("team_h_score") is not None and g.get("minutes", 0) > 0
    ]
    if not appearances:
        return 0.0

    return sum(g.get("total_shots", 0) for g in appearances) / len(appearances)


def poisson_probability_at_least_n(lambda_: float, n: int) -> float:
    """
    Calculate P(X >= n) for a Poisson-distributed random variable X with rate lambda_.

    Uses the complement of the cumulative mass function:
        P(X >= n) = 1 - sum_{k=0}^{n-1} [ e^{-lambda} * lambda^k / k! ]

    Args:
        lambda_ (float): The Poisson rate parameter (expected number of events).
        n (int): The minimum count threshold.

    Returns:
        float: Probability in [0.0, 1.0].
    """
    if lambda_ <= 0.0:
        return 0.0

    cumulative = sum(
        math.exp(-lambda_) * (lambda_ ** k) / math.factorial(k)
        for k in range(n)
    )
    return max(0.0, 1.0 - cumulative)


def gw30_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 30 'Goal Threat' challenge rules to player projections.

    Challenge rule:
        +6 points for any player who registers 3 or more goal attempts (total_shots).

    Implementation:
        For each player, the season-to-date match history is retrieved from the
        FPL Challenge element summary API. The mean shots per appearance is computed
        across all finished matches where the player featured (minutes > 0).

        Shot attempts are modelled as a Poisson process. The historical mean is
        scaled by the player's projected minutes (xMins) relative to a full 90
        to account for partial appearances::

            lambda = mean_shots_per_appearance * (xMins / 90)
            P(goal_threat) = P(X >= 3 | X ~ Poisson(lambda))
            expected_bonus  = P(goal_threat) * 6

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
        mean_shots = calculate_mean_shots(history)
        x_mins = float(row.get("xMins", 90))
        scaled_lambda = mean_shots * (x_mins / 90.0)
        prob = poisson_probability_at_least_n(scaled_lambda, GOAL_THREAT_SHOT_THRESHOLD)
        return prob * BONUS_POINTS_FOR_GOAL_THREAT

    projections = projections.copy()
    projections["Predicted_Points"] = (
        projections["Predicted_Points"] + projections.apply(expected_bonus, axis=1)
    ).round(2)

    return projections
