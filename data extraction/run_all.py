"""
run_all.py — Batch extractor for all DM scorecards
====================================================
Reads scorecard_urls.csv, finds the matching PDF for each game,
and runs the extractor to produce .md and .csv files.

Usage:
    python "data extraction/run_all.py"
"""

import csv
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR   = Path(__file__).parent
PDF_DIR    = BASE_DIR / 'pdfs'
CSV_FILE   = BASE_DIR / 'scorecard_urls.csv'
SCRIPT     = BASE_DIR / 'extract_scorecard.py'

# PDF subfolders keyed by season
SEASON_FOLDERS = {
    'spring2025': PDF_DIR / 'Fourways Cricket - Cricket Spring Season 2025 - C3',
    'autumn2026': PDF_DIR / 'Hillfox Cricket - Cricket Autumn 2026 - C1',
}


def find_pdf(season: str, game: str) -> Path | None:
    """Find the PDF file matching a given season and game number."""
    folder = SEASON_FOLDERS.get(season)
    if not folder or not folder.exists():
        return None
    # Look for any file starting with the game number
    for f in folder.iterdir():
        if f.suffix.lower() == '.pdf' and f.name.startswith(game + ' '):
            return f
    return None


def main():
    if not CSV_FILE.exists():
        sys.exit(f"CSV not found: {CSV_FILE}")

    with open(CSV_FILE, newline='', encoding='utf-8') as f:
        games = list(csv.DictReader(f))

    print(f"Found {len(games)} games in CSV\n")

    success, skipped, failed = [], [], []

    for row in games:
        season   = row['Season']
        game     = row['GameWeek']
        date     = row['Date']
        opponent = row['Opponent']

        pdf = find_pdf(season, game)

        if not pdf:
            print(f"  [{game}] PDF not found - skipping")
            skipped.append(game)
            continue

        print(f"  [{game}] {pdf.name}")

        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             str(pdf),
             '--season',   season,
             '--game',     game,
             '--opponent', opponent,
             '--date',     date],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                print(f"         {line}")
            success.append(game)
        else:
            print(f"  [{game}] FAILED")
            print(result.stderr[-500:] if result.stderr else result.stdout[-500:])
            failed.append(game)

    print(f"\n-- Summary ----------------------------------")
    print(f"  Success: {len(success)} -- {', '.join(success)}")
    if skipped:
        print(f"  Skipped: {len(skipped)} -- {', '.join(skipped)}")
    if failed:
        print(f"  Failed:  {len(failed)} -- {', '.join(failed)}")


if __name__ == '__main__':
    main()
