"""Projection adjustment for GW1: Instant Impact."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import requests


BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
NEW_SIGNING_CUTOFF = pd.Timestamp("2026-06-01")


def eligible_new_signing_ids(bootstrap: Mapping[str, Any]) -> set[int]:
    """Return players whose Challenge join date meets the official GW1 cutoff."""
    eligible: set[int] = set()
    for element in bootstrap.get("elements", []):
        join_date = pd.to_datetime(element.get("team_join_date"), errors="coerce")
        if pd.notna(join_date) and join_date >= NEW_SIGNING_CUTOFF:
            eligible.add(int(element["id"]))
    return eligible


def gw1_rules(
    projections: pd.DataFrame,
    api_url: str = BOOTSTRAP_URL,
    *,
    bootstrap: Mapping[str, Any] | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Double xPts for players classed as summer signings in GW1.

    The official rule defines eligible signings as joining on or after
    1 June 2026. FPL Challenge's ``team_join_date`` also represents permanent
    loan conversions and newly registered youth players used by its filter.
    """
    if bootstrap is None:
        http = session or requests.Session()
        response = http.get(api_url, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()

    eligible_ids = eligible_new_signing_ids(bootstrap)
    adjusted = projections.copy()
    adjusted.loc[
        adjusted["ID"].astype(int).isin(eligible_ids), "Predicted_Points"
    ] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
