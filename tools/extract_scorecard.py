"""
extract_scorecard.py — Durban Mallu's Scorecard Extractor
==========================================================
Extracts ball-by-ball batting tables from Action Sports (Spawtz) PDF scorecards
and saves them as structured Markdown files for use with the DM stats tracker.

Usage:
    python extract_scorecard.py <pdf_path> [options]

Options:
    --season    Season ID (e.g. spring2025, autumn2026)
    --game      Game number (e.g. G7)
    --opponent  Opponent name
    --date      Match date (YYYY-MM-DD)
    --out       Output folder for MD file (default: ../scorecards/)

Example:
    python extract_scorecard.py scorecard_G7.pdf --season autumn2026 --game G7 --opponent Incredibles --date 2026-02-24

Requirements:
    pip install pdfplumber pdf2image pytesseract pillow
    (Also requires Poppler for pdf2image on Windows:
     https://github.com/oschwartz10612/poppler-windows/releases)
"""

import argparse
import os
import re
import sys
from pathlib import Path


# ── Delivery notation ─────────────────────────────────────────────────────────
# Maps raw scorecard codes to structured types and run values
DELIVERY_MAP = {
    # Dismissals (−5 runs, batter continues)
    'w':   {'type': 'wicket',  'subtype': 'caught',    'runs': -5},
    'c':   {'type': 'wicket',  'subtype': 'caught',    'runs': -5},
    'b':   {'type': 'wicket',  'subtype': 'bowled',    'runs': -5},
    'ro':  {'type': 'wicket',  'subtype': 'runout',    'runs': -5},
    'r':   {'type': 'wicket',  'subtype': 'runout',    'runs': -5},
    'st':  {'type': 'wicket',  'subtype': 'stumped',   'runs': -5},
    's':   {'type': 'wicket',  'subtype': 'stumped',   'runs': -5},
    'lbw': {'type': 'wicket',  'subtype': 'lbw',       'runs': -5},
    'lb':  {'type': 'wicket',  'subtype': 'lbw',       'runs': -5},
    'h':   {'type': 'wicket',  'subtype': 'hitwkt',    'runs': -5},
    'hw':  {'type': 'wicket',  'subtype': 'hitwkt',    'runs': -5},
    'h/w': {'type': 'wicket',  'subtype': 'hitwkt',    'runs': -5},
    'm':   {'type': 'wicket',  'subtype': 'mankad',    'runs': -5},
    '2b':  {'type': 'wicket',  'subtype': 'secondball','runs': -5},
    # Extras (+2 runs, no extra delivery)
    'nb':  {'type': 'extra',   'subtype': 'noball',    'runs': 2},
    'ls':  {'type': 'extra',   'subtype': 'legside',   'runs': 2},
    'wd':  {'type': 'extra',   'subtype': 'wide',      'runs': 2},
}

OVER_LABELS = {
    1: ('S1', 'O1'), 2: ('S1', 'O2'), 3: ('S1', 'O3'), 4: ('S1', 'O4'),
    5: ('S2', 'O1'), 6: ('S2', 'O2'), 7: ('S2', 'O3'), 8: ('S2', 'O4'),
    9: ('S3', 'O1'),10: ('S3', 'O2'),11: ('S3', 'O3'),12: ('S3', 'O4'),
   13: ('S4', 'O1'),14: ('S4', 'O2'),15: ('S4', 'O3'),16: ('S4', 'O4'),
}


# ── PDF extraction ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[str]:
    """Extract text from each page of a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber not installed. Run: pip install pdfplumber")

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                pages_text.append(text)
    return pages_text


def extract_tables_from_pdf(pdf_path: str) -> list:
    """Extract structured tables from PDF using pdfplumber's table detector."""
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber not installed. Run: pip install pdfplumber")

    all_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            for table in tables:
                if table and len(table) > 2:
                    all_tables.append({'page': page_num, 'data': table})
    return all_tables


# ── Table parsing ──────────────────────────────────────────────────────────────

def clean_cell(cell: str) -> str:
    """Normalise a cell value: strip whitespace, lowercase."""
    if cell is None:
        return ''
    return str(cell).strip().lower().replace('\n', ' ')


