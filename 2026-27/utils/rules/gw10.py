"""Projection adjustment for GW10: Spectacular."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

FOTMOB_URL = "https://www.fotmob.com/api/data"
BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
SEASON_ROOT = Path(__file__).resolve().parents[2]
POSITION_MAP = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
EVENT_COLUMNS = ["Outside_Saved_Shots", "Outside_Goals"]


def parse_match_history(payload: dict, season: str) -> list[dict]:
    """Count outside-box saves and goals, joining FotMob IDs to Opta codes."""
    match = payload["general"]
    if not match["finished"]:
        raise ValueError(f"FotMob match {match['matchId']} is not finished.")

    players = {}
    for player in payload["content"]["playerStats"].values():
        stats = {
            stat["key"]: stat["stat"]
            for group in player["stats"]
            for stat in group["stats"].values()
            if stat.get("key")
        }
        minutes = stats.get("minutes_played", {}).get("value", 0)
        if minutes <= 0:
            continue
        players[int(player["id"])] = {
            "Match_ID": int(match["matchId"]),
            "Season": season,
            "Round": int(match["matchRound"]),
            "Kickoff": match["matchTimeUTCDate"],
            "Code": int(str(player["optaId"]).removeprefix("p")),
            "Position": POSITION_MAP[player["usualPosition"]],
            "Team_ID": int(player["teamId"]),
            "Minutes": minutes,
            "Outside_Saved_Shots": 0,
            "Outside_Goals": 0,
        }
    if not players or len({row["Team_ID"] for row in players.values()}) != 2:
        raise ValueError(f"Incomplete FotMob player data for match {match['matchId']}.")

    # A missing shot map is a coverage failure, not a match with zero shots.
    for shot in payload["content"]["shotmap"]["shots"]:
        if shot["isOwnGoal"] or shot["period"] not in {"FirstHalf", "SecondHalf"}:
            continue
        if shot["isFromInsideBox"]:
            continue
        goal = shot["eventType"] == "Goal"
        if goal or shot["isOnTarget"]:
            event = "Outside_Goals" if goal else "Outside_Saved_Shots"
            players[int(shot["playerId"])][event] += 1
    return list(players.values())


def fetch_player_history(
    gameweek: int,
    *,
    cutoff: pd.Timestamp | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch two PL seasons, stopping before the target GW and its deadline."""
    http = session or requests.Session()
    start_year = int(SEASON_ROOT.name.split("-")[0])
    now = pd.Timestamp.now(tz="UTC")
    cutoff = min(now, cutoff) if cutoff is not None else now
    rows = []
    # Read the current season first so the same cutoff applies to both seasons.
    for year in (start_year, start_year - 1):
        season = f"{year}/{year + 1}"
        response = http.get(
            f"{FOTMOB_URL}/leagues", params={"id": 47, "season": season}, timeout=60
        )
        response.raise_for_status()
        league = response.json()
        if league["details"]["selectedSeason"] != season:
            raise ValueError(f"FotMob did not return the requested season {season}.")
        fixtures = league["fixtures"]["allMatches"]
        if year == start_year:
            target_kickoffs = [
                pd.Timestamp(fixture["status"]["utcTime"])
                for fixture in fixtures
                if int(fixture["round"]) == gameweek
            ]
            if not target_kickoffs:
                raise ValueError(f"FotMob has no fixtures for GW{gameweek}.")
            cutoff = min(cutoff, min(target_kickoffs))
        completed = [
            fixture
            for fixture in fixtures
            if fixture["status"].get("finished")
            and not fixture["status"].get("cancelled")
            and not fixture["status"].get("awarded")
            and pd.Timestamp(fixture["status"]["utcTime"]) < cutoff
            and (year < start_year or int(fixture["round"]) < gameweek)
        ]
        print(
            f"FotMob {season}: fetching {len(completed)} completed matches...",
            flush=True,
        )
        for number, fixture in enumerate(completed, 1):
            response = http.get(
                f"{FOTMOB_URL}/matchDetails",
                params={"matchId": fixture["id"]},
                timeout=60,
            )
            response.raise_for_status()
            rows.extend(parse_match_history(response.json(), season))
            if number % 20 == 0:
                print(f"  Fetched {number} matches.", flush=True)
            time.sleep(0.2)

    if not rows:
        raise ValueError("No completed FotMob player history found.")
    history = pd.DataFrame(rows)
    history["Kickoff"] = pd.to_datetime(history["Kickoff"], utc=True)
    if history.duplicated(["Match_ID", "Code"]).any():
        raise ValueError("FotMob history contains duplicate player-match records.")
    history = history.sort_values(["Kickoff", "Match_ID", "Code"]).reset_index(
        drop=True
    )
    history.attrs["cutoff"] = cutoff
    return history


