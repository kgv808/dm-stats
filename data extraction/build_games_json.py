"""
build_games_json.py — Rebuild data/games.json from extracted CSV data
======================================================================
Reads:
  - data extraction/aggregated/dm_player_games.csv   (player stats per game)
  - data extraction/scorecard_urls.csv               (game metadata)
  - data/games.json                                  (existing — preserves
                                                       seasons, games, pairsData,
                                                       bowlingData)

Writes:
  - data/games.json                                  (updated gameStats array)

Changes vs existing games.json:
  - gameStats rows now keyed by (game, fixtureId) not just date — fixes double-headers
  - gameStats gains 'game' and 'fixtureId' fields
  - games array gains 'game' field (G1..G19)
  - Stats sourced from PDF extraction instead of manual entry

Usage:
    python "data extraction/build_games_json.py"
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR    = Path(__file__).parent
GAMES_JSON  = BASE_DIR.parent / 'data' / 'games.json'
URLS_CSV    = BASE_DIR / 'scorecard_urls.csv'
PLAYER_CSV  = BASE_DIR / 'aggregated' / 'dm_player_games.csv'


def fmt_date(iso: str) -> str:
    """'2025-10-30' -> '30 Oct 2025'"""
    months = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']
    y, m, d = iso.split('-')
    return f"{int(d)} {months[int(m)-1]} {y}"


def main():
    # ── Load existing games.json ──────────────────────────────────────────────
    with open(GAMES_JSON, encoding='utf-8') as f:
        data = json.load(f)

    # ── Load game metadata (scorecard_urls.csv) ───────────────────────────────
    meta = {}
    with open(URLS_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            meta[row['GameWeek']] = row

    # ── Add 'game' field to existing games array ──────────────────────────────
    # Match by fixtureId (already present in games array)
    fixture_to_game = {r['FixtureID']: r['GameWeek'] for r in meta.values()}
    for g in data['games']:
        fid = str(g.get('fixtureId', ''))
        if fid in fixture_to_game:
            g['game'] = fixture_to_game[fid]

    # ── Load per-game player stats from CSV ───────────────────────────────────
    player_games = []
    with open(PLAYER_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            player_games.append(row)

    print(f"Loaded {len(player_games)} player-game records from CSV")

    # ── Build new gameStats array ─────────────────────────────────────────────
    new_game_stats = []
    for row in player_games:
        game      = row['game']
        m         = meta.get(game, {})
        date_iso  = row['date']
        date_fmt  = fmt_date(date_iso) if date_iso else ''

        new_game_stats.append({
            'season':    row['season'],
            'game':      game,
            'date':      date_fmt,
            'dateVal':   date_iso,
            'fixtureId': row['fixtureId'],
            'opponent':  row['opponent'],
            'name':      row['name'],
            # Core stats
            'rs':        int(row['rs']),
            'rc':        int(row['rc']),
            'wkts':      int(row['wkts']),
            'contrib':   int(row['contrib']),
            # Derived
            'sr':        float(row['sr']),
            'ob':        int(row['ob']),
            'econ':      float(row['econ']),
            # Ball-by-ball computed
            'sevens':    int(row['sevens']),
            'dotsFaced': int(row['dotsFaced']),
            'dotsBowled':int(row['dotsBowled']),
            'extras':    int(row['extras']),
        })

    # Sort: season order, then game number, then player name
    def sort_key(r):
        game_num = int(r['game'].replace('G', ''))
        return (game_num, r['name'])

    new_game_stats.sort(key=sort_key)

    print(f"Built {len(new_game_stats)} gameStats entries")

    # ── Validate: check player counts per game ────────────────────────────────
    by_game = defaultdict(list)
    for r in new_game_stats:
        by_game[r['game']].append(r['name'])

    print("\n-- Players per game --")
    for game in sorted(by_game, key=lambda g: int(g.replace('G',''))):
        n = len(by_game[game])
        flag = ' <<<' if n != 8 else ''
        print(f"  {game}: {n} players{flag} - {sorted(by_game[game])}")

    # ── Write updated games.json ──────────────────────────────────────────────
    data['gameStats'] = new_game_stats

    with open(GAMES_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nDone: {GAMES_JSON}")
    print(f"  seasons:     {len(data['seasons'])}")
    print(f"  games:       {len(data['games'])}")
    print(f"  gameStats:   {len(data['gameStats'])}")
    print(f"  pairsData:   {len(data['pairsData'])}")
    print(f"  bowlingData: {len(data['bowlingData'])}")


if __name__ == '__main__':
    main()
