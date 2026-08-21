"""Fetch and persist solver constraints from FPL Challenge bootstrap data."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests
import yaml


BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
SEASON_ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS_PATH = SEASON_ROOT / "data" / "constraints.yaml"


def fetch_bootstrap(
    api_url: str = BOOTSTRAP_URL,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    http = session or requests.Session()
    response = http.get(api_url, timeout=60)
    response.raise_for_status()
    return response.json()


def _merged_element_types(bootstrap: Mapping[str, Any], event: Mapping[str, Any]):
    """Merge event overrides onto defaults, retaining omitted positions."""
    by_id = {
        int(element_type["id"]): dict(element_type)
        for element_type in bootstrap.get("element_types", [])
    }
    override_types = event.get("overrides", {}).get("element_types", []) or []
    for override in override_types:
        element_type_id = int(override["id"])
        by_id[element_type_id] = {
            **by_id.get(element_type_id, {}),
            **override,
        }
    return [by_id[element_type_id] for element_type_id in sorted(by_id)]


def build_gameweek_constraints(
    bootstrap: Mapping[str, Any], gameweek: int
) -> dict[str, Any]:
    """Build the solver constraint block for one gameweek."""
    event = next(
        (
            candidate
            for candidate in bootstrap.get("events", [])
            if int(candidate.get("id", -1)) == int(gameweek)
        ),
        None,
    )
    if event is None:
        raise ValueError(f"GW{gameweek} was not found in bootstrap events.")

    rules = event.get("overrides", {}).get("rules", {}) or {}
    required_rules = {
        "squad_squadplay": "total players",
        "squad_team_limit": "maximum players per team",
    }
    missing_rules = [
        field for field in required_rules if rules.get(field) is None
    ]
    if missing_rules:
        raise ValueError(
            f"GW{gameweek} is missing required bootstrap rules: "
            + ", ".join(missing_rules)
        )

    position_constraints: dict[str, dict[str, int]] = {}
    for element_type in _merged_element_types(bootstrap, event):
        position = element_type.get("singular_name")
        min_count = element_type.get("squad_min_play")
        max_count = element_type.get("squad_max_play")
        if not position or min_count is None or max_count is None:
            raise ValueError(
                f"GW{gameweek} has incomplete position constraints for "
                f"element type {element_type.get('id')}."
            )
        position_constraints[position] = {
            "min_count": int(min_count),
            "max_count": int(max_count),
        }

    constraints: dict[str, Any] = {
        # squad_squadplay is the active team solved by this project; no bench.
        "total_players": int(rules["squad_squadplay"]),
        "max_per_team": int(rules["squad_team_limit"]),
        "position_constraints": position_constraints,
    }
    if rules.get("squad_total_spend") is not None:
        constraints["budget_max"] = round(
            float(rules["squad_total_spend"]) / 10,
            1,
        )
    return constraints


def write_gameweek_constraints(
    gameweek: int,
    constraints: Mapping[str, Any],
    constraints_path: Path = CONSTRAINTS_PATH,
) -> None:
    """Update one GW entry while preserving any unrelated/manual entries."""
    if constraints_path.exists():
        with constraints_path.open(encoding="utf-8") as constraints_file:
            all_constraints = yaml.safe_load(constraints_file) or {}
    else:
        all_constraints = {}

    gameweek_key = f"GW{int(gameweek)}"
    existing_gameweek = all_constraints.get(gameweek_key, {}) or {}
    existing_gameweek.pop("captain_count", None)
    all_constraints[gameweek_key] = {
        **existing_gameweek,
        **dict(constraints),
    }
    def gameweek_sort_key(item):
        key = str(item[0])
        number = key.removeprefix("GW")
        if key.startswith("GW") and number.isdigit():
            return (0, int(number))
        return (1, key)

    all_constraints = dict(sorted(all_constraints.items(), key=gameweek_sort_key))

    constraints_path.parent.mkdir(parents=True, exist_ok=True)
    with constraints_path.open("w", encoding="utf-8") as constraints_file:
        yaml.safe_dump(
            all_constraints,
            constraints_file,
            sort_keys=False,
            allow_unicode=True,
        )
    print(
        f"GW{gameweek} constraints written to "
        f"{constraints_path.relative_to(SEASON_ROOT.parent)}"
    )


def update_constraints(
    gameweek: int,
    api_url: str = BOOTSTRAP_URL,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch, derive, write, and return one gameweek's constraints."""
    constraints = build_gameweek_constraints(
        fetch_bootstrap(api_url=api_url, session=session), gameweek
    )
    write_gameweek_constraints(gameweek, constraints)
    return constraints