def estimate_rates(
    history: pd.DataFrame,
    players: pd.DataFrame,
    cutoff: pd.Timestamp,
    shrinkage_minutes: int,
    half_life_days: int,
) -> pd.DataFrame:
    """Gamma-Poisson posterior means with recency weights and position priors.

    Saved shots and goals are disjoint counts. Fitting them separately keeps
    expected goals below expected shots on target, even with different priors.
    Prior minutes are equivalent exposure; observed zero-event minutes count.
    """
    past = history.loc[history["Kickoff"] < cutoff].copy()
    if past.empty:
        raise ValueError("No FotMob history precedes the rate-estimation cutoff.")
    age_days = (cutoff - past["Kickoff"]).dt.total_seconds() / 86400
    columns = ["Minutes", *EVENT_COLUMNS]
    past[columns] = past[columns].mul(0.5 ** (age_days / half_life_days), axis=0)
    totals = past.groupby("Code")[columns].sum()
    positions = past.groupby("Position")[columns].sum()
    observed_minutes = players["Code"].map(totals["Minutes"]).fillna(0)
    rates = pd.DataFrame(index=players.index)
    for event in EVENT_COLUMNS:
        position_rates = 90 * positions[event] / positions["Minutes"]
        prior = (
            players["Position"]
            .map(position_rates)
            .fillna(90 * past[event].sum() / past["Minutes"].sum())
        )
        events = players["Code"].map(totals[event]).fillna(0)
        rates[event] = (90 * events + shrinkage_minutes * prior) / (
            observed_minutes + shrinkage_minutes
        )
    return rates


def select_rate_parameters(history: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """Tune each count's Poisson log score on five rolling GW holdouts.

    All priors and player rates in a fold use only matches before that GW.
    Actual minutes are exposure for rate validation, not a minutes forecast.
    """
    current_season = history["Season"].max()
    rounds = history.loc[history["Season"] == current_season].groupby("Round")
    validation = []
    for _, held_out in list(rounds)[-5:]:
        cutoff = held_out["Kickoff"].min()
        if (history["Kickoff"] < cutoff).any():
            validation.append((held_out, cutoff))
    parameters = {event: (900, 180) for event in EVENT_COLUMNS}
    best_errors = dict.fromkeys(EVENT_COLUMNS, float("inf"))
    if not validation:
        return parameters

    for shrinkage in (450, 900, 1800, 3600):
        for half_life in (90, 180, 365):
            errors = dict.fromkeys(EVENT_COLUMNS, 0.0)
            for held_out, cutoff in validation:
                rates = estimate_rates(history, held_out, cutoff, shrinkage, half_life)
                for event in EVENT_COLUMNS:
                    predicted = (rates[event] * held_out["Minutes"] / 90).clip(
                        lower=1e-12
                    )
                    # The omitted log-factorial is constant across candidates.
                    errors[event] += float(
                        (predicted - held_out[event] * np.log(predicted)).sum()
                    )
            for event in EVENT_COLUMNS:
                if errors[event] < best_errors[event]:
                    best_errors[event] = errors[event]
                    parameters[event] = (shrinkage, half_life)
    return parameters


def gw10_rules(
    projections: pd.DataFrame,
    *,
    bootstrap: dict | None = None,
    history: pd.DataFrame | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Add E[outside-box SOT] + 5 E[outside-box goals] to ordinary xPts.

    A goal is also on target, so its extra value is six points. Counts, rather
    than probabilities of at least one event, allow repeated scoring. XLTHM
    xMins already incorporates availability; rates scale linearly with it.
    Fixture difficulty is represented in base xPts, but these extra event
    rates use only player history, position and projected minutes.
    """
    http = session or requests.Session()
    if bootstrap is None:
        response = http.get(BOOTSTRAP_URL, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()
    deadline = pd.Timestamp(
        next(event for event in bootstrap["events"] if int(event["id"]) == 10)[
            "deadline_time"
        ]
    )
    if history is None:
        history = fetch_player_history(10, cutoff=deadline, session=http)

    codes = {int(player["id"]): int(player["code"]) for player in bootstrap["elements"]}
    players = projections[["ID", "Position"]].copy()
    players["Code"] = players["ID"].astype(int).map(codes)
    if players["Code"].isna().any():
        raise ValueError("Some projected players have no Challenge player code.")

    cutoff = min(history.attrs.get("cutoff", deadline), deadline)
    current_season = f"{SEASON_ROOT.name[:4]}/{int(SEASON_ROOT.name[:4]) + 1}"
    history = history.loc[
        (history["Kickoff"] < cutoff)
        & ((history["Season"] != current_season) | (history["Round"] < 10))
    ].copy()
    if history.empty:
        raise ValueError("No FotMob history precedes the GW10 cutoff.")
    parameters = select_rate_parameters(history)
    rates = pd.DataFrame(index=players.index)
    for event, (shrinkage, half_life) in parameters.items():
        rates[event] = estimate_rates(history, players, cutoff, shrinkage, half_life)[
            event
        ]
        print(
            f"GW10 FotMob {event}: {shrinkage} prior minutes, "
            f"{half_life}-day half-life."
        )
    missing_history = ~players["Code"].isin(history["Code"])
    if missing_history.any():
        print(
            f"Using position priors for {int(missing_history.sum())} players without history."
        )

    adjusted = projections.copy()
    exposure = adjusted["xMins"] / 90
    adjusted["Base_Predicted_Points"] = adjusted["Predicted_Points"]
    adjusted["Projected_Outside_Box_Goals"] = rates["Outside_Goals"] * exposure
    adjusted["Projected_Outside_Box_SOT"] = (
        rates["Outside_Saved_Shots"] + rates["Outside_Goals"]
    ) * exposure
    adjusted["GW10_Extra_xPts"] = (
        adjusted["Projected_Outside_Box_SOT"]
        + 5 * adjusted["Projected_Outside_Box_Goals"]
    )
    adjusted["Predicted_Points"] = (
        adjusted["Base_Predicted_Points"] + adjusted["GW10_Extra_xPts"]
    ).round(2)
    return adjusted
