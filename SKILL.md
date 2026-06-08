# DM Stats Tracker — Project Intelligence & Analytics Guide

This file is read by Claude at the start of every working session. It describes the actual
project structure, the full data model, what has been built, what the data can support, and
specific analytics features that are implementable from existing data.

---

## Project Structure (current state)

```
dm-stats/                              ← GitHub repo (kgv808/dm-stats)
├── index.html                         ← Main tracker app (7 tabs, loads from games.json)
├── data/
│   └── games.json                     ← App data source — rebuilt by build_games_json.py
├── scorecards/
│   └── index.html                     ← Scorecard archive (Spawtz links per game)
├── data extraction/                   ← Local pipeline — NOT in repo
│   ├── extract_scorecard.py           ← PDF → per-game balls.csv + stats.csv
│   ├── run_all.py                     ← Batch runner
│   ├── aggregate.py                   ← CSVs → aggregated CSVs
│   ├── build_games_json.py            ← Aggregated CSVs → data/games.json
│   ├── scorecard_urls.csv             ← Game metadata (19 games)
│   ├── csv/                           ← 19 × _balls.csv + 19 × _stats.csv
│   └── aggregated/
│       ├── dm_player_games.csv        ← 152 rows (19 games × ~8 players)
│       ├── dm_player_season.csv
│       └── dm_player_alltime.csv
├── SKILL.md                           ← This file
├── README.md
├── DEPLOY.md
└── .gitignore
```

**Live site:** https://kgv808.github.io/dm-stats/

---

## Data Model — What Exists and Where

### games.json (loaded by app via fetch)

**`games[]`** — one row per match (19 games):
```
season, game (G1–G19), date, dateVal (ISO), opponent, dmScore, oppScore,
dmSkins, oppSkins, result (win/loss), points, maxPoints, fixtureId,
dmSkin1, dmSkin2, dmSkin3, dmSkin4,   ← DM net skin scores (from PDF)
oppSkin1, oppSkin2, oppSkin3, oppSkin4 ← Opponent net skin scores (from PDF)
```

**`gameStats[]`** — one row per DM player per match (152 rows):
```
season, game, date, dateVal (ISO), fixtureId, opponent, name,
rs, rc, wkts, contrib, sr, ob, econ,
sevens, dotsFaced, dotsBowled, extras,
dCaught, dBowled, dRunOut, dStumped    ← dismissal type counts
```
- `sevens` = Zone D full hits (delivery_raw == '7') — the 7-run back-net-on-the-full shot
- `dotsFaced` = deliveries DM batter received where runs == 0 and delivery_type == 'runs'
- `dotsBowled` = deliveries DM bowler sent where opponent scored 0
- `extras` = extras DM batters received while batting (nb, ls, w)
- `rc` = NET runs conceded (gross runs − wicket credits; each wicket = −5)
- `econ` = rc / ob (can be negative for good bowlers — this is correct)

**`pairStats[]`** — one row per DM batting pair per skin per game (76 rows):
```
game, season, date, opponent, result, skin (1–4),
pair (string), batters (array of 2 canonical names),
dmRuns, dmWickets,  ← DM batting totals from PDF skin scores
oppRuns             ← Opponent batting total from PDF skin scores
```

**`seasons[]`** — Spring 2025 (C3, Fourways), Autumn 2026 (C1, Hillfox)

### balls.csv — The Rich Source (19 files, not yet fully utilised)

Columns per delivery row:
```
season, game, date,
batting_team, bowling_team,
skin (1–4), pair (e.g. "Nithin & Chibin"),
batter, bowler,
over (1–16, global within team batting innings), ball (1–6),
delivery_raw, delivery_type, delivery_sub, runs
```

**delivery_raw values and meanings:**
| Value | Meaning | delivery_type |
|-------|---------|---------------|
| `0` | Dot ball | runs |
| `1`–`6` | Runs scored | runs |
| `7` | Zone D full hit (6 bonus + 1 physical = 7 total) | runs |
| `8` | Zone hit variant (rare, likely data entry) | runs |
| `nb`, `nb1`–`nb7` | No ball (+ any runs off it) | extra |
| `ls`, `ls1` | Leg side bye (+ any runs) | extra |
| `w1` | Wide + 1 run | extra |
| `w` | Wicket — caught | wicket |
| `c` | Wicket — caught (alternate notation) | wicket |
| `b` | Wicket — bowled | wicket |
| `r`, `ro` | Wicket — run out | wicket |
| `s`, `st` | Wicket — stumped | wicket |

