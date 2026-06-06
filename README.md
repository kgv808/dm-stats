# 🏏 Durban Mallu's — Season Stats Tracker

A self-hosted web app for tracking player statistics, results, and performance across seasons for the **Durban Mallu's** indoor Action Cricket team.

🔗 **Live site:** [kgv808.github.io/dm-stats](https://kgv808.github.io/dm-stats)

---

## What's inside

| Tab | What it shows |
|-----|--------------|
| **Insights** | Season summary, last game result, highlights, ladder standings, head-to-head records |
| **Results** | Full match history with scores, skins points, and result badges |
| **Player Stats** | Season aggregates (RS, RC, Wkts, Contribution) + Detailed Stats (SR, 7s, Dots Faced/Bowled, Extras) |
| **Pairs & Bowling** | Batting pair records by skin, bowling performance heatmap |
| **Team Sheet** | Pre-match squad selector with auto-generated batting pairs and bowling order |

Covers two seasons:
- **Spring 2025** — C3 Division · Fourways Falcons
- **Autumn 2026** — C1 Division · Hillfox Action Sports

---

## File structure

```
dm-stats/
├── index.html        # The tracker app — only change this for UI updates
└── data/
    └── games.json    # All game data — update this after every new game
```

---

## Adding a new game

All game data lives in `data/games.json`. After each match, update this file with the new game's stats. The app loads it fresh every time the page opens — no rebuild needed.

The JSON has five sections:

- **`games`** — one entry per match (date, opponent, scores, skins, result, points)
- **`gameStats`** — one entry per player per match (RS, RC, Wkts, Contrib, SR, 7s, DF, DB, Extras)
- **`seasons`** — season metadata (label, division, venue)
- **`pairsData`** — batting pair records per skin per match
- **`bowlingData`** — bowling performance per over per match

After updating `games.json`, commit and push via GitHub Desktop — the live site updates within ~60 seconds.

---

## Stat definitions

| Stat | Meaning |
|------|---------|
| **RS** | Runs Scored |
| **RC** | Net Runs Conceded (gross runs − wicket credits; can be negative) |
| **Wkts** | Wickets taken |
| **C** | Contribution = RS − RC |
| **SR** | Strike Rate = (RS ÷ balls faced) × 100 |
| **7s** | Zone D full hits (back net, on the full = 6 bonus runs) |
| **DF** | Dots Faced — deliveries where the batter did not score |
| **DB** | Dots Bowled — deliveries where the bowler did not concede |
| **Ex** | Extras given (No Balls + Wides + Legsides, each worth +2 to batting team) |

> **RC note:** This platform's economy can go negative — a bowler who takes wickets worth more than the runs they concede ends up with a negative RC. This is correct behaviour, not an error.

---

## Tech

- Vanilla HTML, CSS, JavaScript — no frameworks, no build step
- [Chart.js](https://www.chartjs.org/) for data visualisation
- [Google Fonts](https://fonts.google.com/) — Bebas Neue + DM Sans
- Hosted on [GitHub Pages](https://pages.github.com/) (free)

---

## Season records

| Season | Division | Venue | P | W | L |
|--------|----------|-------|---|---|---|
| Spring 2025 | C3 | Fourways Falcons | 6 | 4 | 2 |
| Autumn 2026 | C1 | Hillfox Action Sports | 13 | 7 | 6 |
