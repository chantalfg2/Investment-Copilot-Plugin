---
name: dashboard-refresh
description: >-
  Refresh a user's multi-account portfolio dashboard from the current month's
  statements. Use whenever the user drops new monthly statements, says
  "refresh the dashboard," "update my portfolio," "I added this month's
  statements," "run the new holdings," or wants the dashboard regenerated —
  even if they don't name it. Aggregates EVERY account in the latest month
  folder (any broker, any format — CSV, PDF, PNG, private holdings), recomputes
  look-through sector weights, current-vs-recommended allocation, concentration
  flags, and per-account filtering, then updates the dashboard output. Also
  use for ad-hoc questions like "what's my tech weight across everything now?"
  or "what does just my 401k look like vs target?" when statements are
  available. Requires portfolio-profile.json — if missing, use the
  portfolio-setup skill first.
---

# Portfolio Dashboard Refresh (multi-account)

Aggregate every account statement in the current month's folder into one
portfolio dashboard. A bundled Python script does the look-through math and
HTML generation; your job is to read each statement (any broker, any format),
write it into one holdings JSON, run the script, and brief the user.

## Context

- **Who:** read from `portfolio-profile.json` (risk tolerance, life stage,
  target allocation, accounts, contributions, constraints) — never assume a
  life stage, risk tolerance, or account lineup.
- **Statements folder:** `holdings/`, organized **one subfolder per month**
  named `Month YYYY` (e.g., `June 2026`). Read `holdings/README.md` — it
  documents the drop convention.
- Any recurring private holding (an SPV, a non-brokerage account) can live at
  the `holdings/` root instead of a month folder if it isn't part of a
  monthly statement drop — read it every run regardless.
- Lead with the bottom line, cite external claims, never fabricate values.

## Workflow

### 1. Find the latest month folder

Pick the most recent `Month YYYY` subfolder (not by filename — by month).
List its contents. Expect a mix of formats — CSVs, PDF statements, PNG
screenshots — from whatever brokers the user's `portfolio-profile.json`
accounts list. Note which accounts are present, and which are missing this
month (say so rather than carrying stale data forward silently).

### 2. Build this month's holdings JSON

**Every account, every format, funnels through one JSON file** —
`manual-accounts.json` in the month folder. There is no automatic CSV parser:
you read each statement natively (CSV, PDF, or PNG — you can read all three
directly) and write one entry per holding, with a **pre-computed `buckets`
dollar map** so the dashboard can aggregate and filter it. See
`references/manual-accounts.example.json` for the full shape:

```json
[
  {
    "account": "401(k)", "broker": "Example Provider",
    "sym": "VMCIX", "name": "Example Mid-Cap Index Fund", "value": 145000.0,
    "gl": 32000.0, "group": "US Value & Size", "source": "401k-statement.pdf",
    "buckets": {"Info Tech": 26100, "Industrials": 22475, "...": 0}
  },
  { "account": "HSA (Example Bank)", "broker": "Example Bank", "sym": "HSA-CASH",
    "name": "HSA Cash", "value": 9200.0, "gl": 0, "group": "Cash",
    "source": "hsa-statement.png", "buckets": {"Cash": 9200.0} }
]
```

Every entry's `source` should name the statement file it came from — the
folder-completeness check in Step 3 uses this to catch a dropped statement
that never made it in.

Rules for `buckets` (every value's dollars must sum to the holding's `value`):

- **Single-sector holding** (a stock or sector ETF): one GICS key, e.g.
  `{"Info Tech": 2329.09}`. Valid GICS keys: Info Tech, Comm Services,
  Cons Disc, Health Care, Financials, Industrials, Cons Staples, Energy,
  Utilities, Real Estate, Materials.
- **International fund** → `{"Intl ex-US": value}`. **Bond fund** →
  `{"Bonds": value}`. **Gold** → `{"Gold": value}`. **Private/illiquid** →
  `{"Private": value}`.
- **Broad US fund** (mid-cap, growth index): spread across GICS using the
  fund's known sector mix — well-known tickers are already in the script's
  `FUND_MAP`; omit `buckets` entirely for those and the script fills it in.
- **Target-date fund**: decompose into bonds + intl + US-equity-by-sector. A
  20-yr TDF is roughly 90% equity / 10% bonds, equity roughly 60% US / 40%
  intl. Apply that split, then spread the US slice across GICS via S&P
  weights.
- **Cost basis / gain:** if the statement gives a total gain, apportion it
  across that account's holdings by value share. Flag it as approximate.

Sanity check before running: each holding's buckets sum to its value, and
each account's holdings sum to the statement's stated total.

### 3. Run the aggregator

```bash
python3 <skill-dir>/scripts/build_dashboard.py \
  --profile "<project>/portfolio-profile.json" \
  --accounts "<project>/holdings/<Month YYYY>/manual-accounts.json" \
  --assumptions "<project>/market-assumptions.json" \
  --dir "<project>/holdings/<Month YYYY>" \
  --out /tmp/portfolio-dashboard.html \
  --metrics "<project>/dashboards/<YYYY-MM>-metrics.json" \
  --note "<Month YYYY> statements"
```

`--assumptions` is optional — omit it to use the plugin's shipped default
market assumptions. `--dir` doesn't parse anything; it only turns on the
folder-completeness check described below, so pass it whenever you have a
month folder to check against.

Read stdout. It prints a per-account table and a TOTAL, plus **WARNINGS** for:

- **Bucket mismatches** — a holding's `buckets` don't sum to its `value`;
  every downstream percentage involving it will be wrong until fixed.
- **Folder completeness** (only runs when `--dir` is passed) — flags any
  statement file in the month folder that no holding's `source` tag
  references, i.e. a statement that never made it into `manual-accounts.json`.

