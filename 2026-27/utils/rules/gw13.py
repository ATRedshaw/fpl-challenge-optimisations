"""Projection adjustment for GW13: Dribbling: 20."""

from __future__ import annotations

import time

import pandas as pd
import requests
from scipy.stats import nbinom, poisson

BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
SUMMARY_URL = "https://fplchallenge.premierleague.com/api/element-summary/{}/"
POSITION_MAP = {1: "Goalkeeper", 2: "Defender", 3: "Midfielder", 4: "Forward"}


def fetch_player_history(
    bootstrap: dict,
    cutoff: pd.Timestamp,
    session: requests.Session,
) -> pd.DataFrame:
    """Fetch completed-dribble counts for all players with season minutes.

    Challenge summaries use the same IDs as the projections. All positions'
    players contribute to the priors, including appearances with zero dribbles.
    """
    elements = [player for player in bootstrap["elements"] if player["minutes"] > 0]
    rows = []
    print(
        f"GW13: fetching Challenge dribble history for {len(elements)} players...",
        flush=True,
    )
    for number, player in enumerate(elements, 1):
        response = session.get(SUMMARY_URL.format(player["id"]), timeout=60)
        response.raise_for_status()
        for match in response.json()["history"]:
            if (
                match["team_h_score"] is None
                or match["team_a_score"] is None
                or match["minutes"] <= 0
                or int(match["round"]) >= 13
                or pd.Timestamp(match["kickoff_time"]) >= cutoff
            ):
                continue
            # Missing coverage must not be interpreted as zero completed dribbles.
            if match.get("dribbles") is None:
                raise ValueError(
                    f"Missing Challenge dribbles for player {player['id']}, "
                    f"fixture {match['fixture']}."
                )
            rows.append(
                {
                    "ID": int(player["id"]),
                    "Position": POSITION_MAP[player["element_type"]],
                    "Round": int(match["round"]),
                    "Kickoff": match["kickoff_time"],
                    "Minutes": match["minutes"],
                    "Dribbles": match["dribbles"],
                }
            )
        if number % 50 == 0 or number == len(elements):
            print(f"  Fetched {number}/{len(elements)} players.", flush=True)
        if number < len(elements):
            time.sleep(0.2)
    return pd.DataFrame(
        rows, columns=["ID", "Position", "Round", "Kickoff", "Minutes", "Dribbles"]
    )


def estimate_rates(
    history: pd.DataFrame,
    players: pd.DataFrame,
    cutoff: pd.Timestamp,
    shrinkage_minutes: int,
    half_life_days: int,
) -> pd.Series:
    """Shrink recency-weighted completed dribbles per 90 to position rates."""
    past = history.loc[history["Kickoff"] < cutoff].copy()
    if past.empty:
        raise ValueError("No dribble history precedes the rate-estimation cutoff.")
    age_days = (cutoff - past["Kickoff"]).dt.total_seconds() / 86400
    columns = ["Minutes", "Dribbles"]
    past[columns] = past[columns].mul(0.5 ** (age_days / half_life_days), axis=0)
    totals = past.groupby("ID")[columns].sum()
    positions = past.groupby("Position")[columns].sum()
    position_rates = 90 * positions["Dribbles"] / positions["Minutes"]
    prior = (
        players["Position"]
        .map(position_rates)
        .fillna(90 * past["Dribbles"].sum() / past["Minutes"].sum())
    )
    minutes = players["ID"].map(totals["Minutes"]).fillna(0)
    dribbles = players["ID"].map(totals["Dribbles"]).fillna(0)
    return (90 * dribbles + shrinkage_minutes * prior) / (minutes + shrinkage_minutes)


def count_distribution(mean: pd.Series, dispersion: float):
    """Use variance = mean + dispersion * mean**2; zero gives Poisson."""
    if dispersion == 0:
        return poisson(mean)
    return nbinom(1 / dispersion, 1 / (1 + dispersion * mean))


