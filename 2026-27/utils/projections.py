"""Build solver-ready projections from the XLTHM xPts API."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import requests

XLTHM_PLAYERS_URL = "https://api.xlthm.atredshaw.com/api/players"
CHALLENGE_BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

POSITION_MAP = {
    "GK": "Goalkeeper",
    "DEF": "Defender",
    "MID": "Midfielder",
    "FWD": "Forward",
}
ELEMENT_TYPE_MAP = {
    1: "Goalkeeper",
    2: "Defender",
    3: "Midfielder",
    4: "Forward",
}

# The first nine fields preserve the solver-facing table used in prior seasons.
# Component counts, probabilities and xPts are kept separate so challenge rules
# can use the model output that matches their scoring mechanic.
PROJECTION_COLUMNS = [
    "ID",
    "Name",
    "Team",
    "Region",
    "Position",
    "Cost",
    "Predicted_Points",
    "xMins",
    "Opponent",
    "Status",
    "Availability_Probability",
    "Projected_Goals",
    "Projected_Assists",
    "Projected_Defcons",
    "Projected_BPS",
    "Saves",
    "Bonus",
    "Appearance_Probability",
    "Start_Probability",
    "Sixty_Plus_Probability",
    "Goal_Probability",
    "Assist_Probability",
    "Clean_Sheet",
    "Defcon",
    "Appearance_xPts",
    "Goal_xPts",
    "Assist_xPts",
    "Clean_Sheet_xPts",
    "Save_xPts",
    "Defcon_xPts",
    "Negative_Points_Probability",
    "Zero_Points_Probability",
    "Two_Plus_Points_Probability",
    "Five_Plus_Points_Probability",
    "Ten_Plus_Points_Probability",
    "P10",
    "P25",
    "P50",
    "P75",
    "P90",
]

NUMERIC_COLUMNS = [
    column
    for column in PROJECTION_COLUMNS
    if column not in {"ID", "Name", "Team", "Region", "Position", "Opponent", "Status"}
]


def _get_json(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Any:
    response = session.get(url, params=params, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def _load_api_key(api_key: str | None, env_path: Path) -> str:
    key = api_key or os.environ.get("XLTHM_API_KEY")
    if not key and env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if separator and name.strip() == "XLTHM_API_KEY":
                key = value.strip().strip('"').strip("'")
                break

    if not key:
        raise RuntimeError(
            "XLTHM_API_KEY must be set in the environment or the project .env file."
        )
    return key


def _normalise_region(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-1"
    return str(value)


def _sum_fixture_values(
    fixtures: Sequence[Mapping[str, Any]],
    section: str,
    field: str,
) -> float | None:
    if not fixtures:
        return 0.0

    values = []
    for fixture in fixtures:
        section_values = fixture.get(section)
        if not isinstance(section_values, Mapping):
            return None
        value = section_values.get(field)
        if value is None:
            return None
        values.append(float(value))
    return sum(values)


def _opponent_names(
    fixtures: Sequence[Mapping[str, Any]],
    team_name_by_short_name: Mapping[str, str],
) -> str:
    names = []
    for fixture in fixtures:
        short_name = fixture.get("opponent")
        name = team_name_by_short_name.get(str(short_name))
        if name is None:
            name = fixture.get("opponent_name") or short_name
        if name is not None:
            names.append(str(name))
    return " / ".join(names)


def build_projection_dataframe(
    players: Sequence[Mapping[str, Any]],
    bootstrap: Mapping[str, Any],
    gameweek: int,
) -> pd.DataFrame:
    """Transform XLTHM and FPL Challenge payloads into the projection table."""
    if not isinstance(players, Sequence) or isinstance(players, (str, bytes)):
        raise TypeError("XLTHM players response must be a list.")
    if not isinstance(bootstrap, Mapping):
        raise TypeError("FPL Challenge bootstrap response must be an object.")

    elements = bootstrap.get("elements", [])
    teams = bootstrap.get("teams", [])
    element_by_code = {
        int(element["code"]): element
        for element in elements
        if element.get("code") is not None
    }
    team_name_by_id = {int(team["id"]): team["name"] for team in teams}
    team_name_by_short_name = {
        str(team["short_name"]): str(team["name"]) for team in teams
    }

    rows: list[dict[str, Any]] = []
    for player in players:
        player_code = player.get("code")
        element = (
            element_by_code.get(int(player_code)) if player_code is not None else None
        )
        # Standard FPL and FPL Challenge allocate numeric IDs independently.
        # The stable player code is the only safe key across the two feeds.
        if element is None:
            continue

        gameweek_projection = next(
            (
                projection
                for projection in player.get("future_points", [])
                if int(projection.get("gameweek", -1)) == gameweek
            ),
            None,
        )
        if gameweek_projection is None:
            continue

        fixtures = gameweek_projection.get("fixture_projections", [])
        if not isinstance(fixtures, Sequence) or isinstance(fixtures, (str, bytes)):
            raise TypeError(
                f"XLTHM fixture projections are invalid for player code {player_code}."
            )

        team_id = int(element["team"])
        team_name = team_name_by_id.get(team_id, player.get("team_name", "Unknown"))
        price = (
            element["now_cost"] / 10
            if element.get("now_cost") is not None
            else player.get("price")
        )

        challenge_position = ELEMENT_TYPE_MAP.get(element.get("element_type"))
        xlthm_position = POSITION_MAP.get(
            player.get("position"), player.get("position")
        )
        if (
            challenge_position is not None
            and xlthm_position is not None
            and challenge_position != xlthm_position
        ):
            raise ValueError(
                "Position mismatch for stable player code "
                f"{player_code}: XLTHM has {xlthm_position}, "
                f"FPL Challenge has {challenge_position}."
            )

        outcome_probabilities = gameweek_projection.get("outcome_probabilities", {})
        percentiles = outcome_probabilities.get("percentiles", {})
        rows.append(
            {
                "ID": int(element["id"]),
                "Name": element.get("web_name", player.get("name")),
                "Team": team_name,
                "Region": _normalise_region(element.get("region")),
                "Position": challenge_position or xlthm_position,
                "Cost": price,
                "Predicted_Points": gameweek_projection.get("xpts"),
                "xMins": gameweek_projection.get("xmins"),
                "Opponent": _opponent_names(fixtures, team_name_by_short_name),
                "Status": player.get("status"),
                "Availability_Probability": player.get("availability_probability"),
                "Projected_Goals": _sum_fixture_values(
                    fixtures, "expected_actions", "goals"
                ),
                "Projected_Assists": _sum_fixture_values(
                    fixtures, "expected_actions", "assists"
                ),
                "Projected_Defcons": _sum_fixture_values(
                    fixtures, "expected_actions", "defensive_contributions"
                ),
                "Projected_BPS": _sum_fixture_values(
                    fixtures, "expected_actions", "bps"
                ),
                "Saves": _sum_fixture_values(fixtures, "expected_actions", "saves"),
                "Bonus": _sum_fixture_values(fixtures, "expected_actions", "bonus"),
                "Appearance_Probability": _sum_fixture_values(
                    fixtures, "action_probabilities", "appearance"
                ),
                "Start_Probability": _sum_fixture_values(
                    fixtures, "action_probabilities", "start"
                ),
                "Sixty_Plus_Probability": _sum_fixture_values(
                    fixtures, "action_probabilities", "sixty_plus"
                ),
                "Goal_Probability": _sum_fixture_values(
                    fixtures, "action_probabilities", "goal"
                ),
                "Assist_Probability": _sum_fixture_values(
                    fixtures, "action_probabilities", "assist"
                ),
                "Clean_Sheet": _sum_fixture_values(
                    fixtures, "action_probabilities", "clean_sheet"
                ),
                "Defcon": _sum_fixture_values(
                    fixtures,
                    "action_probabilities",
                    "defensive_contribution_points",
                ),
                "Appearance_xPts": _sum_fixture_values(
                    fixtures, "xpts_breakdown", "appearance"
                ),
                "Goal_xPts": _sum_fixture_values(fixtures, "xpts_breakdown", "goals"),
                "Assist_xPts": _sum_fixture_values(
                    fixtures, "xpts_breakdown", "assists"
                ),
                "Clean_Sheet_xPts": _sum_fixture_values(
                    fixtures, "xpts_breakdown", "clean_sheet"
                ),
                "Save_xPts": _sum_fixture_values(fixtures, "xpts_breakdown", "saves"),
                "Defcon_xPts": _sum_fixture_values(
                    fixtures, "xpts_breakdown", "defensive_contributions"
                ),
                "Negative_Points_Probability": outcome_probabilities.get(
                    "negative_points"
                ),
                "Zero_Points_Probability": outcome_probabilities.get("zero_points"),
                "Two_Plus_Points_Probability": outcome_probabilities.get(
                    "two_plus_points"
                ),
                "Five_Plus_Points_Probability": outcome_probabilities.get(
                    "five_plus_points"
                ),
                "Ten_Plus_Points_Probability": outcome_probabilities.get(
                    "ten_plus_points"
                ),
                "P10": percentiles.get("p10"),
                "P25": percentiles.get("p25"),
                "P50": percentiles.get("p50"),
                "P75": percentiles.get("p75"),
                "P90": percentiles.get("p90"),
            }
        )

    projections = pd.DataFrame(rows, columns=PROJECTION_COLUMNS)
    if projections.empty:
        raise ValueError(f"No XLTHM projections found for GW{gameweek}.")

    duplicated_ids = projections.loc[projections["ID"].duplicated(), "ID"].tolist()
    if duplicated_ids:
        raise ValueError(
            "Multiple XLTHM players mapped to the same Challenge ID: "
            + ", ".join(map(str, duplicated_ids))
        )

    projections[NUMERIC_COLUMNS] = projections[NUMERIC_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    )
    required = ["ID", "Name", "Team", "Position", *NUMERIC_COLUMNS]
    missing_values = [column for column in required if projections[column].isna().any()]
    if missing_values:
        raise ValueError(
            "Projection rows contain missing required values: "
            + ", ".join(missing_values)
        )

    projections["Predicted_Points"] = projections["Predicted_Points"].round(2)
    return projections.sort_values("ID").reset_index(drop=True)


def generate_projections(
    gameweek: int,
    *,
    api_key: str | None = None,
    players_url: str = XLTHM_PLAYERS_URL,
    bootstrap_url: str = CHALLENGE_BOOTSTRAP_URL,
    env_path: Path = ENV_PATH,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch one gameweek of XLTHM projections for the optimiser."""
    if not 1 <= int(gameweek) <= 38:
        raise ValueError("gameweek must be between 1 and 38")

    gameweek = int(gameweek)
    http = session or requests.Session()
    key = _load_api_key(api_key, env_path)
    projection_payload = _get_json(
        http,
        players_url,
        params={
            "start_gameweek": gameweek,
            "gameweeks": 1,
            "detail": "full",
            "include_distribution": "false",
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    if not isinstance(projection_payload, Mapping):
        raise TypeError("XLTHM players response must be an object.")

    bootstrap = _get_json(http, bootstrap_url)
    return build_projection_dataframe(
        projection_payload.get("players", []),
        bootstrap,
        gameweek,
    )
