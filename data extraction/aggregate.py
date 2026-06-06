"""
aggregate.py — DM Stats Aggregator
====================================
Reads all per-game _stats.csv and _balls.csv files, applies name
normalisation, and outputs three aggregated CSV files:

  aggregated/dm_player_games.csv   — one row per player per game
  aggregated/dm_player_season.csv  — totals/averages per player per season
  aggregated/dm_player_alltime.csv — totals/averages per player all time

Usage:
    python "data extraction/aggregate.py"
"""

import csv
import glob
import os
from collections import defaultdict
from pathlib import Path

BASE_DIR  = Path(__file__).parent
CSV_DIR   = BASE_DIR / 'csv'
OUT_DIR   = BASE_DIR / 'aggregated'
URLS_CSV  = BASE_DIR / 'scorecard_urls.csv'

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Name normalisation map ─────────────────────────────────────────────────────
# 42 PDF variants → 25 canonical app names
NAME_MAP = {
    # Ashwin
    'Ash': 'Ashwin', 'Ashwin J': 'Ashwin', 'Ashwin': 'Ashwin',
    # Chibin
    'Chiban': 'Chibin', 'Chibin': 'Chibin',
    # Zayd
    'Zade .': 'Zayd', 'Zayd': 'Zayd', 'Zaid': 'Zayd',
    # Vijay
    'Vijay .': 'Vijay', 'Vijay': 'Vijay',
    # Yusuf
    'Yusuf .': 'Yusuf', 'Yusuf': 'Yusuf',
    # Godfrey
    'Godfeer': 'Godfrey', 'Godfrey': 'Godfrey',
    # Dony
    'Dony .': 'Dony', 'Donny': 'Dony', 'Dony': 'Dony',
    # Vishnu
    'Vish': 'Vishnu', 'Vishlu': 'Vishnu', 'Vishnu': 'Vishnu',
    # Amir
    'Ameer': 'Amir', 'Amir': 'Amir',
    # Nithin Thomas (nicknames: Ice, Unspecified in G16)
    'Nithin .': 'Nithin Thomas', 'Nithin': 'Nithin Thomas',
    'Ice': 'Nithin Thomas', 'Unspecified': 'Nithin Thomas',
    # Nithin G (nickname: Nitz)
    'Nitz': 'Nithin G',
    # Kiran Varghese — many variants; "Kiaran N" in Spring 2025 is Varghese
    # (only one Kiran on those rosters; G2 is the exception where both Kirans played)
    'Kiaran N': 'Kiran Varghese',
    'Kiaran V': 'Kiran Varghese', 'Kiran Varghese': 'Kiran Varghese',
    'Kieran': 'Kiran Varghese', 'Keiran': 'Kiran Varghese',
    # Kiran Ninan — "Kiran N" only appears in G2 where both Kirans are on the sheet
    'Kiran N': 'Kiran Ninan', 'Kiran Ninan': 'Kiran Ninan',
    # One-to-one
    'Arun': 'Arun', 'Akhil': 'Akhil', 'Aaron': 'Aaron', 'Alex': 'Alex',
    'Zach': 'Zach', 'Shaun': 'Shaun', 'Goukol': 'Goukol',
    'Jesse': 'Jesse', 'Merlin': 'Merlin', 'Nandu': 'Nandu',
    'Vinay': 'Vinay', 'Don': 'Don',
    'Nithin G': 'Nithin G',
}


def normalise(name: str) -> str | None:
    """Return canonical name, or None if not a DM player / unmapped."""
    return NAME_MAP.get(name.strip())


# ── Load game metadata ─────────────────────────────────────────────────────────