def select_rate_parameters(history: pd.DataFrame) -> tuple[int, int, float]:
    """Tune shrinkage, recency and dispersion on five rolling GW holdouts.

    Count log scores test the whole distribution, including the three-dribble
    tail. Priors use only earlier matches. Actual held-out minutes measure
    exposure when validating event rates, rather than forecasting playing time.
    """
    validation = []
    for _, held_out in list(history.groupby("Round"))[-5:]:
        cutoff = held_out["Kickoff"].min()
        if (history["Kickoff"] < cutoff).any():
            validation.append((held_out, cutoff))
    best_parameters = (450, 90, 0.0)
    if not validation:
        return best_parameters

    best_error = float("inf")
    dispersions = (0.0, 0.25, 0.5, 1.0)
    for shrinkage in (180, 450, 900, 1800):
        for half_life in (30, 90, 180):
            errors = dict.fromkeys(dispersions, 0.0)
            for held_out, cutoff in validation:
                rates = estimate_rates(history, held_out, cutoff, shrinkage, half_life)
                predicted = (rates * held_out["Minutes"] / 90).clip(lower=1e-12)
                for dispersion in dispersions:
                    distribution = count_distribution(predicted, dispersion)
                    errors[dispersion] -= float(
                        distribution.logpmf(held_out["Dribbles"]).sum()
                    )
            for dispersion, error in errors.items():
                if error < best_error:
                    best_error = error
                    best_parameters = (shrinkage, half_life, dispersion)
    return best_parameters


def gw13_rules(
    projections: pd.DataFrame,
    *,
    bootstrap: dict | None = None,
    history: pd.DataFrame | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Add E[completed dribbles] + 5 P(completed dribbles >= 3).

    The five-point award is one-off, not repeated at multiples of three.
    XLTHM xMins already includes availability. For the nonlinear threshold,
    condition on appearing, then multiply by appearance probability once.
    Playing time within an appearance is approximated by its conditional mean;
    extra dribble rates do not adjust for the upcoming opponent.
    """
    adjusted = projections.copy()
    appearance = adjusted["Appearance_Probability"]
    if (
        not appearance.between(0, 1).all()
        or ((appearance == 0) & (adjusted["xMins"] > 0)).any()
    ):
        raise ValueError(
            "GW13 requires consistent single-fixture appearance probabilities."
        )

    http = session or requests.Session()
    if bootstrap is None:
        response = http.get(BOOTSTRAP_URL, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()
    deadline = pd.Timestamp(
        next(event for event in bootstrap["events"] if int(event["id"]) == 13)[
            "deadline_time"
        ]
    )
    cutoff = min(pd.Timestamp.now(tz="UTC"), deadline)
    if history is None:
        history = fetch_player_history(bootstrap, cutoff, http)
    history = history.copy()
    history["Kickoff"] = pd.to_datetime(history["Kickoff"], utc=True)
    history = history.loc[
        (history["Round"] < 13)
        & (history["Kickoff"] < cutoff)
        & (history["Minutes"] > 0)
    ].copy()
    if history.empty:
        raise ValueError("No completed dribble appearances precede GW13.")
    if (
        history["Dribbles"].isna()
        | (history["Dribbles"] < 0)
        | (history["Dribbles"] % 1 != 0)
    ).any():
        raise ValueError("Challenge dribble history must contain nonnegative counts.")

    shrinkage, half_life, dispersion = select_rate_parameters(history)
    print(
        f"GW13 dribble rates: {shrinkage} prior minutes, {half_life}-day half-life, "
        f"dispersion {dispersion:g}; {len(history)} historical appearances."
    )
    rates = estimate_rates(history, adjusted, cutoff, shrinkage, half_life)
    missing_history = ~adjusted["ID"].isin(history["ID"])
    if missing_history.any():
        print(
            f"Using position priors for {int(missing_history.sum())} players without history."
        )

    adjusted["Base_Predicted_Points"] = adjusted["Predicted_Points"]
    adjusted["Projected_Dribbles"] = rates * adjusted["xMins"] / 90
    conditional_mean = (
        adjusted["Projected_Dribbles"] / appearance.where(appearance > 0)
    ).fillna(0)
    distribution = count_distribution(conditional_mean, dispersion)
    adjusted["Three_Plus_Dribbles_Probability"] = appearance * distribution.sf(2)
    adjusted["GW13_Extra_xPts"] = (
        adjusted["Projected_Dribbles"] + 5 * adjusted["Three_Plus_Dribbles_Probability"]
    )
    adjusted["Predicted_Points"] = (
        adjusted["Base_Predicted_Points"] + adjusted["GW13_Extra_xPts"]
    ).round(2)
    return adjusted