### 4. Sanity-check the aggregation

- Does the grand total match the sum of each account's statement total?
- Do international and bonds look right? A 401(k) heavy in target-date/EM/TIPS
  funds will pull both up a lot — that's expected, not a bug.
- Any account auto-classified into "US Broad" by surprise usually means a
  fund fell through to the fallback — give it an explicit `buckets` entry.

### 5. Publish the dashboard

If this environment has a way to publish/update a live, shareable dashboard
view (e.g. an Artifact), update it in place using the generated HTML and a
one-line summary of what changed. Otherwise, the HTML file written to
`dashboards/<YYYY-MM>-dashboard.html` is the deliverable — point the user at
it directly.

The dashboard has an **account filter** (chips at the top) — every view
recomputes for the selected accounts. The holdings table also groups **by
account** or by sector group.

### 6. Dispatch market research on the largest flagged gap

If a market-research agent/skill is available in this environment, dispatch
it against the single largest current-vs-`recommendedAllocation` gap or
concentration flag from this month's metrics — e.g. if international is
5.5pp overweight, give it the sector/theme angle "international ex-US
developed equity — is the current overweight still justified." It should
return a sourced industry overview and an ideas shortlist for that gap area.

- This is independent research to sanity-check the gap, not a proofread of
  the dashboard's numbers.
- If the research turns up something worth keeping, append it to the
  project's `sector-research.json` (starts as `[]`) rather than hand-editing
  it into the script — the next `--sector-research` run will pick it up.
  These cards render as "What's Moving Your Portfolio" in the Portfolio
  Snapshot tab. Each entry:
  ```json
  {
    "name": "Short sector/theme label",
    "tone": "tailwind | mixed | headwind",
    "color": "#1f7a43",
    "asof": "2026-09",
    "headline": "One factual, sourced sentence — the finding itself.",
    "sowhat": "One sentence tying it back to this portfolio's actual holdings.",
    "sources": [["Source name", "https://..."]]
  }
  ```
  `color` should match the tone (green-ish for tailwind, amber for mixed,
  red-ish for headwind) — see existing cards for exact hex values, or reuse
  one of the amber/moss/rust CSS tokens already in the script's theme.
- Only surface it in Step 7 if it changes the read or turns up a name worth
  flagging. Skip silently if it just confirms the status quo.
- Skip this step entirely if no research capability is available, or the gap
  is immaterial (<1pp on every dimension).

### 7. Brief the user — lead with what changed

Compare to last month (pull the prior `dashboards/<YYYY-MM>-metrics.json`).
Cover total value and MoM change, the big allocation reads (tech, intl % of
equity, bonds) vs targets, any account that moved materially, and one
recommendation if a gap widened. Note any account missing from this month's
folder, and anything material from Step 6's market research. Keep it tight.

## Momentum trend — check for gaps before every run

The "Momentum — Is It Working?" panel reads every
`dashboards/<YYYY-MM>-metrics.json` file that exists — it does NOT know how
many months of statements are sitting in `holdings/`. If a `Month YYYY`
folder exists under `holdings/` but has no matching `<YYYY-MM>-metrics.json`
in `dashboards/`, that month was never actually run through this script, and
the trend panel will silently start later than it should.

**Before relying on the momentum panel's date range, or whenever asked to
extend how far back it shows**, compare `ls holdings/` (month folders)
against `ls dashboards/*-metrics.json` (built months). Backfill any gap by
building that old month exactly like a current one — Step 3's command,
`--metrics` pointed at that month's own `dashboards/<YYYY-MM>-metrics.json`
— from files that already sat in its folder; that's not fabrication, it's
the same statement-based build as the current month, just run late.

**`valueMarks` (in `portfolio-profile.json`) are dated, and that matters most
on a backfill.** Each mark carries an `effectiveMonth` field, and the script
skips it for any month before that. Never delete or backdate `effectiveMonth`
on an existing mark — a backfilled month should reflect what the account was
actually worth *then*, not a judgment call made months later. When you add a
new mark, set `effectiveMonth` to the month you're deciding it in — otherwise
re-running an older month would wrongly apply it too.

## Adding/maintaining classifications

- **Well-known tickers** auto-map via `FUND_MAP` in the script (VTI, SPY,
  QQQ, and similar broad ETFs). A new permanent one worth adding → add an
  entry there (match the existing shape: asset, group, look-through sectors).
  Anything account-specific or less common should just carry an explicit
  `buckets` map in `manual-accounts.json` instead.
- **Recommended-model targets** (`recommendedAllocation` in
  `portfolio-profile.json`) are a fixed strategic target for the whole
  portfolio; change only if the user's strategy changes, and note why.
- **`valueMarks`/`forecastOverrides`/`concentrationWatch`/`goals`** all live
  in `portfolio-profile.json`, never in the script — see
  `references/portfolio-profile.example.json` for the shape of each.
- **`marketBenchmark`** (in `market-assumptions.json`) is an optional market
  index return (e.g. S&P 500) the Momentum panel compares your organic
  growth against. Update it by hand periodically — same cadence as
  `sectorGrowth`/`analystAggressiveWeights` in the same file, or whenever
  Step 6's market research gives you a fresher read. Leave `asof` empty to
  turn the comparison off entirely; the dashboard skips it gracefully rather
  than showing a bogus "0% over an empty period" line.

## What not to do

- Don't fabricate values you can't read off a statement — flag instead.
- Don't double-count: the same account appearing in two statements is one
  account, one entry.
- Don't silently drop an account because its format is awkward — extract it
  into `manual-accounts.json` and say what you assumed.
- Don't hand-edit personal targets, contributions, or narrative text into
  `build_dashboard.py` — it all belongs in `portfolio-profile.json`.
