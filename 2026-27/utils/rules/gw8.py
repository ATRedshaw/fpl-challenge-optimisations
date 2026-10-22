"""Projection adjustment for GW8: Legends."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import requests


BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"
LEGENDS_CUTOFF = pd.Timestamp("2021-10-25")


def gw8_rules(
    projections: pd.DataFrame,
    api_url: str = BOOTSTRAP_URL,
    *,
    bootstrap: Mapping[str, Any] | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Double xPts for players who joined by 25 October 2021, inclusive.

    Five years of service is measured at the final GW8 deadline, 25 October 2026.
    """
    if bootstrap is None:
        http = session or requests.Session()
        response = http.get(api_url, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()

    eligible_ids = set()
    for element in bootstrap.get("elements", []):
        join_date = pd.to_datetime(element.get("team_join_date"), errors="coerce")
        if pd.notna(join_date) and join_date <= LEGENDS_CUTOFF:
            eligible_ids.add(int(element["id"]))

    adjusted = projections.copy()
    adjusted.loc[
        adjusted["ID"].astype(int).isin(eligible_ids), "Predicted_Points"
    ] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
