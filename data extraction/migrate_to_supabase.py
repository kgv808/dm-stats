"""
migrate_to_supabase.py — One-time migration of all existing DM data to Supabase
================================================================================
Reads the current games.json + scorecard_urls.csv and populates:
  - seasons
  - games
  - players
  - player_aliases
  - game_stats
  - pair_stats
  - bowling_data

Run once after the schema has been applied in Supabase.

Setup:
    pip install supabase python-dotenv

Create a .env file in the project root (or set env vars directly):
    SUPABASE_URL=https://chswumfxdyjstgsddbhd.supabase.co
    SUPABASE_SERVICE_KEY=<your service_role key from Project Settings → API>

Usage:
    cd "data extraction"
    python migrate_to_supabase.py
"""

import csv
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass  # .env loading is optional if vars are set in the shell

try:
    from supabase import create_client, Client
except ImportError:
    sys.exit("supabase not installed. Run: pip install supabase")

# ── Config ─────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit(
        "Missing credentials.\n"
        "Set SUPABASE_URL and SUPABASE_SERVICE_KEY as environment variables,\n"
        "or create a .env file in the project root."
    )

BASE_DIR   = Path(__file__).parent
GAMES_JSON = BASE_DIR.parent / 'data' / 'games.json'
URLS_CSV   = BASE_DIR / 'scorecard_urls.csv'

# ── Name map ───────────────────────────────────────────────────────────────────
# Mirrors aggregate.py NAME_MAP — source of truth for players + aliases

NAME_MAP = {
    'Ash': 'Ashwin', 'Ashwin J': 'Ashwin', 'Ashwin': 'Ashwin',
    'Chiban': 'Chibin', 'Chibin': 'Chibin',
    'Zade .': 'Zayd', 'Zayd': 'Zayd', 'Zaid': 'Zayd',
    'Vijay .': 'Vijay', 'Vijay': 'Vijay',
    'Yusuf .': 'Yusuf', 'Yusuf': 'Yusuf',
    'Godfeer': 'Godfrey', 'Godfrey': 'Godfrey',
    'Dony .': 'Dony', 'Donny': 'Dony', 'Dony': 'Dony',
    'Vish': 'Vishnu', 'Vishlu': 'Vishnu', 'Vishnu': 'Vishnu',
    'Ameer': 'Amir', 'Amir': 'Amir',
    'Nithin .': 'Nithin Thomas', 'Nithin': 'Nithin Thomas',
    'Ice': 'Nithin Thomas', 'Unspecified': 'Nithin Thomas',
    'Nitz': 'Nithin G',
    'Kiaran N': 'Kiran Varghese',
    'Kiaran V': 'Kiran Varghese', 'Kiran Varghese': 'Kiran Varghese',
    'Kieran': 'Kiran Varghese', 'Keiran': 'Kiran Varghese',
    'Kiran N': 'Kiran Ninan', 'Kiran Ninan': 'Kiran Ninan',
    'Arun': 'Arun', 'Akhil': 'Akhil', 'Aaron': 'Aaron', 'Alex': 'Alex',
    'Zach': 'Zach', 'Shaun': 'Shaun', 'Goukol': 'Goukol',
    'Jesse': 'Jesse', 'Merlin': 'Merlin', 'Nandu': 'Nandu',
    'Vinay': 'Vinay', 'Don': 'Don', 'Nithin G': 'Nithin G',
}

# Game-specific overrides — {game_key: {raw_name: canonical}}
GAME_OVERRIDES = {
    'G2': {'Kiaran N': 'Kiran Ninan'},
}

