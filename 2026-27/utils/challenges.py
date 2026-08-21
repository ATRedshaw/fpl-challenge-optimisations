"""Discover and extract FPL Challenge descriptions from the live JS bundle."""

from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml

from utils.data import ensure_season_in_registry


SEASON_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SEASON_ROOT.parent
SEASON = SEASON_ROOT.name
CONFIG_PATH = SEASON_ROOT / "data" / "config.yaml"

CHALLENGE_PATTERN = re.compile(
    r'(\d+):\{copy:\{description:"((?:\\.|[^"\\])*)".*?'
    r'title:"((?:\\.|[^"\\])*)"\}',
    re.DOTALL,
)
INDEX_BUNDLE_PATTERN = re.compile(r"(?:^|/)assets/index-[^/?]+\.js(?:\?.*)?$")


class _ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "script":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        if values.get("src"):
            self.scripts.append(values)


def fetch_text(url: str, session: requests.Session | None = None) -> str:
    http = session or requests.Session()
    response = http.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def discover_js_bundle_url(page_url: str, html: str) -> str:
    """Return the hashed main JS asset referenced by the Challenge homepage."""
    parser = _ScriptParser()
    parser.feed(html)

    candidates = []
    for script in parser.scripts:
        src = script["src"]
        path = urlparse(src).path
        if INDEX_BUNDLE_PATTERN.search(path):
            # Prefer the module script when more than one matching asset exists.
            candidates.append((script.get("type") == "module", urljoin(page_url, src)))

    if not candidates:
        raise ValueError(f"No /assets/index-*.js script found at {page_url}")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _decode_js_string(value: str) -> str:
    # Challenge copy is emitted as JSON-compatible double-quoted JS strings.
    return json.loads(f'"{value}"')


def parse_challenges(js_content: str) -> dict[str, dict[str, str]]:
    """Extract challenge ID, title, and description from the minified bundle."""
    challenges: dict[str, dict[str, str]] = {}
    for challenge_id, description, title in CHALLENGE_PATTERN.findall(js_content):
        challenges[challenge_id] = {
            "title": _decode_js_string(title),
            "description": _decode_js_string(description),
        }
    return challenges


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Written: {path.relative_to(PROJECT_ROOT)}")


def update_challenges(session: requests.Session | None = None) -> dict:
    """Discover the current bundle, parse its challenge copy, and mirror it."""
    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    page_url = config.get(
        "descriptions_page", "https://fplchallenge.premierleague.com/"
    )
    print(f"Discovering the current FPL Challenge bundle from {page_url} ...")
    html = fetch_text(page_url, session=session)
    js_bundle_url = discover_js_bundle_url(page_url, html)
    print(f"Fetching challenge descriptions from {js_bundle_url} ...")
    challenges = parse_challenges(fetch_text(js_bundle_url, session=session))
    if not challenges:
        raise ValueError(f"No challenge descriptions parsed from {js_bundle_url}")

    write_json(SEASON_ROOT / "data" / "descriptions" / "challenges.json", challenges)
    write_json(PROJECT_ROOT / "site" / "data" / SEASON / "challenges.json", challenges)
    ensure_season_in_registry(SEASON)
    return challenges


if __name__ == "__main__":
    update_challenges()
