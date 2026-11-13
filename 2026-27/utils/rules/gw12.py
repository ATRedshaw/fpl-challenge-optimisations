"""Projection adjustment for GW12: Wonderkids."""

from __future__ import annotations

import pandas as pd
import requests


BOOTSTRAP_URL = "https://fplchallenge.premierleague.com/api/bootstrap-static/"


def gw12_rules(
    projections: pd.DataFrame,
    api_url: str = BOOTSTRAP_URL,
    *,
    bootstrap: dict | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Double xPts for players aged 23 or under at the final GW12 deadline."""
    if bootstrap is None:
        http = session or requests.Session()
        response = http.get(api_url, timeout=60)
        response.raise_for_status()
        bootstrap = response.json()

    deadline = pd.Timestamp(
        next(event for event in bootstrap["events"] if int(event["id"]) == 12)[
            "deadline_time"
        ]
    )
    birthday_cutoff = pd.Timestamp(deadline.date()) - pd.DateOffset(years=24)
    eligible_ids = set()
    for element in bootstrap["elements"]:
        birth_date = pd.to_datetime(element.get("birth_date"), errors="coerce")
        if pd.notna(birth_date) and birth_date > birthday_cutoff:
            eligible_ids.add(int(element["id"]))

    adjusted = projections.copy()
    adjusted.loc[
        adjusted["ID"].astype(int).isin(eligible_ids), "Predicted_Points"
    ] *= 2
    adjusted["Predicted_Points"] = adjusted["Predicted_Points"].round(2)
    return adjusted