def parse_delivery(raw: str) -> dict:
    """Parse a raw cell value into a structured delivery event."""
    raw = clean_cell(raw)
    if raw == '' or raw == '-':
        return {'raw': raw, 'type': 'dot', 'subtype': None, 'runs': 0}

    # Pure number = runs scored
    try:
        runs = int(raw)
        return {'raw': raw, 'type': 'runs', 'subtype': None, 'runs': runs}
    except ValueError:
        pass

    # Known code
    if raw in DELIVERY_MAP:
        d = DELIVERY_MAP[raw].copy()
        d['raw'] = raw
        return d

    # Number + code (e.g. "w1", "nb2")
    m = re.match(r'^(\d+)([a-z/]+)$', raw)
    if m:
        code = m.group(2)
        if code in DELIVERY_MAP:
            d = DELIVERY_MAP[code].copy()
            d['raw'] = raw
            return d

    # Fallback — treat as dot
    return {'raw': raw, 'type': 'unknown', 'subtype': None, 'runs': 0}


def find_batting_sections(tables: list) -> dict:
    """
    Identify DM batting table and opponent batting table from extracted tables.
    Returns {'dm': table_data, 'opp': table_data}
    """
    dm_table = None
    opp_table = None

    for t in tables:
        data = t['data']
        # Look for header row containing over numbers 1-16
        for row in data[:3]:
            row_text = ' '.join([clean_cell(c) for c in row if c])
            # Over columns usually appear as single digits 1-16
            over_nums = re.findall(r'\b(\d{1,2})\b', row_text)
            if len(over_nums) >= 8:
                # Check if this looks like DM batting (DM player names in row labels)
                # or opponent batting
                # We rely on the caller to identify which is which based on section header
                if dm_table is None:
                    dm_table = t
                elif opp_table is None:
                    opp_table = t
                break

    return {'dm': dm_table, 'opp': opp_table}


def parse_batting_grid(table_data: list, team_name: str) -> dict:
    """
    Parse a batting grid table into structured per-player, per-over ball data.

    Returns:
    {
        'team': str,
        'skins': {
            1: {
                'pair': [player1, player2],
                'overs': {
                    1: {'bowler': str, 'balls': [delivery, ...]},
                    ...
                },
                'skin_score': int,
                'dismissals': int
            },
            ...
        }
    }
    """
    result = {'team': team_name, 'skins': {}}

    if not table_data:
        return result

    data = table_data['data']
    if not data:
        return result

    # Find the header row (contains over numbers)
    header_row_idx = None
    header_row = None
    for i, row in enumerate(data):
        row_clean = [clean_cell(c) for c in row]
        nums = [c for c in row_clean if re.match(r'^\d{1,2}$', c)]
        if len(nums) >= 8:
            header_row_idx = i
            header_row = row_clean
            break

    if header_row_idx is None:
        print(f"  Warning: Could not find header row in {team_name} table")
        return result

    # Map column index to over number
    col_to_over = {}
    for col_idx, cell in enumerate(header_row):
        if re.match(r'^\d{1,2}$', cell):
            over_num = int(cell)
            if 1 <= over_num <= 16:
                col_to_over[col_idx] = over_num

    # Parse data rows (below the header)
    current_skin = 0
    current_over = 0
    skin_players = {}
    skin_overs = {}

    for row in data[header_row_idx + 1:]:
        row_clean = [clean_cell(c) for c in row]
        if not any(row_clean):
            continue

        # Row label (first non-empty cell) = player name or skin total
        label = next((c for c in row_clean if c), '')

        # Skip summary/total rows
        if re.match(r'^\d+/[\d-]+$', label) or label in ('total', 'totals', ''):
            continue

        # This is a player row — collect their deliveries
        player_name = label
        player_balls = {}

        for col_idx, cell in enumerate(row_clean[1:], 1):
            if col_idx in col_to_over:
                over_num = col_to_over[col_idx]
                delivery = parse_delivery(cell)
                if over_num not in player_balls:
                    player_balls[over_num] = []
                player_balls[over_num].append(delivery)

        if player_balls:
            # Determine which skin this player belongs to
            # Players are grouped in pairs per skin (2 players per 4 overs)
            overs_played = sorted(player_balls.keys())
            if overs_played:
                first_over = overs_played[0]
                skin_num = (first_over - 1) // 4 + 1

                if skin_num not in skin_players:
                    skin_players[skin_num] = []
                if player_name not in skin_players[skin_num]:
                    skin_players[skin_num].append(player_name)

                if skin_num not in skin_overs:
                    skin_overs[skin_num] = {}
                skin_overs[skin_num][player_name] = player_balls

    # Assemble final structure
    for skin_num in sorted(set(list(skin_players.keys()) + list(skin_overs.keys()))):
        players = skin_players.get(skin_num, [])
        overs_data = skin_overs.get(skin_num, {})

        # Calculate skin score
        skin_runs = 0
        skin_dismissals = 0
        for player, over_balls in overs_data.items():
            for over_num, balls in over_balls.items():
                for ball in balls:
                    skin_runs += ball['runs']
                    if ball['type'] == 'wicket':
                        skin_dismissals += 1

        result['skins'][skin_num] = {
            'pair': players,
            'overs': overs_data,
            'skin_score': skin_runs,
            'dismissals': skin_dismissals
        }

    return result


