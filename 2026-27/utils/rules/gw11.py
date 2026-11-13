"""Projection adjustment for GW11: Make the Call."""

from __future__ import annotations

import time

import pandas as pd
import requests

CHALLENGE_BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
FPL_BASE_URL = "https://fantasy.premierleague.com/api"


def fetch_player_history(
    projections: pd.DataFrame,
    bootstrap: dict,
    session: requests.Session,
) -> pd.DataFrame:
    """Join ordinary FPL match points to Challenge IDs using stable codes."""
    codes = {int(player["id"]): int(player["code"]) for player in bootstrap["elements"]}
    players = {
        codes[int(player.ID)]: (int(player.ID), player.Position)
        for player in projections.itertuples()
    }
    response = session.get(f"{FPL_BASE_URL}/bootstrap-static/", timeout=60)
    response.raise_for_status()
    elements = [
        player
        for player in response.json()["elements"]
        if int(player["code"]) in players
    ]
    rows = []
    print(
        f"GW11: fetching ordinary FPL history for {len(elements)} players...",
        flush=True,
    )
    for number, player in enumerate(elements, 1):
        response = session.get(
            f"{FPL_BASE_URL}/element-summary/{player['id']}/", timeout=60
        )
        response.raise_for_status()
        player_id, position = players[int(player["code"])]
        for match in response.json()["history"]:
            if match["team_h_score"] is None or match["team_a_score"] is None:
                continue
            rows.append(
                {
                    "ID": player_id,
                    "Position": position,
                    "Round": int(match["round"]),
                    "Kickoff": match["kickoff_time"],
                    "Minutes": match["minutes"],
                    "Starts": match["starts"],
                    "Points": match["total_points"],
                }
            )
        if number % 50 == 0 or number == len(elements):
            print(f"  Fetched {number}/{len(elements)} players.", flush=True)
        if number < len(elements):
            time.sleep(0.2)
    return pd.DataFrame(
        rows,
        columns=[
            "ID",
            "Position",
            "Round",
            "Kickoff",
            "Minutes",
            "Starts",
            "Points",
        ],
    )


def estimate_substitute_points(
    history: pd.DataFrame,
    players: pd.DataFrame,
    cutoff: pd.Timestamp,
    shrinkage_appearances: int,
    half_life_days: int,
) -> pd.Series:
    """Shrink recency-weighted points per substitute appearance to position means."""
    past = history.loc[history["Kickoff"] < cutoff].copy()
    if past.empty:
        raise ValueError("No substitute appearances precede the estimation cutoff.")
    age_days = (cutoff - past["Kickoff"]).dt.total_seconds() / 86400
    past["Weight"] = 0.5 ** (age_days / half_life_days)
    past["Weighted_Points"] = past["Points"] * past["Weight"]
    columns = ["Weight", "Weighted_Points"]
    totals = past.groupby("ID")[columns].sum()
    positions = past.groupby("Position")[columns].sum()
    position_means = positions["Weighted_Points"] / positions["Weight"]
    prior = (
        players["Position"]
        .map(position_means)
        .fillna(past["Weighted_Points"].sum() / past["Weight"].sum())
    )
    appearances = players["ID"].map(totals["Weight"]).fillna(0)
    points = players["ID"].map(totals["Weighted_Points"]).fillna(0)
    return (points + shrinkage_appearances * prior) / (
        appearances + shrinkage_appearances
    )


def select_history_parameters(history: pd.DataFrame) -> tuple[int, int]:
    """Tune the conditional mean by squared error on five chronological GW holdouts."""
    validation = []
    for _, held_out in list(history.groupby("Round"))[-5:]:
        cutoff = held_out["Kickoff"].min()
        if (history["Kickoff"] < cutoff).any():
            validation.append((held_out, cutoff))
    best_parameters = (10, 90)
    best_error = float("inf")
    for shrinkage in (5, 10, 20, 40):
        for half_life in (30, 90, 180):
            squared_error = 0.0
            for held_out, cutoff in validation:
                predicted = estimate_substitute_points(
                    history, held_out, cutoff, shrinkage, half_life
                )
                squared_error += float(((predicted - held_out["Points"]) ** 2).sum())
            if validation and squared_error < best_error:
                best_error = squared_error
                best_parameters = (shrinkage, half_life)
    return best_parameters


def gw11_rules(
    projections: pd.DataFrame,
    *,
    bootstrap: dict | None = None,
    history: pd.DataFrame | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Estimate ordinary xPts + 2 P(substitute) E[points | substitute].

    XLTHM does not export points conditional on substitute status, so their
    conditional mean is estimated from ordinary FPL history, not Challenge
    scores. It includes deductions and is not scaled by minutes. This estimate
    does not adjust substitute points for the upcoming opponent or entry time.
    XLTHM appearance probabilities already incorporate availability.
    """
    adjusted = projections.copy()
    expected_substitutions = (
        adjusted["Appearance_Probability"] - adjusted["Start_Probability"]
    )
    if (expected_substitutions < -1e-6).any():
        raise ValueError("XLTHM start probabilities exceed appearance probabilities.")

    http = session or requests.Session()
    if bootstrap is None:
        response = http.get(CHALLENGE_BOOTSTRAP_URL, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()
    deadline = pd.Timestamp(
        next(event for event in bootstrap["events"] if int(event["id"]) == 11)[
            "deadline_time"
        ]
    )
    cutoff = min(pd.Timestamp.now(tz="UTC"), deadline)
    if history is None:
        history = fetch_player_history(projections, bootstrap, http)
    history = history.copy()
    history["Kickoff"] = pd.to_datetime(history["Kickoff"], utc=True)
    history = history.loc[
        (history["Round"] < 11)
        & (history["Kickoff"] < cutoff)
        & (history["Starts"] == 0)
        & (history["Minutes"] > 0)
    ].copy()
    if history.empty:
        raise ValueError("No completed substitute appearances precede GW11.")

    shrinkage, half_life = select_history_parameters(history)
    print(
        f"GW11 substitute points estimate: {shrinkage} prior appearances, "
        f"{half_life}-day half-life; {len(history)} historical substitute appearances."
    )
    adjusted["Base_Predicted_Points"] = adjusted["Predicted_Points"]
    # Summed fixture probabilities are expected counts in a double gameweek.
    adjusted["Expected_Substitute_Appearances"] = expected_substitutions.clip(lower=0)
    adjusted["Substitute_Conditional_xPts"] = estimate_substitute_points(
        history, adjusted, cutoff, shrinkage, half_life
    )
    adjusted["Substitute_Contribution_xPts"] = (
        adjusted["Expected_Substitute_Appearances"]
        * adjusted["Substitute_Conditional_xPts"]
    )
    adjusted["GW11_Extra_xPts"] = 2 * adjusted["Substitute_Contribution_xPts"]
    adjusted["Predicted_Points"] = (
        adjusted["Base_Predicted_Points"] + adjusted["GW11_Extra_xPts"]
    ).round(2)
    return adjusted
