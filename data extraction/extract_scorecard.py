"""
extract_scorecard.py - Durban Mallu's Scorecard Extractor v3
=============================================================
Extracts ball-by-ball data AND contribution stats from Action Sports
(Spawtz) PDF scorecards. Saves structured Markdown + two CSV files.

Output files per game:
  extracts/SEASON_GAME_OPP.md        - ball-by-ball markdown
  csv/SEASON_GAME_OPP_balls.csv      - every delivery (ball-by-ball)
  csv/SEASON_GAME_OPP_stats.csv      - per-player contribution stats

Usage:
    python extract_scorecard.py <pdf_path> [options]

Options:
    --season    Season ID (e.g. spring2025, autumn2026)
    --game      Game number (e.g. G1)
    --opponent  Opponent team name
    --date      Match date (YYYY-MM-DD)
    --out       Output base folder (default: same folder as this script)

Requirements:
    pip install pdfplumber
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path


# ── Table layout constants ─────────────────────────────────────────────────────
# Each batting table has 17 rows:
#   Row 0:          'Batting Team:', team_name
#   Rows 1,5,9,13:  Skin header (over numbers + bowler names)
#   Rows 2,6,10,14: Batter 1 deliveries
#   Rows 3,7,11,15: Batter 2 deliveries
#   Rows 4,8,12,16: Skin totals (contains 'N/M' wickets/runs per over)
#
# Each over block starts at these column indices (col where over number sits):
OVER_START_COLS = [1, 8, 15, 22]


# ── Delivery notation ──────────────────────────────────────────────────────────
DELIVERY_MAP = {
    'w':   {'type': 'wicket',  'subtype': 'caught',     'runs': -5},
    'c':   {'type': 'wicket',  'subtype': 'caught',     'runs': -5},
    'b':   {'type': 'wicket',  'subtype': 'bowled',     'runs': -5},
    'ro':  {'type': 'wicket',  'subtype': 'runout',     'runs': -5},
    'r':   {'type': 'wicket',  'subtype': 'runout',     'runs': -5},
    'st':  {'type': 'wicket',  'subtype': 'stumped',    'runs': -5},
    's':   {'type': 'wicket',  'subtype': 'stumped',    'runs': -5},
    'lbw': {'type': 'wicket',  'subtype': 'lbw',        'runs': -5},
    'lb':  {'type': 'wicket',  'subtype': 'lbw',        'runs': -5},
    'h':   {'type': 'wicket',  'subtype': 'hitwkt',     'runs': -5},
    'hw':  {'type': 'wicket',  'subtype': 'hitwkt',     'runs': -5},
    'h/w': {'type': 'wicket',  'subtype': 'hitwkt',     'runs': -5},
    'm':   {'type': 'wicket',  'subtype': 'mankad',     'runs': -5},
    '2b':  {'type': 'wicket',  'subtype': 'secondball', 'runs': -5},
    'nb':  {'type': 'extra',   'subtype': 'noball',     'runs': 2},
    'ls':  {'type': 'extra',   'subtype': 'legside',    'runs': 2},
    'wd':  {'type': 'extra',   'subtype': 'wide',       'runs': 2},
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def clean_cell(cell) -> str:
    if cell is None:
        return ''
    return str(cell).strip().lower().replace('\n', ' ')


def clean_name(raw) -> str:
    if not raw:
        return ''
    name = re.sub(r'\s+unknown\s*$', '', str(raw), flags=re.IGNORECASE).strip()
    name = re.sub(r'\s+', ' ', name)
    return name.title()


def parse_delivery(raw) -> dict:
    s = clean_cell(raw)

    if s == '' or s == '-':
        return {'raw': '', 'type': 'dot', 'subtype': None, 'runs': 0}

    try:
        runs = int(s)
        return {'raw': s, 'type': 'runs', 'subtype': None, 'runs': runs}
    except ValueError:
        pass

    if s in DELIVERY_MAP:
        d = DELIVERY_MAP[s].copy()
        d['raw'] = s
        return d

    # Code with embedded bonus number: e.g. 'ls1' (legside + 1 bonus run)
    m = re.match(r'^([a-z/]+)(\d+)$', s)
    if m:
        code, bonus = m.group(1), int(m.group(2))
        if code in DELIVERY_MAP:
            d = DELIVERY_MAP[code].copy()
            d['raw'] = s
            d['runs'] += bonus
            return d

    # Number + code: e.g. '1nb'
    m = re.match(r'^(\d+)([a-z/]+)$', s)
    if m:
        code = m.group(2)
        if code in DELIVERY_MAP:
            d = DELIVERY_MAP[code].copy()
            d['raw'] = s
            return d

    return {'raw': s, 'type': 'unknown', 'subtype': None, 'runs': 0}


# ── PDF extraction ─────────────────────────────────────────────────────────────

def extract_tables(pdf_path: str) -> list:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber not installed. Run: pip install pdfplumber")

    all_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                if table and len(table) > 1:
                    all_tables.append({'page': page_num, 'data': table})
    return all_tables


def find_batting_tables(all_tables: list) -> list:
    result = []
    for t in all_tables:
        row0 = t['data'][0] if t['data'] else []
        row0_text = ' '.join(str(c) for c in row0 if c)
        if 'Batting Team:' in row0_text:
            result.append(t)
    return result


def find_contribution_tables(all_tables: list) -> list:
    """Find per-player contribution stat tables (Name, RS, SR, OB, RC...)."""
    result = []
    for t in all_tables:
        for row in t['data'][:3]:
            cells = [clean_cell(c) for c in row if c]
            if 'name' in cells and 'rs' in cells and 'sr' in cells:
                result.append(t)
                break
    return result


# ── Over boundary detection ────────────────────────────────────────────────────

def find_subtotal_cols(totals_row: list) -> list:
    """
    Find column indices of per-over subtotals in the skin totals row.
    Subtotals look like '0/5', '1/-3', '2/14' (wickets/runs).
    Returns list of col indices in over order.
    """
    cols = []
    for col_idx, cell in enumerate(totals_row):
        val = clean_cell(cell)
        if re.match(r'^\d+/-?\d+$', val):
            cols.append(col_idx)
    return cols


# ── Batting table parser ───────────────────────────────────────────────────────

def parse_batting_table(table) -> dict:
    data = table['data']

    # Team name from row 0
    team_name = ''
    row0 = [str(c).strip() if c else '' for c in data[0]]
    for i, cell in enumerate(row0):
        if 'Batting Team' in cell:
            for j in range(i + 1, len(row0)):
                if row0[j]:
                    team_name = row0[j]
                    break
            break

    result = {'team': team_name, 'skins': {}}

    for skin_idx in range(4):
        skin_num = skin_idx + 1
        base = 1 + skin_idx * 4

        if base + 3 >= len(data):
            print(f"  Warning: table too short for skin {skin_num}")
            break

        header_row  = data[base]
        batter1_row = data[base + 1]
        batter2_row = data[base + 2]
        totals_row  = data[base + 3]

        # Find where each over's subtotal sits in the totals row.
        # This tells us how many balls are in each over (handles 6 AND 7 ball overs).
        subtotal_cols = find_subtotal_cols(totals_row)

        # Parse over headers
        overs_meta = []
        for i, start_col in enumerate(OVER_START_COLS):
            if start_col >= len(header_row):
                continue
            over_num_raw = clean_cell(header_row[start_col])
            bowler_raw   = clean_cell(header_row[start_col + 1]) if start_col + 1 < len(header_row) else ''
            try:
                over_num = int(over_num_raw)
                # Balls run from start_col up to (but not including) the subtotal col
                subtotal_col = subtotal_cols[i] if i < len(subtotal_cols) else start_col + 6
                overs_meta.append({
                    'over':         over_num,
                    'bowler':       clean_name(bowler_raw),
                    'start_col':    start_col,
                    'subtotal_col': subtotal_col,
                })
            except ValueError:
                pass

        # Parse batter rows
        batters = []
        for batter_row in [batter1_row, batter2_row]:
            if not batter_row:
                continue
            raw_name = batter_row[0]
            player_name = clean_name(str(raw_name).strip()) if raw_name else ''
            if not player_name:
                continue

            player_overs = {}
            for ov in overs_meta:
                balls = []
                for col in range(ov['start_col'], ov['subtotal_col']):
                    if col < len(batter_row):
                        balls.append(parse_delivery(batter_row[col]))
                player_overs[ov['over']] = {
                    'bowler': ov['bowler'],
                    'balls':  balls,
                }
            batters.append({'name': player_name, 'overs': player_overs})

        # Skin score: last numeric value in totals row
        skin_score = None
        if totals_row:
            for v in [clean_cell(c) for c in reversed(totals_row) if clean_cell(c)]:
                try:
                    skin_score = int(v)
                    break
                except ValueError:
                    pass

        result['skins'][skin_num] = {
            'pair':       [b['name'] for b in batters],
            'batters':    batters,
            'skin_score': skin_score,
        }

    return result


# ── Contribution stats parser ──────────────────────────────────────────────────

def parse_contribution_table(table) -> dict:
    """
    Parse a player contribution table into:
    { team_name: str, players: [{ name, rs, sr, ob, rc, wkts, econ, c }, ...] }
    """
    data = table['data']

    # Row 0 = team name, Row 1 = headers, Rows 2+ = player data
    team_name = clean_cell(data[0][0]) if data[0] else ''
    team_name = team_name.title()

    # Find header row
    headers = []
    header_row_idx = 0
    for i, row in enumerate(data):
        cells = [clean_cell(c) for c in row if c]
        if 'name' in cells and 'rs' in cells:
            headers = [clean_cell(c) for c in row]
            header_row_idx = i
            break

    if not headers:
        return {'team': team_name, 'players': []}

    players = []
    for row in data[header_row_idx + 1:]:
        if not row or not row[0]:
            continue
        player = {}
        for col_idx, header in enumerate(headers):
            if col_idx < len(row):
                player[header] = clean_cell(row[col_idx])
        if player.get('name'):
            player['name'] = clean_name(player['name'])
            players.append(player)

    return {'team': team_name, 'players': players}


def identify_teams(batting_tables: list, opponent: str) -> tuple:
    parsed = [parse_batting_table(t) for t in batting_tables]
    dm, opp = None, None
    for p in parsed:
        name_lower = p['team'].lower()
        if 'durban' in name_lower or 'mallu' in name_lower or 'dm' in name_lower:
            dm = p
        else:
            opp = p
    if dm is None and len(parsed) >= 2:
        opp, dm = parsed[0], parsed[1]
    elif opp is None and len(parsed) >= 2:
        opp = parsed[0] if parsed[0] is not dm else parsed[1]
    return dm, opp


# ── CSV output ─────────────────────────────────────────────────────────────────

BALLS_CSV_FIELDS = [
    'season', 'game', 'date',
    'batting_team', 'bowling_team',
    'skin', 'pair',
    'batter', 'bowler',
    'over', 'ball',
    'delivery_raw', 'delivery_type', 'delivery_sub', 'runs',
]

STATS_CSV_FIELDS = [
    'season', 'game', 'date', 'team',
    'name', 'rs', 'sr', 'ob', 'rc', 'wkts', 'econ', 'c',
]


def build_balls_csv(dm: dict, opp: dict, meta: dict) -> list:
    rows = []

    def add_team(batting_team, bowling_team_name):
        for skin_num, skin in sorted(batting_team['skins'].items()):
            for batter in skin['batters']:
                for over_num, over_data in sorted(batter['overs'].items()):
                    for ball_num, ball in enumerate(over_data['balls'], 1):
                        if ball['raw'] == '' and ball['type'] == 'dot':
                            continue
                        rows.append({
                            'season':        meta['season'],
                            'game':          meta['game'],
                            'date':          meta['date'],
                            'batting_team':  batting_team['team'],
                            'bowling_team':  bowling_team_name,
                            'skin':          skin_num,
                            'pair':          ' & '.join(skin['pair']),
                            'batter':        batter['name'],
                            'bowler':        over_data['bowler'],
                            'over':          over_num,
                            'ball':          ball_num,
                            'delivery_raw':  ball['raw'],
                            'delivery_type': ball['type'],
                            'delivery_sub':  ball['subtype'] or '',
                            'runs':          ball['runs'],
                        })

    opp_name = opp['team'] if opp else meta.get('opponent', 'Opponent')
    dm_name  = dm['team']  if dm  else "Durban Mallus"
    if dm:
        add_team(dm, opp_name)
    if opp:
        add_team(opp, dm_name)
    return rows


def build_stats_csv(contrib_tables: list, meta: dict) -> list:
    rows = []
    for table in contrib_tables:
        parsed = parse_contribution_table(table)
        for player in parsed['players']:
            rows.append({
                'season': meta['season'],
                'game':   meta['game'],
                'date':   meta['date'],
                'team':   parsed['team'],
                'name':   player.get('name', ''),
                'rs':     player.get('rs', ''),
                'sr':     player.get('sr', ''),
                'ob':     player.get('ob', ''),
                'rc':     player.get('rc', ''),
                'wkts':   player.get('wkts', ''),
                'econ':   player.get('econ', ''),
                'c':      player.get('c', ''),
            })
    return rows


# ── Markdown output ────────────────────────────────────────────────────────────

def fmt_delivery(d: dict) -> str:
    if d['type'] == 'dot':
        return '0'
    if d['type'] == 'runs':
        return str(d['runs'])
    if d['type'] == 'wicket':
        codes = {'caught': 'c', 'bowled': 'b', 'runout': 'ro', 'stumped': 'st',
                 'lbw': 'lbw', 'hitwkt': 'hw', 'mankad': 'm', 'secondball': '2b'}
        return codes.get(d['subtype'], 'w')
    if d['type'] == 'extra':
        codes = {'noball': 'nb', 'legside': 'ls', 'wide': 'wd'}
        return codes.get(d['subtype'], 'ex')
    return d['raw'] or '?'


def batting_grid_md(parsed: dict, title: str) -> str:
    lines = [f"## {title}\n"]
    for skin_num in sorted(parsed['skins']):
        skin = parsed['skins'][skin_num]
        pair_label = ' + '.join(skin['pair']) if skin['pair'] else 'Unknown'
        score_label = f"Skin score: {skin['skin_score']}" if skin['skin_score'] is not None else ''
        over_nums = sorted({o for b in skin['batters'] for o in b['overs']})

        lines.append(f"### Skin {skin_num} | {pair_label}")
        if score_label:
            lines.append(f"_{score_label}_\n")

        if not over_nums:
            lines.append("_No data_\n")
            continue

        header = '| Batter | ' + ' | '.join(f'O{o}' for o in over_nums) + ' | RS | Wkts |'
        sep    = '|--------|' + '--------|' * len(over_nums) + '-----|------|'
        lines.append(header)
        lines.append(sep)

        for batter in skin['batters']:
            cells, rs, wkts = [], 0, 0
            for o in over_nums:
                balls = batter['overs'].get(o, {}).get('balls', [])
                delivered = [b for b in balls if b['raw'] != '']
                cell_str = ' '.join(fmt_delivery(b) for b in delivered) if delivered else '-'
                cells.append(cell_str)
                for b in delivered:
                    rs += b['runs']
                    if b['type'] == 'wicket':
                        wkts += 1
            lines.append(f"| {batter['name']} | " + ' | '.join(cells) + f' | {rs} | {wkts} |')

        lines.append('')
    return '\n'.join(lines)


def build_markdown(dm: dict, opp: dict, meta: dict) -> str:
    season_label = meta.get('season', '').replace('spring', 'Spring ').replace('autumn', 'Autumn ')
    game     = meta.get('game', '')
    opponent = meta.get('opponent', opp['team'] if opp else 'Unknown')
    date     = meta.get('date', '')

    sections = [
        f"# {game} - {date} - DM vs {opponent}",
        f"**Season:** {season_label}",
        "",
        "---",
        "",
    ]

    if dm:
        sections.append(batting_grid_md(dm, f"DM Batting - vs {opponent}"))
        sections.append("---\n")
    if opp:
        sections.append(batting_grid_md(opp, f"{opponent} Batting - DM Bowling"))
        sections.append("---\n")

    return '\n'.join(sections)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Extract DM scorecard from PDF')
    parser.add_argument('pdf',        help='Path to the scorecard PDF')
    parser.add_argument('--season',   default='unknown',  help='Season ID (e.g. spring2025)')
    parser.add_argument('--game',     default='G?',       help='Game number (e.g. G1)')
    parser.add_argument('--opponent', default='Opponent', help='Opponent team name')
    parser.add_argument('--date',     default='',         help='Match date YYYY-MM-DD')
    parser.add_argument('--out',      default=None,       help='Output base folder')
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"Error: PDF not found: {args.pdf}")

    base_dir     = Path(args.out) if args.out else Path(__file__).parent
    extracts_dir = base_dir / 'extracts'
    csv_dir      = base_dir / 'csv'
    extracts_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    safe_opp  = re.sub(r'[^\w]', '_', args.opponent)
    stem      = f"{args.season}_{args.game}_{safe_opp}"
    md_file   = extracts_dir / f"{stem}.md"
    balls_csv = csv_dir      / f"{stem}_balls.csv"
    stats_csv = csv_dir      / f"{stem}_stats.csv"

    print(f"Extracting: {args.pdf}")

    tables = extract_tables(args.pdf)
    print(f"  Tables found: {len(tables)}")

    batting_tables = find_batting_tables(tables)
    contrib_tables = find_contribution_tables(tables)
    print(f"  Batting tables: {len(batting_tables)} | Contribution tables: {len(contrib_tables)}")

    if len(batting_tables) < 2:
        print(f"ERROR: Expected 2 batting tables, found {len(batting_tables)}")
        sys.exit(1)

    meta = {
        'season':   args.season,
        'game':     args.game,
        'opponent': args.opponent,
        'date':     args.date,
    }

    dm, opp = identify_teams(batting_tables, args.opponent)

    if dm:
        print(f"  DM:  '{dm['team']}' | Skins: {len(dm['skins'])}")
    if opp:
        print(f"  Opp: '{opp['team']}' | Skins: {len(opp['skins'])}")

    # Write markdown
    md_file.write_text(build_markdown(dm, opp, meta), encoding='utf-8')
    print(f"Done: Markdown  -> {md_file.name}")

    # Write ball-by-ball CSV
    ball_rows = build_balls_csv(dm, opp, meta)
    with open(balls_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=BALLS_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(ball_rows)
    print(f"Done: Balls CSV -> {balls_csv.name} ({len(ball_rows)} rows)")

    # Write contribution stats CSV
    stat_rows = build_stats_csv(contrib_tables, meta)
    with open(stats_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=STATS_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(stat_rows)
    print(f"Done: Stats CSV -> {stats_csv.name} ({len(stat_rows)} players)")

    # Skin score sanity check
    print("\n-- DM Skin Scores ------------------")
    if dm:
        for sn, skin in sorted(dm['skins'].items()):
            print(f"  Skin {sn}: {skin['pair']} = {skin['skin_score']}")


if __name__ == '__main__':
    main()
