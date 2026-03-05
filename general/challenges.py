"""
Fetches FPL Challenge descriptions from the JS bundle for each configured season,
parses challenge metadata, and writes the output to both the season data directory
and the site data directory.

Run from the repository root:
    python general/challenges.py
"""

import json
import re
import sys
from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path("general/config.yaml")

# Captures challenge ID, description, and title from the minified JS bundle.
# Format: <id>:{copy:{description:"...", ..., title:"..."}}
CHALLENGE_PATTERN = re.compile(
    r'(\d+):\{copy:\{description:"([^"]*)".*?title:"([^"]*)"\}'
)


def fetch_js(url: str) -> str:
    """Fetch the raw JS bundle text from the given URL.

    :param url: The URL of the JS asset to retrieve.
    :returns: The response body as a string.
    :raises SystemExit: If the request fails.
    """
    response = requests.get(url, timeout=30)
    if not response.ok:
        print(f"Failed to fetch JS ({response.status_code}): {url}", file=sys.stderr)
        sys.exit(1)
    return response.text


def parse_challenges(js_content: str) -> dict:
    """Extract challenge metadata from a minified JS bundle.

    :param js_content: Raw text of the JS bundle.
    :returns: Mapping of challenge ID string to title and description.
    """
    challenges = {}
    for challenge_id, description, title in CHALLENGE_PATTERN.findall(js_content):
        challenges[challenge_id] = {
            "title": title,
            "description": description,
        }
    return challenges


def write_json(path: Path, data: dict) -> None:
    """Serialise *data* as indented JSON and write to *path*, creating parent dirs.

    :param path: Destination file path.
    :param data: Dictionary to serialise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"Written: {path}")


def main() -> None:
    """Entry point — iterates over each season in config and processes challenges."""
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for season, settings in config.items():
        url = settings.get("descriptions_link")
        if not url:
            print(f"No descriptions_link for season {season}, skipping.")
            continue

        print(f"Fetching challenges for {season} from {url} ...")
        js_content = fetch_js(url)
        challenges = parse_challenges(js_content)

        if not challenges:
            print(f"Warning: no challenges parsed for {season}.", file=sys.stderr)

        season_data_path = Path(season) / "data" / "challenges.json"
        site_data_path = Path("site") / "data" / season / "challenges.json"

        write_json(season_data_path, challenges)
        write_json(site_data_path, challenges)


if __name__ == "__main__":
    main()