# ── Markdown output ────────────────────────────────────────────────────────────

def format_delivery_md(d: dict) -> str:
    """Format a delivery for Markdown output."""
    if d['type'] == 'dot':
        return '·'
    if d['type'] == 'runs':
        return str(d['runs'])
    if d['type'] == 'wicket':
        codes = {'caught':'c','bowled':'b','runout':'ro','stumped':'st',
                 'lbw':'lbw','hitwkt':'hw','mankad':'m','secondball':'2b'}
        return codes.get(d['subtype'], 'w')
    if d['type'] == 'extra':
        codes = {'noball':'nb','legside':'ls','wide':'wd'}
        return codes.get(d['subtype'], 'ex')
    return d['raw'] or '?'


def batting_grid_to_md(grid: dict, title: str) -> str:
    """Convert a parsed batting grid to a Markdown table."""
    lines = [f"## {title}\n"]

    if not grid['skins']:
        lines.append("_No data extracted_\n")
        return '\n'.join(lines)

    for skin_num in sorted(grid['skins'].keys()):
        skin = grid['skins'][skin_num]
        start_over = (skin_num - 1) * 4 + 1
        end_over = skin_num * 4
        skin_label = f"S{skin_num}"
        pair_label = ' + '.join(skin['pair']) if skin['pair'] else 'Unknown'
        score_label = f"Score: {skin['skin_score']} ({skin['dismissals']} dismissals)"

        lines.append(f"### Skin {skin_num} — Overs {start_over}–{end_over} | {pair_label}")
        lines.append(f"_{score_label}_\n")

        # Build header: Player | O1 B1 | O1 B2 | ... | O2 B1 | ... | Runs | Wkts
        # Simpler: one column per over, cells show all balls space-separated
        over_nums = list(range(start_over, end_over + 1))
        header = '| Player | ' + ' | '.join([f'Over {o}' for o in over_nums]) + ' | RS | Wkts |'
        separator = '|--------|' + '--------|' * len(over_nums) + '-----|------|'
        lines.append(header)
        lines.append(separator)

        for player in skin['pair']:
            player_data = skin['overs'].get(player, {})
            cells = []
            rs = 0
            wkts = 0
            for o in over_nums:
                balls = player_data.get(o, [])
                if balls:
                    cell_str = ' '.join([format_delivery_md(b) for b in balls])
                    for b in balls:
                        if b['type'] == 'runs':
                            rs += b['runs']
                        elif b['type'] == 'wicket':
                            wkts += 1
                else:
                    cell_str = '—'
                cells.append(cell_str)
            lines.append(f'| {player} | ' + ' | '.join(cells) + f' | {rs} | {wkts} |')

        lines.append('')  # blank line between skins

    return '\n'.join(lines)


