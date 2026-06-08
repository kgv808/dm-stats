"""
build_games_json.py — Rebuild data/games.json from extracted CSV data
======================================================================
Reads:
  - data extraction/aggregated/dm_player_games.csv   (player stats per game)
  - data extraction/scorecard_urls.csv               (game metadata)
  - data extraction/pdfs/**/*.pdf                    (skin scores per game)
  - data/games.json                                  (existing — preserves seasons)

Writes:
  - data/games.json  (gameStats, games with real skin scores, pairStats)

Usage:
    python "data extraction/build_games_json.py"
"""

import csv
import json
import re
from pathlib import Path
from collections import defaultdict

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("WARNING: pdfplumber not installed — skin scores will be 0")

BASE_DIR    = Path(__file__).parent
GAMES_JSON  = BASE_DIR.parent / 'data' / 'games.json'
URLS_CSV    = BASE_DIR / 'scorecard_urls.csv'
PLAYER_CSV  = BASE_DIR / 'aggregated' / 'dm_player_games.csv'
PDF_DIR     = BASE_DIR / 'pdfs'


def fmt_date(iso: str) -> str:
    months = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']
    y, m, d = iso.split('-')
    return f"{int(d)} {months[int(m)-1]} {y}"


def parse_skin_scores(pdf_path: Path):
    if not PDF_AVAILABLE:
        return None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
    except Exception as e:
        print(f"  WARNING: could not read {pdf_path.name}: {e}")
        return None

    ROW_RE = re.compile(
        r'^(.+?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+'
        r'\((\d+)\s+skins?\)\s+(\d+)$'
    )
    lines = [l for l in text.split('\n') if l.strip()]

    def parse_row(line):
        m = ROW_RE.match(line.strip())
        if not m:
            return None
        return {
            'team':     m.group(1).strip(),
            'skin1':    int(m.group(2)), 'skin2': int(m.group(3)),
            'skin3':    int(m.group(4)), 'skin4': int(m.group(5)),
            'total':    int(m.group(6)),
            'skinsWon': int(m.group(7)),
            'points':   int(m.group(8)),
        }

    row_a = parse_row(lines[3]) if len(lines) > 3 else None
    row_b = parse_row(lines[4]) if len(lines) > 4 else None

    if not row_a or not row_b:
        print(f"  WARNING: skin parse failed for {pdf_path.name}")
        return None

    if 'Durban' in row_a['team']:
        return {'dm': row_a, 'opp': row_b}
    else:
        return {'dm': row_b, 'opp': row_a}


def load_skin_scores() -> dict:
    skin_data = {}
    if not PDF_DIR.exists():
        print("WARNING: pdfs/ folder not found — skin scores will be 0")
        return skin_data

    pdfs = sorted(PDF_DIR.rglob('*.pdf'))
    print(f"Found {len(pdfs)} PDFs")

    for pdf_path in pdfs:
        m = re.search(r'G(\d+)', pdf_path.name)
        if not m:
            continue
        game_id = f"G{int(m.group(1))}"
        result = parse_skin_scores(pdf_path)
        if result:
            skin_data[game_id] = result

    print(f"Parsed skin scores for {len(skin_data)}/{len(pdfs)} games")
    return skin_data



def main():
    with open(GAMES_JSON, encoding='utf-8') as f:
        data = json.load(f)

    with open(URLS_CSV, newline='', encoding='utf-8') as f:
        meta = {row['GameWeek']: row for row in csv.DictReader(f)}

    skin_scores = load_skin_scores()

    # Rebuild games array with real skin data
    fixture_to_game = {r['FixtureID']: r['GameWeek'] for r in meta.values()}
    new_games = []
    for g in data['games']:
        fid = str(g.get('fixtureId', ''))
        game_id = fixture_to_game.get(fid, g.get('game', ''))
        g['game'] = game_id
        sk = skin_scores.get(game_id)
        if sk:
            g['dmSkins']  = sk['dm']['skinsWon']
            g['oppSkins'] = sk['opp']['skinsWon']
            g['points']   = sk['dm']['points']
            g['maxPoints']= sk['dm']['points'] + sk['opp']['points']
            g['dmSkin1']  = sk['dm']['skin1']
            g['dmSkin2']  = sk['dm']['skin2']
            g['dmSkin3']  = sk['dm']['skin3']
            g['dmSkin4']  = sk['dm']['skin4']
            g['oppSkin1'] = sk['opp']['skin1']
            g['oppSkin2'] = sk['opp']['skin2']
            g['oppSkin3'] = sk['opp']['skin3']
            g['oppSkin4'] = sk['opp']['skin4']
        new_games.append(g)
    data['games'] = new_games

    player_games = []
    with open(PLAYER_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            player_games.append(row)

    print(f"Loaded {len(player_games)} player-game records from CSV")

    new_game_stats = []
    for row in player_games:
        game     = row['game']
        date_iso = row['date']
        date_fmt = fmt_date(date_iso) if date_iso else ''
        new_game_stats.append({
            'season':    row['season'],
            'game':      game,
            'date':      date_fmt,
            'dateVal':   date_iso,
            'fixtureId': row['fixtureId'],
            'opponent':  row['opponent'],
            'name':      row['name'],
            'rs':        int(row['rs']),
            'rc':        int(row['rc']),
            'wkts':      int(row['wkts']),
            'contrib':   int(row['contrib']),
            'sr':        float(row['sr']),
            'ob':        int(row['ob']),
            'econ':      float(row['econ']),
            'sevens':    int(row['sevens']),
            'dotsFaced': int(row['dotsFaced']),
            'dotsBowled':int(row['dotsBowled']),
            'extras':    int(row['extras']),
            'dCaught':   int(row.get('dCaught', 0)),
            'dBowled':   int(row.get('dBowled', 0)),
            'dRunOut':   int(row.get('dRunOut', 0)),
            'dStumped':  int(row.get('dStumped', 0)),
        })

    def sort_key(r):
        return (int(r['game'].replace('G', '')), r['name'])

    new_game_stats.sort(key=sort_key)
    print(f"Built {len(new_game_stats)} gameStats entries")

    by_game = defaultdict(list)
    for r in new_game_stats:
        by_game[r['game']].append(r['name'])

    print("\n-- Players per game --")
    for game in sorted(by_game, key=lambda g: int(g.replace('G',''))):
        n = len(by_game[game])
        flag = ' <<<' if n != 8 else ''
        print(f"  {game}: {n} players{flag}")

    if 'pairStats' in data and skin_scores:
        for ps in data['pairStats']:
            sk = skin_scores.get(ps.get('game', ''))
            if not sk:
                continue
            skin_num = ps.get('skin', 1)
            ps['dmRuns']  = sk['dm'][f'skin{skin_num}']
            ps['oppRuns'] = sk['opp'][f'skin{skin_num}']
        print(f"\nUpdated {len(data['pairStats'])} pairStats with PDF skin totals")

    data['gameStats'] = new_game_stats

    with open(GAMES_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nDone: {GAMES_JSON}")
    print(f"  seasons:   {len(data['seasons'])}")
    print(f"  games:     {len(data['games'])}")
    print(f"  gameStats: {len(data['gameStats'])}")
    print(f"  pairStats: {len(data.get('pairStats', []))}")


if __name__ == '__main__':
    main()