def load_meta() -> dict:
    """Returns dict: game -> {season, date, opponent, fixtureId, result}"""
    meta = {}
    with open(URLS_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            meta[row['GameWeek']] = {
                'season':    row['Season'],
                'game':      row['GameWeek'],
                'date':      row['Date'],
                'opponent':  row['Opponent'],
                'fixtureId': row['FixtureID'],
                'result':    row['Result'],
            }
    return meta


# ── Load contribution stats ────────────────────────────────────────────────────

def load_stats_csvs() -> list:
    """Load all _stats.csv files. Returns list of dicts with game + player stats."""
    rows = []
    for path in sorted(glob.glob(str(CSV_DIR / '*_stats.csv'))):
        stem = Path(path).stem.replace('_stats', '')
        parts = stem.split('_')
        game = parts[1]   # e.g. G1
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                team = row['team'].lower()
                # Some PDFs (e.g. G12, G13) have no team-name row in the
                # contribution table, so pdfplumber returns team='Name' (the
                # header cell). Accept these rows if the player normalises to
                # a known DM name and is not a known opponent player.
                is_dm = ('durban' in team or 'mallu' in team or team == 'name')
                if not is_dm:
                    continue
                canonical = normalise(row['name'])
                if not canonical:
                    continue
                rs = int(row['rs']) if row['rs'] else 0
                rc = int(row['rc']) if row['rc'] else 0
                # 'c' column absent in some PDFs — compute as RS - RC
                contrib = int(row['c']) if row.get('c') else (rs - rc)
                rows.append({
                    'game':    game,
                    'name':    canonical,
                    'rs':      rs,
                    'rc':      rc,
                    'wkts':    int(row['wkts']) if row['wkts'] else 0,
                    'contrib': contrib,
                    'sr':      float(row['sr']) if row['sr'] else 0.0,
                    'ob':      int(row['ob'])   if row['ob'] else 0,
                    'econ':    float(row['econ']) if row['econ'] else 0.0,
                })
    return rows


# ── Load ball-by-ball data ─────────────────────────────────────────────────────

def load_balls_csvs() -> dict:
    """
    Returns: { (game, canonical_name): {dotsFaced, dotsBowled, extras, sevens} }
    sevens = Zone D full hits (delivery_raw == '7', i.e. back-net-on-the-full for 7 runs).
    """
    result = defaultdict(lambda: {'dotsFaced': 0, 'dotsBowled': 0,
                                  'extras': 0, 'sevens': 0})

    for path in sorted(glob.glob(str(CSV_DIR / '*_balls.csv'))):
        stem = Path(path).stem.replace('_balls', '')
        parts = stem.split('_')
        game = parts[1]

        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                bat_team = row['batting_team'].lower()
                dm_batting = 'durban' in bat_team or 'mallu' in bat_team

                batter  = normalise(row['batter'])
                bowler  = normalise(row['bowler'])
                dtype   = row['delivery_type']
                runs    = int(row['runs']) if row['runs'] else 0
                raw     = row['delivery_raw'].strip()

                if dm_batting and batter:
                    # Dot balls are stored as delivery_type='runs', runs=0
                    if dtype == 'runs' and runs == 0:
                        result[(game, batter)]['dotsFaced'] += 1
                    elif dtype == 'extra':
                        result[(game, batter)]['extras'] += 1
                    # Sevens: Zone D full hit (back net on the full = 7 runs)
                    if raw == '7':
                        result[(game, batter)]['sevens'] += 1

                if not dm_batting and bowler:
                    if dtype == 'runs' and runs == 0:
                        result[(game, bowler)]['dotsBowled'] += 1

    return result


# ── Build per-game records ─────────────────────────────────────────────────────

GAME_FIELDS = [
    'season', 'game', 'date', 'opponent', 'fixtureId', 'result',
    'name',
    'rs', 'rc', 'wkts', 'contrib', 'sr', 'ob', 'econ',
    'dotsFaced', 'dotsBowled', 'extras', 'sevens',
]


def build_player_games(stats_rows, balls_map, meta) -> list:
    game_records = []
    # De-duplicate: some games have the same player twice (double-header PDF issue)
    # Keep the row with the higher |contrib| value as the primary entry.
    seen = {}
    for row in stats_rows:
        key = (row['game'], row['name'])
        if key not in seen or abs(row['contrib']) > abs(seen[key]['contrib']):
            seen[key] = row

    for (game, name), s in sorted(seen.items()):
        m = meta.get(game, {})
        b = balls_map.get((game, name), {})
        game_records.append({
            'season':     m.get('season', ''),
            'game':       game,
            'date':       m.get('date', ''),
            'opponent':   m.get('opponent', ''),
            'fixtureId':  m.get('fixtureId', ''),
            'result':     m.get('result', ''),
            'name':       name,
            'rs':         s['rs'],
            'rc':         s['rc'],
            'wkts':       s['wkts'],
            'contrib':    s['contrib'],
            'sr':         round(s['sr'], 1),
            'ob':         s['ob'],
            'econ':       round(s['econ'], 2),
            'dotsFaced':  b.get('dotsFaced', 0),
            'dotsBowled': b.get('dotsBowled', 0),
            'extras':     b.get('extras', 0),
            'sevens':     b.get('sevens', 0),
        })
    return game_records


# ── Aggregation helpers ────────────────────────────────────────────────────────

def safe_div(a, b, decimals=1):
    return round(a / b, decimals) if b else 0.0


def aggregate_group(rows: list) -> dict:
    gp = len(rows)
    rs_tot  = sum(r['rs']  for r in rows)
    rc_tot  = sum(r['rc']  for r in rows)
    wk_tot  = sum(r['wkts'] for r in rows)
    c_tot   = sum(r['contrib'] for r in rows)
    ob_tot  = sum(r['ob']  for r in rows)
    df_tot  = sum(r['dotsFaced']  for r in rows)
    db_tot  = sum(r['dotsBowled'] for r in rows)
    ex_tot  = sum(r['extras'] for r in rows)
    sv_tot  = sum(r['sevens'] for r in rows)

    # Strike rate: weighted (total RS / total balls faced × 100)
    # Balls faced ≈ RS * 100 / SR for each game — but SR can be 0 if RS=0
    # Simpler: average SR weighted by overs batted (ob proxy for balls)
    # Best: sum(rs)/sum(balls_faced)*100, but balls_faced not stored directly.
    # Use SR from stats CSV as a weighted average instead.
    sr_weighted = safe_div(
        sum(r['rs'] for r in rows if r['sr'] > 0),
        sum(r['rs'] / r['sr'] * 100 for r in rows if r['sr'] > 0) / 100,
        1
    ) if any(r['sr'] > 0 for r in rows) else 0.0

    # Economy: weighted by overs bowled
    if ob_tot > 0:
        econ_avg = safe_div(sum(r['rc'] for r in rows), ob_tot, 2)
    else:
        econ_avg = 0.0

    # Best contribution game
    best_c = max((r['contrib'] for r in rows), default=0)

    return {
        'gp':        gp,
        'rs_total':  rs_tot,
        'rs_avg':    safe_div(rs_tot, gp),
        'rs_best':   max((r['rs'] for r in rows), default=0),
        'rc_total':  rc_tot,
        'rc_avg':    safe_div(rc_tot, gp),
        'wkts_total': wk_tot,
        'wkts_avg':  safe_div(wk_tot, gp),
        'contrib_total': c_tot,
        'contrib_avg':   safe_div(c_tot, gp),
        'contrib_best':  best_c,
        'sr_avg':    sr_weighted,
        'ob_total':  ob_tot,
        'econ_avg':  econ_avg,
        'dotsFaced_total':  df_tot,
        'dotsBowled_total': db_tot,
        'extras_total':     ex_tot,
        'sevens_total':     sv_tot,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Loading metadata...")
    meta = load_meta()

    print("Loading contribution stats CSVs...")
    stats_rows = load_stats_csvs()
    print(f"  {len(stats_rows)} player-game stat rows loaded")

    print("Loading ball-by-ball CSVs...")
    balls_map = load_balls_csvs()
    print(f"  {len(balls_map)} player-game ball records loaded")

    print("Building per-game records...")
    game_records = build_player_games(stats_rows, balls_map, meta)
    print(f"  {len(game_records)} player-game records")

    # Write dm_player_games.csv
    games_path = OUT_DIR / 'dm_player_games.csv'
    with open(games_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=GAME_FIELDS)
        w.writeheader()
        w.writerows(game_records)
    print(f"Done: {games_path.name}")

    # Build per-season aggregates
    print("Aggregating by season...")
    by_season = defaultdict(list)
    for r in game_records:
        by_season[(r['name'], r['season'])].append(r)

    # Build field list from a real record
    _dummy = aggregate_group(game_records[:1])
    season_rows = []
    SEASON_FIELDS = ['name', 'season'] + list(_dummy.keys())
    for (name, season), rows in sorted(by_season.items()):
        agg = aggregate_group(rows)
        season_rows.append({'name': name, 'season': season, **agg})

    season_path = OUT_DIR / 'dm_player_season.csv'
    with open(season_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SEASON_FIELDS)
        w.writeheader()
        w.writerows(season_rows)
    print(f"Done: {season_path.name}")

    # Build all-time aggregates
    print("Aggregating all-time...")
    by_player = defaultdict(list)
    for r in game_records:
        by_player[r['name']].append(r)

    alltime_rows = []
    ALLTIME_FIELDS = ['name'] + list(_dummy.keys())
    for name, rows in sorted(by_player.items()):
        agg = aggregate_group(rows)
        alltime_rows.append({'name': name, **agg})

    alltime_path = OUT_DIR / 'dm_player_alltime.csv'
    with open(alltime_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=ALLTIME_FIELDS)
        w.writeheader()
        w.writerows(alltime_rows)
    print(f"Done: {alltime_path.name}")
    print()
    print("-- All-time leaderboard (top 10 by contrib_total) --")
    top10 = sorted(alltime_rows, key=lambda x: x['contrib_total'], reverse=True)[:10]
    print("  Name                  GP    RS    RC  Wkts  Contrib     SR  Econ")
    for r in top10:
        vals = (r['name'], r['gp'], r['rs_total'], r['rc_total'], r['wkts_total'], r['contrib_total'], r['sr_avg'], r['econ_avg'])
        print("  %-20s %3d %5d %5d %5d %7d %6.1f %6.2f" % vals)


if __name__ == '__main__':
    main()