**Critical**: `delivery_type` disambiguates — always filter on this, not just delivery_raw.
A `w` with `delivery_type == 'wicket'` is a caught dismissal, not a wide.
Wides appear as `w` or `w1` with `delivery_type == 'extra'`.

**What balls.csv gives us that gameStats doesn't:**
- Ball position within the over (ball 1–6) → wicket timing, second ball situations
- Skin number (1–4) → skin-level scoring, which skin each player bats in
- Pair name → partnership analysis from raw data
- Over number within skin (1–4) → over-by-over scoring within a skin
- Bowler name for DM batting overs → matchup analysis

### scorecard_urls.csv

```
Season, SeasonLabel, GameWeek, Date, Opponent, Result, DMScore, OppScore, FixtureID, URL, PDFAvailable
```

---

## Current App Features (7 tabs)

| Tab | What it shows | Data source |
|-----|---------------|-------------|
| Insights | Last game card, highlights, head-to-head records | `games[]` from games.json |
| Results | Full match history with scores and results | `games[]` from games.json |
| Player Stats | 3 sub-tabs: Core Stats, Batting & Bowling, Dismissals | `gameStats[]` from games.json |
| Rankings | Leaderboard cards — batting, bowling, dismissals | `gameStats[]` from games.json |
| Form | Last 5 games per player, trend indicators | `gameStats[]` from games.json |
| Pairs & Bowling | Batting pair records, bowling heatmap | `pairsData[]` from games.json, `bowlingData[]` hardcoded |
| Team Sheet | Squad selector, pair builder, match day sheet | Derived from `gameStats[]` |

**Remaining hardcoded data:** `bowlingData[]` (per-over bowling breakdown) is still hardcoded
in index.html. Computing it from balls.csv is blocked by a data gap: the PDF extractor does
not capture extras for opponent batting overs, causing per-over rc totals to be systematically
wrong (~7–21 runs short per skin). Fix requires updating extract_scorecard.py to capture extras.

---

## Action Cricket Rules That Directly Affect Analytics

### The Second Ball Rule — Most Impactful Batting Metric
Every dot ball (delivery_raw == '0') immediately puts the batter at risk. The very next
legal delivery must score runs — if it doesn't, the batter is dismissed (-5 runs).
No Balls, Wides, and Legsides reset the count (they are not dot balls for this rule).

**Why this matters for analysis:** A player facing many dots isn't just unproductive —
they are actively creating dismissal risk every ball. The Second Ball situation rate is
the most tactically meaningful batting pressure indicator in Action Cricket.

### Dismissals Don't Remove the Batter
A dismissed batter continues batting. Each dismissal = -5 runs deducted from the skin total.
Runs scored on the dismissal delivery don't count.
This means a player's RS from the scorecard already excludes dismissal-ball runs.

### Zone D Full Hit = 7 Total Runs
delivery_raw == '7'. Ball reaches back net on the full.
6 bonus runs + 1 physical run = 7 total. Physical run MUST be completed — if batter
is run out on the cross, the 7 runs are void and a -5 dismissal applies instead.

### Skins: 4 Overs per Pair
Each skin (1–4) is contested between corresponding pairs. Higher net skin score wins 1 point.
Tied skin = jackpot (carried to next skin or backward from last skin).
This means skins points are often MORE important than the overall win margin for ladder position.

### Bowler Cannot Bowl Consecutive Overs
Within any skin, a bowler cannot bowl overs back to back. Penalty: -5 per violation.
This constrains bowling rotation and means each player bowls exactly 2 overs spread
across the 4-over skin (e.g. overs 1 and 3, or overs 2 and 4).