# ── Helpers ─────────────────────────────────────────────────────────────────────

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def insert_batch(sb: Client, table: str, rows: list, label: str):
    """Insert rows in batches of 100, print progress."""
    if not rows:
        print(f"  {label}: nothing to insert")
        return
    total = 0
    for batch in chunks(rows, 100):
        sb.table(table).insert(batch).execute()
        total += len(batch)
    print(f"  {label}: inserted {total} rows")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Loading source data...")
    with open(GAMES_JSON, encoding='utf-8') as f:
        data = json.load(f)

    with open(URLS_CSV, newline='', encoding='utf-8') as f:
        urls_meta = {row['GameWeek']: row for row in csv.DictReader(f)}

    # ── 1. Seasons ──────────────────────────────────────────────────────────────
    print("\n[1/7] Inserting seasons...")
    season_rows = [
        {'key': s['id'], 'label': s['label']}
        for s in data['seasons']
    ]
    insert_batch(sb, 'seasons', season_rows, 'seasons')

    # Fetch back with IDs
    season_map = {
        r['key']: r['id']
        for r in sb.table('seasons').select('id,key').execute().data
    }
    print(f"  Season map: {season_map}")

    # ── 2. Games ────────────────────────────────────────────────────────────────
    print("\n[2/7] Inserting games...")
    game_rows = []
    for g in data['games']:
        meta = urls_meta.get(g['game'], {})
        game_rows.append({
            'season_id':  season_map[g['season']],
            'game_key':   g['game'],
            'date':       g.get('dateVal') or g.get('date', ''),
            'opponent':   g['opponent'],
            'result':     g['result'],
            'dm_score':   g.get('dmScore'),
            'opp_score':  g.get('oppScore'),
            'fixture_id': str(g.get('fixtureId', '')),
            'url':        meta.get('URL', ''),
            'dm_skins':   g.get('dmSkins', 0),
            'opp_skins':  g.get('oppSkins', 0),
            'points':     g.get('points', 0),
            'max_points': g.get('maxPoints', 0),
            'dm_skin1':   g.get('dmSkin1', 0),
            'dm_skin2':   g.get('dmSkin2', 0),
            'dm_skin3':   g.get('dmSkin3', 0),
            'dm_skin4':   g.get('dmSkin4', 0),
            'opp_skin1':  g.get('oppSkin1', 0),
            'opp_skin2':  g.get('oppSkin2', 0),
            'opp_skin3':  g.get('oppSkin3', 0),
            'opp_skin4':  g.get('oppSkin4', 0),
        })
    insert_batch(sb, 'games', game_rows, 'games')

    # Fetch back with IDs
    game_map = {
        r['game_key']: r['id']
        for r in sb.table('games').select('id,game_key').execute().data
    }
    print(f"  Inserted {len(game_map)} games")

    # ── 3. Players ──────────────────────────────────────────────────────────────
    print("\n[3/7] Inserting players...")
    canonical_names = sorted(set(NAME_MAP.values()))
    player_rows = [{'name': name} for name in canonical_names]
    insert_batch(sb, 'players', player_rows, 'players')

    # Fetch back with IDs
    player_map = {
        r['name']: r['id']
        for r in sb.table('players').select('id,name').execute().data
    }
    print(f"  Inserted {len(player_map)} players")

    # ── 4. Player aliases ───────────────────────────────────────────────────────
    print("\n[4/7] Inserting player aliases...")
    alias_rows = []

    # Global aliases from NAME_MAP
    for raw, canonical in NAME_MAP.items():
        pid = player_map.get(canonical)
        if not pid:
            print(f"  WARNING: canonical '{canonical}' not found in player_map")
            continue
        alias_rows.append({
            'raw_name':  raw,
            'player_id': pid,
            'game_id':   None,
        })

    # Game-specific overrides
    for game_key, overrides in GAME_OVERRIDES.items():
        gid = game_map.get(game_key)
        if not gid:
            print(f"  WARNING: game '{game_key}' not found for override")
            continue
        for raw, canonical in overrides.items():
            pid = player_map.get(canonical)
            if not pid:
                print(f"  WARNING: override canonical '{canonical}' not found")
                continue
            alias_rows.append({
                'raw_name':  raw,
                'player_id': pid,
                'game_id':   gid,
            })

    insert_batch(sb, 'player_aliases', alias_rows, 'player_aliases')

    # ── 5. Game stats ───────────────────────────────────────────────────────────
    print("\n[5/7] Inserting game_stats...")
    stat_rows = []
    unresolved = []

    for gs in data['gameStats']:
        gid = game_map.get(gs['game'])
        pid = player_map.get(gs['name'])
        if not gid:
            print(f"  WARNING: game '{gs['game']}' not in game_map, skipping")
            continue
        if not pid:
            unresolved.append((gs['game'], gs['name']))

        stat_rows.append({
            'game_id':     gid,
            'player_id':   pid,
            'raw_name':    gs['name'],
            'rs':          gs.get('rs', 0),
            'rc':          gs.get('rc', 0),
            'wkts':        gs.get('wkts', 0),
            'contrib':     gs.get('contrib', 0),
            'sr':          gs.get('sr', 0),
            'ob':          gs.get('ob', 0),
            'econ':        gs.get('econ', 0),
            'dots_faced':  gs.get('dotsFaced', 0),
            'dots_bowled': gs.get('dotsBowled', 0),
            'extras':      gs.get('extras', 0),
            'sevens':      gs.get('sevens', 0),
            'd_caught':    gs.get('dCaught', 0),
            'd_bowled':    gs.get('dBowled', 0),
            'd_runout':    gs.get('dRunOut', 0),
            'd_stumped':   gs.get('dStumped', 0),
        })

    insert_batch(sb, 'game_stats', stat_rows, 'game_stats')

    if unresolved:
        print(f"\n  ⚠️  {len(unresolved)} unresolved player names:")
        for game, name in unresolved:
            print(f"     {game}: '{name}'")
    else:
        print("  ✓  All player names resolved")

    # ── 6. Pair stats ───────────────────────────────────────────────────────────
    print("\n[6/7] Inserting pair_stats...")
    pair_rows = []
    for ps in data.get('pairStats', []):
        gid = game_map.get(ps['game'])
        if not gid:
            continue
        batters = ps.get('batters', [])
        p1_raw  = ps.get('pair', '').split(' & ')[0] if ' & ' in ps.get('pair', '') else ''
        p2_raw  = ps.get('pair', '').split(' & ')[1] if ' & ' in ps.get('pair', '') else ''
        p1_id   = player_map.get(batters[0]) if len(batters) > 0 else None
        p2_id   = player_map.get(batters[1]) if len(batters) > 1 else None
        pair_rows.append({
            'game_id':     gid,
            'skin':        ps['skin'],
            'player1_id':  p1_id,
            'player2_id':  p2_id,
            'player1_raw': p1_raw,
            'player2_raw': p2_raw,
            'dm_runs':     ps.get('dmRuns', 0),
            'opp_runs':    ps.get('oppRuns', 0),
            'dm_wickets':  ps.get('dmWickets', 0),
            'over_runs':   json.dumps(ps.get('overRuns', {})),
        })
    insert_batch(sb, 'pair_stats', pair_rows, 'pair_stats')

    # ── 7. Bowling data ─────────────────────────────────────────────────────────
    print("\n[7/7] Inserting bowling_data...")
    bowl_rows = []
    for bd in data.get('bowlingData', []):
        gid = game_map.get(bd['game'])
        pid = player_map.get(bd['bowler'])
        if not gid:
            continue
        bowl_rows.append({
            'game_id':  gid,
            'player_id': pid,
            'raw_name': bd['bowler'],
            'skin':     bd['skin'],
            'over_num': bd['over'],
            'rc':       bd['rc'],
        })
    insert_batch(sb, 'bowling_data', bowl_rows, 'bowling_data')

    # ── Summary ─────────────────────────────────────────────────────────────────
    print("\n✅  Migration complete!")
    print(f"   Seasons:      {len(season_rows)}")
    print(f"   Games:        {len(game_map)}")
    print(f"   Players:      {len(player_map)}")
    print(f"   Aliases:      {len(alias_rows)}")
    print(f"   Game stats:   {len(stat_rows)}")
    print(f"   Pair stats:   {len(pair_rows)}")
    print(f"   Bowling data: {len(bowl_rows)}")

    # Final check: unresolved_names view
    unresolved_check = sb.table('unresolved_names').select('*').execute().data
    if unresolved_check:
        print(f"\n⚠️  {len(unresolved_check)} unresolved names in DB (check unresolved_names view):")
        for r in unresolved_check:
            print(f"   {r['game_key']} ({r['date']}): '{r['raw_name']}'")
    else:
        print("\n✓  No unresolved names — all players matched successfully")


if __name__ == '__main__':
    main()
