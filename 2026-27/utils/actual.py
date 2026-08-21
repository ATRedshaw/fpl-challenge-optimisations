"""Build and persist the actual result of each submitted predicted lineup."""

from __future__ import annotations

import json
from pathlib import Path

import requests
import yaml

from utils.data import PROJECT_ROOT, ensure_season_in_registry


BASE_URL = "https://fplchallenge.premierleague.com/api"


def fetch_entry_picks(gameweek: int, entry_id: int) -> dict:
    response = requests.get(
        f"{BASE_URL}/entry/{entry_id}/event/{gameweek}/picks/", timeout=60
    )
    response.raise_for_status()
    return response.json()


def build_actual_outcome_for_gw(
    predicted_players: dict,
    live_data: dict,
    entry_history: dict,
) -> dict:
    live_points_by_id = {
        int(element["id"]): element["stats"]["total_points"]
        for element in live_data["elements"]
    }

    outcome_players: dict[str, list] = {}
    for position, players in predicted_players.items():
        outcome_players[position] = []
        for player in players:
            player_id = int(player["ID"])
            is_captain = player.get("Captain", False)
            outcome_players[position].append(
                {
                    "ID": player_id,
                    "Name": player["Name"],
                    "Team": player["Team"],
                    "Cost": player["Cost"],
                    "Points": live_points_by_id.get(player_id, 0)
                    * (2 if is_captain else 1),
                    "Captain": is_captain,
                }
            )

    total_cost = sum(
        player["Cost"]
        for players in outcome_players.values()
        for player in players
    )
    total_points = sum(
        player["Points"]
        for players in outcome_players.values()
        for player in players
    )
    return {
        "Players": outcome_players,
        "Ranks": {
            "rank": entry_history.get("rank"),
            "overall_rank": entry_history.get("overall_rank"),
            "percentile_rank": entry_history.get("percentile_rank"),
        },
        "Total_Cost": round(total_cost, 1),
        "Total_Points": round(total_points, 2),
    }


def save_actual_outcome(
    season: str,
    gameweek: int,
    outcome: dict,
    output_path: Path,
    total_players: int | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_gameweeks = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )
    existing_total = all_gameweeks.pop("total_players", None)
    all_gameweeks[str(gameweek)] = outcome
    all_gameweeks = dict(
        sorted(all_gameweeks.items(), key=lambda item: int(item[0]))
    )
    resolved_total = total_players if total_players is not None else existing_total
    if resolved_total is not None:
        all_gameweeks["total_players"] = resolved_total

    serialised = json.dumps(all_gameweeks, indent=4, ensure_ascii=False) + "\n"
    output_path.write_text(serialised, encoding="utf-8")
    print(
        f"Actual outcome for GW{gameweek} saved to "
        f"{output_path.relative_to(PROJECT_ROOT)}"
    )

    site_path = PROJECT_ROOT / "site" / "data" / season / "actual_outcome.json"
    site_path.parent.mkdir(parents=True, exist_ok=True)
    site_path.write_text(serialised, encoding="utf-8")
    print(
        f"Actual outcome for GW{gameweek} mirrored to "
        f"{site_path.relative_to(PROJECT_ROOT)}"
    )
    ensure_season_in_registry(season)


def process_actual_outcome(
    season: str,
    gameweek: int,
    live_data: dict,
    bootstrap: dict,
    is_last_gameweek: bool = False,
) -> None:
    season_root = PROJECT_ROOT / season
    predicted_path = season_root / "data" / "lineups" / "predicted_optimal.json"
    if not predicted_path.exists():
        print(f"No predicted lineups file; skipping actual outcome for GW{gameweek}.")
        return

    predicted_all = json.loads(predicted_path.read_text(encoding="utf-8"))
    gameweek_key = str(gameweek)
    if gameweek_key not in predicted_all:
        print(f"No predicted lineup found for GW{gameweek}; skipping outcome.")
        return

    with (season_root / "data" / "config.yaml").open(
        encoding="utf-8"
    ) as config_file:
        config = yaml.safe_load(config_file) or {}
    entry_id = config.get("team_id")
    if entry_id is None:
        print(f"No team_id configured; skipping actual outcome for GW{gameweek}.")
        return

    print(f"Fetching entry picks for GW{gameweek}...")
    picks_data = fetch_entry_picks(gameweek, int(entry_id))
    outcome = build_actual_outcome_for_gw(
        predicted_all[gameweek_key]["Players"],
        live_data,
        picks_data.get("entry_history", {}),
    )
    total_players = bootstrap.get("total_players") if is_last_gameweek else None
    save_actual_outcome(
        season,
        gameweek,
        outcome,
        season_root / "data" / "lineups" / "actual_outcome.json",
        total_players=total_players,
    )