def summary_stats_to_md(dm_grid: dict, opp_grid: dict, meta: dict) -> str:
    """Generate a summary stats section from the two grids."""
    lines = ["## Summary Stats\n"]

    lines.append("### DM Batting")
    lines.append("| Skin | Pair | Score | Dismissals |")
    lines.append("|------|------|-------|------------|")
    for sn in sorted(dm_grid['skins'].keys()):
        s = dm_grid['skins'][sn]
        lines.append(f"| S{sn} | {' + '.join(s['pair'])} | {s['skin_score']} | {s['dismissals']} |")
    lines.append("")

    lines.append("### Opponent Bowling (from DM batting grid)")
    lines.append("_Per-over breakdown available in batting grid above_\n")

    return '\n'.join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def build_markdown(dm_grid: dict, opp_grid: dict, meta: dict) -> str:
    """Assemble the full Markdown output."""
    season_label = meta.get('season', '').replace('spring', 'Spring ').replace('autumn', 'Autumn ')
    game = meta.get('game', '')
    opponent = meta.get('opponent', 'Unknown')
    date = meta.get('date', '')
    fixture_id = meta.get('fixture_id', '')
    url = f"https://actionsport.spawtz.com/Leagues/IndoorCricket/Scoresheet?FixtureId={fixture_id}" if fixture_id else ''

    sections = [
        f"# {game} · {date} · DM vs {opponent}",
        f"**Season:** {season_label}  ",
        f"**Fixture ID:** {fixture_id}  " if fixture_id else '',
        f"**Scorecard URL:** [{url}]({url})  " if url else '',
        "",
        "---",
        "",
        "## Delivery Key",
        "| Code | Meaning | Runs |",
        "|------|---------|------|",
        "| `·` | Dot ball | 0 |",
        "| `1–6` | Runs scored | face value |",
        "| `7` | Zone D full (back net on the full) | +6 bonus |",
        "| `c` | Caught | −5 |",
        "| `b` | Bowled | −5 |",
        "| `ro` | Run out | −5 |",
        "| `st` | Stumped | −5 |",
        "| `lbw` | LBW | −5 |",
        "| `hw` | Hit wicket | −5 |",
        "| `nb` | No ball | +2 |",
        "| `ls` | Leg side bye | +2 |",
        "| `wd` | Wide | +2 |",
        "",
        "---",
        "",
    ]

    sections.append(batting_grid_to_md(dm_grid, f"DM Batting — vs {opponent}"))
    sections.append("---\n")
    sections.append(batting_grid_to_md(opp_grid, f"{opponent} Batting — DM Bowling"))
    sections.append("---\n")
    sections.append(summary_stats_to_md(dm_grid, opp_grid, meta))

    return '\n'.join(sections)


def main():
    parser = argparse.ArgumentParser(description='Extract DM scorecard from PDF to Markdown')
    parser.add_argument('pdf', help='Path to the scorecard PDF')
    parser.add_argument('--season',   default='unknown', help='Season ID (e.g. autumn2026)')
    parser.add_argument('--game',     default='G?',      help='Game number (e.g. G7)')
    parser.add_argument('--opponent', default='Unknown', help='Opponent team name')
    parser.add_argument('--date',     default='',        help='Match date YYYY-MM-DD')
    parser.add_argument('--fixture',  default='',        help='Spawtz Fixture ID')
    parser.add_argument('--out',      default=None,      help='Output folder (default: ../scorecards/)')
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"Error: PDF not found: {args.pdf}")

    # Output path
    if args.out is None:
        script_dir = Path(__file__).parent
        out_dir = script_dir.parent / 'scorecards'
    else:
        out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_opp = re.sub(r'[^\w]', '_', args.opponent)
    out_file = out_dir / f"{args.season}_{args.game}_{safe_opp}.md"

    print(f"Extracting: {args.pdf}")
    print(f"Output:     {out_file}")

    # Extract
    print("→ Reading PDF tables...")
    tables = extract_tables_from_pdf(args.pdf)
    print(f"  Found {len(tables)} tables")

    if not tables:
        print("  No tables found via pdfplumber. Trying text extraction...")
        pages = extract_text_from_pdf(args.pdf)
        print(f"  Extracted {len(pages)} pages of text")
        print("\nRaw text (first page):\n")
        if pages:
            print(pages[0][:2000])
        print("\nManual parsing required — see SKILL.md for column boundary guidance.")
        sys.exit(1)

    # Identify DM and opponent batting sections
    sections = find_batting_sections(tables)

    meta = {
        'season': args.season,
        'game': args.game,
        'opponent': args.opponent,
        'date': args.date,
        'fixture_id': args.fixture,
    }

    # Parse both grids
    print("→ Parsing DM batting grid...")
    dm_grid = parse_batting_grid(sections.get('dm'), 'Durban Mallus')

    print("→ Parsing opponent batting grid...")
    opp_grid = parse_batting_grid(sections.get('opp'), args.opponent)

    print(f"  DM skins found:  {len(dm_grid['skins'])}")
    print(f"  Opp skins found: {len(opp_grid['skins'])}")

    # Build and write Markdown
    print("→ Writing Markdown...")
    md = build_markdown(dm_grid, opp_grid, meta)
    out_file.write_text(md, encoding='utf-8')

    print(f"\n✅ Done → {out_file}")
    print("\nNext steps:")
    print("  1. Open the MD file and verify the ball-by-ball data")
    print("  2. Cross-check skin scores against the scorecard summary")
    print("  3. Run the 6-ball pair check per over (see SKILL.md)")
    print("  4. Once verified, transfer to player_stats_reference.md")


if __name__ == '__main__':
    main()
