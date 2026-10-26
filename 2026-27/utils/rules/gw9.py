"""Projection adjustment for GW9: Trick or Treat."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

FOTMOB_URL = "https://www.fotmob.com/api/data"
BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
SEASON_ROOT = Path(__file__).resolve().parents[2]
POSITION_MAP = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
EVENT_COLUMNS = ["Successful_Dribbles", "Failed_Dribbles", "Dispossessed"]


def parse_match_history(payload: dict, season: str) -> list[dict]:
    """Extract counts for players who appeared, retaining stable Opta codes."""
    match = payload["general"]
    if not match["finished"]:
        raise ValueError(f"FotMob match {match['matchId']} is not finished.")

    rows = []
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
        # FotMob omits the dribbling entry when no take-ons were attempted.
        dribbles = stats.get("dribbles_succeeded", {"value": 0, "total": 0})
        if player["isGoalkeeper"]:
            dispossessed = stats.get("dispossessed", {"value": 0})["value"]
            tackles = stats.get("matchstats.headers.tackles", {"value": 0})["value"]
        else:
            dispossessed = stats["dispossessed"]["value"]
            tackles = stats["matchstats.headers.tackles"]["value"]
        successful = dribbles["value"]
        failed = dribbles["total"] - successful
        if min(successful, failed, dispossessed, tackles) < 0:
            raise ValueError(f"Invalid FotMob counts for {player['name']}.")
        rows.append(
            {
                "Match_ID": int(match["matchId"]),
                "Season": season,
                "Round": int(match["matchRound"]),
                "Kickoff": match["matchTimeUTCDate"],
                "Code": int(str(player["optaId"]).removeprefix("p")),
                "Position": POSITION_MAP[player["usualPosition"]],
                "Team_ID": int(player["teamId"]),
                "Minutes": minutes,
                "Successful_Dribbles": successful,
                "Failed_Dribbles": failed,
                "Dispossessed": dispossessed,
                "Tackles_Made": tackles,
            }
        )
    if not rows or len({row["Team_ID"] for row in rows}) != 2:
        raise ValueError(f"Incomplete FotMob player data for match {match['matchId']}.")
    return rows


def fetch_player_history(
    gameweek: int,
    *,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch this season and last season in memory, excluding the target GW."""
    http = session or requests.Session()
    start_year = int(SEASON_ROOT.name.split("-")[0])
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for year in (start_year - 1, start_year):
        season = f"{year}/{year + 1}"
        response = http.get(
            f"{FOTMOB_URL}/leagues", params={"id": 47, "season": season}, timeout=60
        )
        response.raise_for_status()
        league = response.json()
        if league["details"]["selectedSeason"] != season:
            raise ValueError(f"FotMob did not return the requested season {season}.")
        fixtures = league["fixtures"]["allMatches"]
        cutoff = now
        if year == start_year:
            target_kickoffs = [
                pd.Timestamp(fixture["status"]["utcTime"])
                for fixture in fixtures
                if int(fixture["round"]) == gameweek
            ]
            if not target_kickoffs:
                raise ValueError(f"FotMob has no fixtures for GW{gameweek}.")
            cutoff = min(now, min(target_kickoffs))
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


def tackled_share(history: pd.DataFrame) -> float:
    """Estimate the share of failed dribbles ending in an opposition tackle."""
    teams = history.groupby(["Match_ID", "Team_ID"])[
        ["Tackles_Made", "Failed_Dribbles", "Dispossessed"]
    ].sum()
    opposing_tackles = (
        teams["Tackles_Made"].groupby(level="Match_ID").transform("sum")
        - teams["Tackles_Made"]
    )
    failed = teams["Failed_Dribbles"].sum()
    if failed == 0:
        return 0.0
    # Failed take-ons can include overruns; dispossessions alone omit tackles
    # during take-ons. Opposing tackle totals calibrate the missing component.
    return float(((opposing_tackles - teams["Dispossessed"]).sum() / failed).clip(0, 1))


def estimate_rates(
    history: pd.DataFrame,
    players: pd.DataFrame,
    cutoff: pd.Timestamp,
    shrinkage_minutes: int,
    half_life_days: int,
) -> pd.DataFrame:
    """Shrink recency-weighted per-90 counts toward position-level priors."""
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