### RC and Economy Are Net (Post Wicket Credits)
Each wicket a bowler takes subtracts 5 from their RC. Econ = RC / OB.
Good bowlers show negative economy. This is correct and non-standard vs traditional cricket.
Always label whether a stat is gross (raw runs) or net (after wicket credits).

---

## Analytics: What the Current Data Can Support

All features below are implementable from existing balls.csv files without new PDF extractions.
They require pipeline additions (new fields in games.json) or direct calculation in the app.

### TIER 1 — High value, straightforward to build

**1. Second Ball Situation Rate per Player**
Count dot balls faced by each DM batter per game (already have as `dotsFaced`). 
The rate of dots per game is already surfaced. What's missing: sequential dot ball analysis 
(was the dot followed by a score or a dismissal?).
Requires: scanning consecutive rows in balls.csv for same batter, same skin.
Stat: `secondBallRate = dots / ballsFaced`, `secondBallDismissals = count`.

**2. Wicket Type Breakdown** ✅ DONE
dCaught, dBowled, dRunOut, dStumped now tracked in gameStats and displayed in the
Dismissals sub-tab of Player Stats. Run-Out Risk and Second Ball Pressure leaderboard
cards added to Rankings tab.

**3. Skin Position Assignment per Player**
From balls.csv: which skin (1–4) does each player consistently bat in?
Skin 1 opener vs Skin 4 anchor are very different roles.
Add to Player Stats or Rankings for context.

**4. Over-by-Over Scoring Heatmap (Within Skin)**
Within a skin (4 overs), which over (1–4) does DM score most?
Over 1 = opener under pressure; Over 4 = death over.
Can show as a team heatmap or per-pair.

**5. Head-to-Head vs Repeat Opponents**
We face Akkerkop Arende 4×, Duck Hunters 3×, Toenails 2×, Gravel Donkeys 2×.
Per-player performance split by opponent is meaningful for team selection vs known opponents.
Already have opponent in gameStats — pure JS calculation.
Add to Insights tab or Rankings.

**6. Season Comparison (Spring 2025 vs Autumn 2026)**
Per player: how have their stats changed between seasons?
Already have both seasons in gameStats. Pure JS — radar/spider chart or side-by-side table.
Meaningful for identifying players in form vs decline.

### TIER 2 — High value, needs pipeline extension

**7. Dismissal Timing by Ball Position**
From balls.csv: filter DM batting wickets, group by `ball` column (1–6).
Shows which ball in the over DM batters get out most often.
Ball 1 dismissals = aggressive starters caught early.
Ball 2 dismissals = Second Ball dismissals (the most costly pattern).
Add `dismissalsByBall` dict to gameStats via aggregate.py.

**8. Scoring Distribution per Player**
Per batter, count delivery_raw values: how many 0s, 1s, 2s, 3s, 4s, 5s, 6s, 7s?
Reveals batting profile: conservative (lots of 1s/2s), aggressive (lots of 4s/5s/7s),
or wasteful (lots of 0s). Already partially covered by dotsFaced and sevens.
Add `scoringDist: {0:n, 1:n, 2:n, ...}` to gameStats.

**9. Pair Skin Totals** ✅ DONE (via PDF, not balls.csv)
`pairStats[]` is now in games.json. dmRuns/oppRuns come from PDF skin score parsing
(not balls.csv — balls.csv misses extras for DM batting). pairsData in the app
is now loaded dynamically from pairStats. bowlingData per-over rc still hardcoded —
see note in app features table above.

**10. Effective Economy per Bowler (Gross + Extras)**
Currently econ is net (after wicket credits). Effective economy = raw runs conceded
+ (extras × 2) / overs bowled. A bowler who gives lots of no-balls is more expensive
than their net economy suggests. Add `grossRC` and `extrasGiven` to gameStats.

### TIER 3 — Useful once Tier 1 & 2 are done

**11. Win Correlation per Player**
Which player's above-average performances most correlate with team wins?
When Zayd scores 25+, how often does DM win? Pure JS from gameStats + games result.

**12. Clutch Skin Analysis**
Skin 4 (overs 13–16) is highest pressure — often decides close games.
Which pairs / players perform best in Skin 4? Needs skin assignment from balls.csv (Tier 2 item 9).

