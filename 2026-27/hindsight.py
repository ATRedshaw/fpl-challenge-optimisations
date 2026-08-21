"""Run hindsight-optimal lineups for completed 2026-27 challenges."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml
from utils.actual import process_actual_outcome
from utils.data import PROJECT_ROOT, ensure_season_in_registry
from utils.solver import FPLChallengeOptimiser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


BASE_URL = "https://fplchallenge.premierleague.com/api"
HINDSIGHT_PROJECTION_COLUMNS = ["ID", "Name", "Team", "Position", "Cost"]


def fetch_bootstrap() -> dict:
    response = requests.get(f"{BASE_URL}/bootstrap-static/", timeout=60)
    response.raise_for_status()
    return response.json()


def fetch_live(gameweek: int) -> dict:
    response = requests.get(f"{BASE_URL}/event/{gameweek}/live/", timeout=60)
    response.raise_for_status()
    return response.json()


def get_completed_gameweeks(events: list) -> list[int]:
    return sorted(
        int(event["id"])
        for event in events
        if event.get("finished") and event.get("data_checked")
    )


def build_player_dataframe(
    projections_path: Path, live_data: dict
) -> pd.DataFrame:
    """Combine the saved pre-deadline player snapshot with actual GW points."""
    if not projections_path.exists():
        raise FileNotFoundError(
            f"Saved projections not found: {projections_path}"
        )

    saved_projections = pd.read_csv(projections_path)
    missing_columns = [
        column
        for column in HINDSIGHT_PROJECTION_COLUMNS
        if column not in saved_projections.columns
    ]
    if missing_columns:
        raise ValueError(
            f"{projections_path} is missing required columns: "
            + ", ".join(missing_columns)
        )

    players = saved_projections[HINDSIGHT_PROJECTION_COLUMNS].copy()
    if players.empty:
        raise ValueError(f"No saved projections found in {projections_path}")

    players["ID"] = pd.to_numeric(players["ID"], errors="coerce")
    players["Cost"] = pd.to_numeric(players["Cost"], errors="coerce")
    missing_values = [
        column
        for column in HINDSIGHT_PROJECTION_COLUMNS
        if players[column].isna().any()
    ]
    if missing_values:
        raise ValueError(
            f"{projections_path} contains missing or invalid values in: "
            + ", ".join(missing_values)
        )

    players["ID"] = players["ID"].astype(int)
    duplicated_ids = players.loc[players["ID"].duplicated(), "ID"].tolist()
    if duplicated_ids:
        raise ValueError(
            f"{projections_path} contains duplicate player IDs: "
            + ", ".join(map(str, duplicated_ids))
        )

    live_points_by_id = {
        int(element["id"]): element["stats"]["total_points"]
        for element in live_data["elements"]
    }
    players["Predicted_Points"] = (
        players["ID"].map(live_points_by_id).fillna(0)
    )
    return players.sort_values("ID").reset_index(drop=True)


def _serialise_player(player: dict) -> dict:
    result = {}
    for key, value in player.items():
        output_key = "Points" if key == "Predicted_Points" else key
        if isinstance(value, np.integer):
            result[output_key] = int(value)
        elif isinstance(value, np.floating):
            result[output_key] = float(value)
        else:
            result[output_key] = value
    return result


def save_actual_optimal(
    lineup: defaultdict,
    season: str,
    gameweek: int,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_gameweeks = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )
    converted = {
        position: [_serialise_player(player) for player in players]
        for position, players in lineup.items()
    }
    for players in converted.values():
        for player in players:
            if player["Captain"]:
                player["Points"] *= 2

    all_gameweeks[str(gameweek)] = {
        "Players": converted,
        "Total_Cost": round(
            sum(
                player["Cost"]
                for players in converted.values()
                for player in players
            ),
            1,
        ),
        "Total_Points": round(
            sum(
                player["Points"]
                for players in converted.values()
                for player in players
            ),
            2,
        ),
    }
    all_gameweeks = dict(
        sorted(all_gameweeks.items(), key=lambda item: int(item[0]))
    )
    serialised = json.dumps(all_gameweeks, indent=4, ensure_ascii=False) + "\n"
    output_path.write_text(serialised, encoding="utf-8")
    print(
        f"Actual optimal for GW{gameweek} saved to "
        f"{output_path.relative_to(PROJECT_ROOT)}"
    )

    site_path = PROJECT_ROOT / "site" / "data" / season / "actual_optimal.json"
    site_path.parent.mkdir(parents=True, exist_ok=True)
    site_path.write_text(serialised, encoding="utf-8")
    print(
        f"Actual optimal for GW{gameweek} mirrored to "
        f"{site_path.relative_to(PROJECT_ROOT)}"
    )
    ensure_season_in_registry(season)


def run_hindsight(season_root: Path | None = None) -> None:
    """Process every completed, not-yet-recorded gameweek for a season."""
    season_root = (
        Path(season_root).resolve()
        if season_root is not None
        else Path(__file__).resolve().parent
    )
    season = season_root.name
    with (season_root / "data" / "constraints.yaml").open(
        encoding="utf-8"
    ) as constraints_file:
        all_constraints = yaml.safe_load(constraints_file) or {}

    output_path = season_root / "data" / "lineups" / "actual_optimal.json"
    outcome_path = season_root / "data" / "lineups" / "actual_outcome.json"
    existing_data = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )
    existing_outcomes = (
        json.loads(outcome_path.read_text(encoding="utf-8"))
        if outcome_path.exists()
        else {}
    )
    already_processed = {
        int(key) for key in existing_data if key.lstrip("-").isdigit()
    }
    outcome_processed = {
        int(key) for key in existing_outcomes if key.lstrip("-").isdigit()
    }

    print("Fetching bootstrap data...")
    bootstrap = fetch_bootstrap()
    completed_gameweeks = get_completed_gameweeks(bootstrap["events"])
    print(f"Completed gameweeks: {completed_gameweeks}")

    for gameweek in completed_gameweeks:
        optimal_done = gameweek in already_processed
        outcome_done = gameweek in outcome_processed
        if optimal_done and outcome_done:
            print(f"\nGW{gameweek} already processed; skipping.")
            continue

        print(f"\n{'=' * 50}\nProcessing GW{gameweek}...\n{'=' * 50}")
        live_data = fetch_live(gameweek)
        if not optimal_done:
            constraints = all_constraints.get(f"GW{gameweek}")
            if not constraints:
                print(f"No constraints found for GW{gameweek}; skipping solver.")
            else:
                projections_path = (
                    season_root
                    / "data"
                    / "projections"
                    / f"gw{gameweek}.csv"
                )
                if not projections_path.exists():
                    print(
                        f"No saved projections found for GW{gameweek}; "
                        "skipping solver."
                    )
                else:
                    projections = build_player_dataframe(
                        projections_path, live_data
                    )
                    solver = FPLChallengeOptimiser(gameweek, projections)
                    solver.setup_problem(
                        f"fpl-hindsight-{season.replace('-', '')}-gw{gameweek}"
                    )
                    solver.total_players_constraint(
                        constraints["total_players"]
                    )
                    solver.position_count_constraints(
                        constraints["position_constraints"]
                    )
                    solver.max_players_from_same_team_constraint(
                        constraints["max_per_team"]
                    )
                    if constraints.get("budget_max") is not None:
                        solver.budget_constraint(
                            constraints["budget_max"],
                            constraints.get("budget_min", 0),
                        )
                    solver.solve()
                    solver.print_players_by_position()
                    save_actual_optimal(
                        solver.selected_players, season, gameweek, output_path
                    )

        if not outcome_done:
            process_actual_outcome(
                season,
                gameweek,
                live_data,
                bootstrap,
                is_last_gameweek=(gameweek == completed_gameweeks[-1]),
            )

    print("\nHindsight optimisation complete.")


if __name__ == "__main__":
    run_hindsight()
