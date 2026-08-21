"""Persistence helpers for season data and the static frontend mirror."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEASONS_REGISTRY = PROJECT_ROOT / "site" / "data" / "seasons.json"


def ensure_season_in_registry(season: str) -> None:
    SEASONS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    if SEASONS_REGISTRY.exists():
        raw = SEASONS_REGISTRY.read_text(encoding="utf-8").strip()
        seasons: list[str] = json.loads(raw) if raw else []
    else:
        seasons = []

    if season not in seasons:
        seasons.append(season)
        seasons.sort()
        SEASONS_REGISTRY.write_text(
            json.dumps(seasons, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Season {season} added to {SEASONS_REGISTRY.relative_to(PROJECT_ROOT)}")


def save_projections(df, season: str, gameweek: int) -> None:
    projections_path = (
        PROJECT_ROOT / season / "data" / "projections" / f"gw{gameweek}.csv"
    )
    projections_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(projections_path, index=False)
    print(f"Projections saved to {projections_path.relative_to(PROJECT_ROOT)}")


def _convert_player(player: dict) -> dict:
    result = {}
    for key, value in player.items():
        if isinstance(value, np.integer):
            result[key] = int(value)
        elif isinstance(value, np.floating):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def save_optimal_prediction(
    lineup_prediction, season: str, gameweek: int, *, confirm: bool = True
) -> bool:
    if confirm:
        proceed = input(
            f"Save optimal prediction to {season}/data/lineups/"
            "predicted_optimal.json? (y/n): "
        )
        if proceed.lower() != "y":
            return False

    optimal_path = (
        PROJECT_ROOT / season / "data" / "lineups" / "predicted_optimal.json"
    )
    optimal_path.parent.mkdir(parents=True, exist_ok=True)
    if optimal_path.exists():
        all_gameweeks = json.loads(optimal_path.read_text(encoding="utf-8"))
    else:
        all_gameweeks = {}

    converted = {
        position: [_convert_player(player) for player in players]
        for position, players in lineup_prediction.items()
    }
    for players in converted.values():
        for player in players:
            if player["Captain"]:
                player["Predicted_Points"] *= 2

    total_cost = sum(
        player["Cost"] for players in converted.values() for player in players
    )
    total_points = sum(
        player["Predicted_Points"]
        for players in converted.values()
        for player in players
    )
    all_gameweeks[str(gameweek)] = {
        "Players": converted,
        "Total_Cost": round(total_cost, 1),
        "Total_Points": round(total_points, 2),
    }
    all_gameweeks = dict(
        sorted(all_gameweeks.items(), key=lambda item: int(item[0]))
    )

    serialised = json.dumps(all_gameweeks, indent=4, ensure_ascii=False) + "\n"
    optimal_path.write_text(serialised, encoding="utf-8")
    print(f"Optimal prediction saved to {optimal_path.relative_to(PROJECT_ROOT)}")

    site_path = PROJECT_ROOT / "site" / "data" / season / "predicted_optimal.json"
    site_path.parent.mkdir(parents=True, exist_ok=True)
    site_path.write_text(serialised, encoding="utf-8")
    print(f"Optimal prediction mirrored to {site_path.relative_to(PROJECT_ROOT)}")
    ensure_season_in_registry(season)
    return True
