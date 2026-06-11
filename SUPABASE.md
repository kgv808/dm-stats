# Supabase Setup — DM Stats Tracker

This document covers the Postgres/Supabase data layer. The current live site still uses `data/games.json`. This setup is ready to switch to when the time comes.

**Supabase project:** [chswumfxdyjstgsddbhd](https://supabase.com/dashboard/project/chswumfxdyjstgsddbhd)  
**Test frontend:** [kgv808.github.io/dm-stats/index_supabase.html](https://kgv808.github.io/dm-stats/index_supabase.html)

---

## Files

| File | Purpose |
|------|---------|
| `supabase/migrations/20260611000001_initial_schema.sql` | Postgres schema — run once in SQL Editor |
| `data extraction/migrate_to_supabase.py` | One-time seed script — loads all existing data from `games.json` into Supabase |
| `index_supabase.html` | Frontend wired to Supabase instead of `games.json` |
| `index_games_json.html` | Backup of the original `games.json` version |
| `.env.example` | Credential template — copy to `.env` and fill in keys |

---

## Database schema

7 tables:

| Table | Description |
|-------|-------------|
| `seasons` | Season keys and labels |
| `games` | One row per game — scores, skins breakdown, result |
| `players` | Canonical player names (25 players) |
| `player_aliases` | Raw PDF name → canonical player mapping (replaces `NAME_MAP` in aggregate.py) |
| `game_stats` | One row per player per game — RS, RC, Wkts, SR, etc. |
| `pair_stats` | One row per skin per game — batting pair and scores |
| `bowling_data` | One row per over — bowler and runs conceded |

RLS is enabled on all tables. The `anon` key can SELECT only. The `service_role` key has full write access.

---

## One-time setup

### 1. Apply the schema
1. Open the [Supabase SQL Editor](https://supabase.com/dashboard/project/chswumfxdyjstgsddbhd/sql)
2. Paste `supabase/migrations/20260611000001_initial_schema.sql` and run it
3. Then run: `GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;`
4. Then run: `GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;`

### 2. Create your `.env` file
Copy `.env.example` to `.env` and fill in the keys from Supabase → Settings → API Keys:
```
SUPABASE_URL=https://chswumfxdyjstgsddbhd.supabase.co
SUPABASE_SERVICE_KEY=<service_role key — never commit this>
SUPABASE_ANON_KEY=<anon key — safe for client-side use>
```

### 3. Seed existing data
```bash
cd "data extraction"
pip install supabase python-dotenv
python migrate_to_supabase.py
```
Do not run this again — it will conflict with existing rows.

---

## Credential rules

- **`SUPABASE_ANON_KEY`** — safe to hardcode in `index_supabase.html`. It's read-only and RLS-enforced.
- **`SUPABASE_SERVICE_KEY`** — Python scripts only, via `.env`. Never commit to git.

---

## Switching over (when ready)

When you're ready to make `index_supabase.html` the live site:

1. Update the data pipeline (`aggregate.py` / `build_games_json.py`) to write directly to Supabase instead of `games.json`
2. Replace `index.html` with `index_supabase.html`
3. Set up a keep-alive ping at [cron-job.org](https://cron-job.org) to prevent Supabase free tier from pausing (ping `https://chswumfxdyjstgsddbhd.supabase.co` every 3 days)
4. Set up a weekly JSON backup — export all data from Supabase and commit to the repo as a fallback

---

## Free tier limitations

| Limitation | Detail |
|-----------|--------|
| Inactivity pause | Project pauses after 1 week with no requests — set up a cron ping to prevent this |
| No auto-backups | Export data manually or via a scheduled script |
| 500 MB storage | Well within limits for this use case |
| 2 GB bandwidth/month | Well within limits for this use case |