def select_rate_parameters(history: pd.DataFrame) -> tuple[int, int]:
    """Choose shrinkage and recency using the last five available GW holdouts."""
    current_season = history["Season"].max()
    rounds = history.loc[history["Season"] == current_season].groupby("Round")
    validation = []
    for _, held_out in list(rounds)[-5:]:
        cutoff = held_out["Kickoff"].min()
        past = history.loc[history["Kickoff"] < cutoff]
        if past.empty:
            continue
        share = tackled_share(past)
        actual = (
            3 * held_out["Successful_Dribbles"]
            - held_out["Dispossessed"]
            - share * held_out["Failed_Dribbles"]
        )
        validation.append((held_out, cutoff, share, actual))
    if not validation:
        return 450, 180

    best_error = float("inf")
    best_parameters = (450, 180)
    for shrinkage in (180, 450, 900, 1800):
        for half_life in (90, 180, 365):
            squared_error = 0.0
            for held_out, cutoff, share, actual in validation:
                rates = estimate_rates(history, held_out, cutoff, shrinkage, half_life)
                predicted = (
                    (
                        3 * rates["Successful_Dribbles"]
                        - rates["Dispossessed"]
                        - share * rates["Failed_Dribbles"]
                    )
                    * held_out["Minutes"]
                    / 90
                )
                squared_error += float(((predicted - actual) ** 2).sum())
            if squared_error < best_error:
                best_error = squared_error
                best_parameters = (shrinkage, half_life)
    return best_parameters


def gw9_rules(
    projections: pd.DataFrame,
    *,
    bootstrap: dict | None = None,
    history: pd.DataFrame | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Add 3 x successful dribbles minus estimated times tackled.

    FotMob does not expose Challenge's tackled count directly. Estimate it
    from dispossessions plus failed take-ons, calibrated to opposing tackles.
    XLTHM xMins already includes appearance and availability probabilities.
    """
    http = session or requests.Session()
    if bootstrap is None:
        response = http.get(BOOTSTRAP_URL, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()
    if history is None:
        history = fetch_player_history(9, session=http)

    codes = {int(player["id"]): int(player["code"]) for player in bootstrap["elements"]}
    players = projections[["ID", "Position"]].copy()
    players["Code"] = players["ID"].astype(int).map(codes)
    if players["Code"].isna().any():
        raise ValueError("Some projected players have no Challenge player code.")

    history = history.copy()
    positions = players.set_index("Code")["Position"]
    history["Position"] = history["Code"].map(positions).fillna(history["Position"])
    shrinkage, half_life = select_rate_parameters(history)
    cutoff = history.attrs.get(
        "cutoff", history["Kickoff"].max() + pd.Timedelta(days=1)
    )
    rates = estimate_rates(history, players, cutoff, shrinkage, half_life)
    share = tackled_share(history)
    print(
        f"GW9 FotMob rates: {shrinkage} prior minutes, {half_life}-day half-life; "
        f"{share:.1%} of failed dribbles estimated as tackled."
    )
    missing_history = ~players["Code"].isin(history["Code"])
    if missing_history.any():
        print(
            f"Using position priors for {int(missing_history.sum())} players without history."
        )

    adjusted = projections.copy()
    exposure = adjusted["xMins"] / 90
    adjusted["Base_Predicted_Points"] = adjusted["Predicted_Points"]
    adjusted["Projected_Dribbles"] = rates["Successful_Dribbles"] * exposure
    adjusted["Projected_Failed_Dribbles"] = rates["Failed_Dribbles"] * exposure
    adjusted["Projected_Dispossessions"] = rates["Dispossessed"] * exposure
    adjusted["Projected_Times_Tackled"] = (
        adjusted["Projected_Dispossessions"]
        + share * adjusted["Projected_Failed_Dribbles"]
    )
    adjusted["GW9_Extra_xPts"] = (
        3 * adjusted["Projected_Dribbles"] - adjusted["Projected_Times_Tackled"]
    )
    adjusted["Predicted_Points"] = (
        adjusted["Base_Predicted_Points"] + adjusted["GW9_Extra_xPts"]
    ).round(2)
    return adjusted
