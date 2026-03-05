import json
import re
import sys
from pathlib import Path

import requests
import yaml

from utils.data import ensure_season_in_registry

SEASON = "2025-26"
CONFIG_PATH = Path(SEASON) / "data" / "config.yaml"

# Pattern captures challenge ID, description and title from the minified JS bundle.
# Expected fragment: <id>:{copy:{description:"...", ..., title:"..."}}
CHALLENGE_PATTERN = re.compile(
    r'(\d+):\{copy:\{description:"([^"]*)".*?title:"([^"]*)"\}'
)


def fetch_js(url: str) -> str:
    """
    Fetch raw JS bundle text from a URL.

    Args:
        url (str): URL of the JS asset to retrieve.

    Returns:
        str: Response body as text.
    """
    response = requests.get(url, timeout=30)
    if not response.ok:
        print(f"Failed to fetch JS ({response.status_code}): {url}", file=sys.stderr)
        sys.exit(1)
    return response.text


def parse_challenges(js_content: str) -> dict:
    """
    Extract challenge metadata from a minified JS bundle.

    Implementation:
        Regular expression matches challenge id, description and title from the
        minified bundle. Values are returned as strings keyed by challenge id.

    Args:
        js_content (str): Raw text of the JS bundle.

    Returns:
        dict: Mapping of challenge ID string to a dict containing 'title' and
              'description'.
    """
    challenges = {}
    for challenge_id, description, title in CHALLENGE_PATTERN.findall(js_content):
        challenges[challenge_id] = {
            "title": title,
            "description": description,
        }
    return challenges


def write_json(path: Path, data: dict) -> None:
    """
    Serialise data as indented JSON and write to path, creating parent dirs.

    Args:
        path (Path): Destination file path.
        data (dict): Dictionary to serialise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"Written: {path}")


def update_challenges() -> None:
    """
    Fetch, parse and persist FPL Challenge metadata for the 2025-26 season.

    Behaviour:
        Fetches the minified JS bundle, parses challenge metadata and writes
        JSON files to both the season data directory and the site data
        directory. Suitable for invocation at the start of a gameweek run.
    """
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    js_bundle_url = config.get("descriptions_link")
    if not js_bundle_url:
        print(f"No descriptions_link found in {CONFIG_PATH}.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching challenges for {SEASON} ...")
    js_content = fetch_js(js_bundle_url)
    challenges = parse_challenges(js_content)

    if not challenges:
        print(f"Warning: no challenges parsed for {SEASON}.", file=sys.stderr)

    write_json(Path(SEASON) / "data" / "descriptions" / "challenges.json", challenges)
    write_json(Path("site") / "data" / SEASON / "challenges.json", challenges)

    ensure_season_in_registry(SEASON)