**13. Bowler Matchup Profiling**
From balls.csv: which opponent bowlers does each DM batter score best against?
We have `bowler` in balls.csv for DM batting overs. Meaningful for game planning.
Requires a new data pass — bowler names are raw PDF text (not normalised).

---

## What the Data Cannot Currently Support

These require new data collection — not implementable from existing CSVs:

- **Zone distribution (A/B/C/D)** — zone is inferred from run value but not explicitly recorded.
  delivery_raw '7' = Zone D full, '4' or '5' = likely Zone D bounce, but not confirmed.
  Would need scorecard annotation to be reliable.
- **Balls faced accurately** — the balls.csv has per-ball rows but some deliveries may be
  missing if the PDF extraction missed them. SR from stats.csv (platform-calculated) is more
  reliable than counting from balls.csv.
- **Physical runs vs zone bonus split** — not separable from current data.
- **Jackpot skin tracking** — tied skins and jackpot resolution not in current data.

---

## Pipeline: Adding a New Game

1. Download PDF from Spawtz, save to `data extraction/pdfs/[season]/`
2. Add row to `data extraction/scorecard_urls.csv`
3. Run:
   ```
   python "data extraction/run_all.py"
   python "data extraction/aggregate.py"
   python "data extraction/build_games_json.py"
   ```
4. Commit `data/games.json` → push → site updates in ~60 seconds

The `extract_scorecard.py` reads PDFs via pdfplumber and outputs:
- `*_stats.csv` — summary stats per player per game (rs, sr, ob, rc, wkts, econ, c)
- `*_balls.csv` — ball-by-ball delivery log with skin, over, ball position

Name normalisation is in `aggregate.py → NAME_MAP`. 42 PDF variants → 25 canonical names.
If a new name appears that isn't in NAME_MAP, it will be silently dropped. Check output counts.
`GAME_OVERRIDES` in aggregate.py handles per-game exceptions — currently G2 where `Kiaran N`
maps to `Kiran Ninan` (not `Kiran Varghese`), the one game both Kirans played simultaneously.

---

## What Claude Should Do When Asked to Build New Analytics

1. **Check which tier the feature falls into** (Tier 1 = pure JS, Tier 2 = needs pipeline work).
2. **For Tier 1 features**: work directly in index.html. The `gameStats[]` array is loaded
   from games.json and available in all render functions. Use `activeSeason` for season filter.
3. **For Tier 2 features**: first add computation to `aggregate.py`, expose the new field in
   `build_games_json.py`, then wire it up in index.html. Verify with a sample print before writing JSON.
4. **Don't surface stats that can't be reliably computed** — flag the data gap and explain
   what would be needed to fill it.
5. **Always respect Action Cricket rules in metric definitions** — particularly: RC is net
   (wicket credits subtracted), econ can be negative, dot balls have immediate dismissal risk,
   skins points matter as much as win/loss.
6. **Surgical edits to index.html** — use Python string replacement. Test that the target
   string is unique before replacing. Don't regenerate the whole file.

---

## Player Reference

**Core squad (appear in 5+ games):**
Zayd, Amir, Akhil, Arun, Ashwin, Kiran Varghese, Nithin Thomas, Chibin, Shaun, Zach, Yusuf

**Occasional (1–4 games):**
Aaron, Alex, Don, Dony, Godfrey, Goukol, Jesse, Kiran Ninan, Merlin, Nandu, Nithin G, Vijay, Vinay, Vishnu

**Seasons covered:**
- Spring 2025 (G1–G6): Fourways Falcons, C3 Division
- Autumn 2026 (G7–G19): Hillfox Action Sports, C1 Division

**Season records:**
- Spring 2025 (G1–G6): 4W 2L
- Autumn 2026 (G7–G19): 5W 8L

**Repeat opponents (meaningful sample size):**
- Akkerkop Arende: 4 games (G8, G12, G14, G19) — DM record: 1W 3L
- Duck Hunters: 3 games (G10, G15, G18) — DM record: 2W 1L
- Toenails: 2 games (G1, G6) — DM record: 2W 0L
- The Gravel Donkeys: 2 games (G2, G4) — DM record: 1W 1L
