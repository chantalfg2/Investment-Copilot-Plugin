---
name: monthly-brief
description: Conduct monthly investment research and produce a structured top-5 brief calibrated to the user's portfolio gaps, risk tolerance, and current macro conditions. Use when running the monthly investment analysis (manually or via scheduled task). Requires portfolio-profile.json and a current-month dashboard refresh — if either is missing, run portfolio-setup or dashboard-refresh first.
---

# Monthly Investment Brief Skill

## Purpose

Produce a high-rigor, recommendation-led monthly investment brief with 5
ranked picks tailored to the user's actual situation — read every one of the
following from `portfolio-profile.json` and the current month's
`portfolio-context.md`, never assume specifics:

- Life stage, risk tolerance, and investment horizon
- Current sector/geography exposure and gaps vs. `recommendedAllocation`
  (re-derive the gap ranking fresh each run — don't assume last month's
  direction still holds; a rebalance or contribution change can flip a gap
  from underweight to overweight)
- Vehicle preference (ETF-first vs. individual stocks) and max funds/month
- Standing constraints (e.g., sector/geography exclusions)

---

## Mandatory Pre-Flight (do these BEFORE research)

### Phase 0 — Confirm Holdings Are Current

This skill does not parse statements itself — `dashboard-refresh` is the
single source of truth for holdings and exposures now.

1. **Check that `dashboard-refresh` already ran this month**: does
   `dashboards/<YYYY-MM>-metrics.json` exist for the current month, and does
   `portfolio-context.md`'s "Last updated" match it?
2. **If not**, invoke the `dashboard-refresh` skill first, then continue.
3. **Read `portfolio-context.md`** Sections 2 (Current Holdings) and 3
   (Current Exposures) — already refreshed, don't re-derive them here.
4. **Validate**: if the parsed total portfolio value differs >20% from prior
   month with no obvious deposit/withdrawal, flag for review before
   proceeding (this should already have surfaced during dashboard-refresh —
   don't silently re-trust a number that looked wrong there).

### Phase 0.5 — Read Refreshed Context

Read `portfolio-context.md` and `portfolio-profile.json` and extract:
- Current holdings + exposures
- This month's investment amount (Section 1 of `portfolio-context.md`)
- Sector/geo gaps vs. `recommendedAllocation`
- Standing preferences and any month-specific constraints (Sections 4–5)
- Last month's picks (avoid recommending the same picks two months in a row
  unless conviction has materially increased)

**Confirm research mode is active** — web search must be available.
**Check today's date** — every data point in the brief must be ≤7 days old
or flagged as stale.

If `portfolio-context.md` Section 1 (monthly amount) is empty, STOP and
surface this to the user — that's the one thing the dashboard refresh can't
infer on its own.

---

## Research Methodology (MECE)

Run these phases sequentially. Each phase produces an artifact that feeds
the next.

### Phase 1 — Macro Scan (15–20 min)

Cover four buckets, each with 2–3 most recent and material developments:

1. **Geopolitics** — armed conflicts, trade relations, sanctions, election outcomes affecting markets
2. **US Economy** — Fed policy, inflation prints, employment, GDP, yield curve, consumer health
3. **Global Economy** — China, EU, Japan, EM growth signals, commodity cycle, FX
4. **US Policy** — tariffs, tax, regulation (financial services, healthcare, energy, tech), fiscal/deficit posture

Sources to consult: Bloomberg, Reuters, FT, WSJ, Yahoo Finance, Fed releases, IMF/OECD updates, Morningstar market commentary.

**Output:** Bullet summary, 4–6 lines per bucket, each line cited with source + date.

### Phase 2 — Sector & Geography Gap Analysis (5–10 min)

Cross-reference the macro scan against `portfolio-context.md`:
- Which sectors/geos are macro tailwinds aligned with the user's gaps?
- Which gaps are too large to ignore even in face of macro headwinds?
- Output a 2x2: tailwind strength vs. portfolio gap size. Top-right quadrant = priority hunting ground.

### Phase 3 — Candidate Screen (20–30 min)

Generate **15–20 candidates** across the priority quadrants:
- 70% ETFs / 30% individual stocks (adjust based on conviction)
- Mix: international developed, EM, sector-specific (avoiding whatever
  sector the user is already over-exposed in), thematic (e.g., infrastructure,
  defense, healthcare innovation)

For each candidate, capture from analyst sources:
- Ticker, name, expense ratio (if ETF), AUM
- Top 10 holdings (for ETFs) or core thesis (for stocks)
- Trailing 1Y, 3Y, 5Y returns
- Recent analyst rating consensus (Morningstar, Yahoo Finance analyst page, Bloomberg if accessible)
- Forward catalysts and known risks
- Dividend yield (informational, not weighted heavily for growth focus)

### Phase 4 — Score on MECE Rubric (15 min)

Use `scoring-rubric.md`. Each candidate scored 1–5 on six dimensions:
1. **Fit-to-portfolio** — does it close a gap or duplicate existing exposure?
2. **Growth potential** — forward earnings/revenue trajectory, secular tailwinds
3. **Risk profile** — volatility, drawdown, concentration risk vs. the user's stated risk tolerance
4. **Valuation** — P/E vs. peers, ETF premium/discount, current entry point quality
5. **Macro tailwinds** — alignment with Phase 1 scan
6. **Analyst consensus** — strength and recency of coverage

Total = sum (max 30). Top 5 advance to the brief.

### Phase 5 — Self-Verification (5 min, MANDATORY)

Before drafting the brief, run this checklist:
- [ ] Every claim has a source with a retrieval date ≤7 days old
- [ ] Top 5 collectively address the user's stated gaps (sector + geo coverage)
- [ ] No more than 1 of top 5 is in a sector where the user is already over-exposed
- [ ] At least 2 of top 5 are international (developed or EM), unless the
      current exposure data shows international is already at or above target
- [ ] Risk profile of any "aggressive" pick is justified by upside, not just hype
- [ ] No pick recommended last month is in top 5 unless thesis has strengthened (note this in justification)

If any check fails, revise the top 5 before drafting.

---

## Brief Output Specification

Format: **Microsoft Word (.docx)**. Save to `../briefs/YYYY-MM-investment-brief.docx`.
Discover a docx-authoring capability available in this environment (e.g. a
`docx` skill) and invoke it by name via the `Skill` tool — never hardcode a
filesystem path to it, since it won't exist on another install. If no
docx-authoring capability is available, fall back to `.md` per the failure
modes below.

### Required Structure

**Page 1: Executive Summary**
- Title: "Monthly Investment Brief — [Month YYYY]"
- 3–4 sentence "bottom line" — top recommendation, key macro context, suggested allocation across top 3
- **Summary table** with all 5 picks (columns: Rank, Ticker, Name, Type [ETF/Stock], Sector/Geo, Total Score, One-Line Thesis)

**Page 2: Macro Context (1 page)**
- 4 buckets from Phase 1, condensed to 3–4 bullets each, with cited sources

**Pages 3–7: Pick Deep Dives (1 page each, ranked 1–5)**

For each pick:
- **Header**: Rank #X — [Ticker] [Name]
- **Description** (3–4 sentences): what it is, what it holds, why it exists
- **Benefits** (4–6 bullets): why it earns the rank — tied to MECE scoring dimensions
- **Watchouts** (3–5 bullets): risks, counter-thesis, what would invalidate the pick
- **Justification for ranking** (2–3 sentences): why this position vs. picks above/below
- **Key data**: expense ratio, AUM, 1Y/3Y/5Y return, current price, analyst consensus rating
- **Sources** (footer): bulleted list of citations with retrieval date

**Page 8: Suggested Allocation**
- If 3-fund scenario: which top 3 + suggested split (rationale tied to portfolio gaps)
- If 2-fund scenario: top 2 + split
- If single-fund scenario: top pick

**Page 9: What Changed Since Last Month**
- Compare to prior brief (read `../briefs/` for most recent prior file if exists)
- Note: macro shifts, picks dropped, picks repeated, conviction changes
- Skip if first run

---

## Notification Step (post-save)

After saving the .docx, per the schedule configured for this skill:

1. **Create a calendar event** (if a calendar tool is available in this
   environment):
   - Title: "Investment Brief Ready – [Month YYYY]"
   - Description: "Brief saved to <project>/briefs/YYYY-MM-investment-brief.docx — top pick: [TICKER]"
   - 15-min popup reminder

2. **Create an email draft** (if an email tool is available) to
   `profile.notifications.email` (from `portfolio-profile.json`):
   - Subject: "Monthly Investment Brief Ready — [Month YYYY]"
   - Body: Executive summary (the page-1 bottom line) + summary table in HTML + file path
   - This sits in Drafts as a pseudo-notification; the user opens their inbox and sees it.

3. **Surface to user in chat**: present the .docx file with summary.

---

## Failure Modes & Recovery

- **Web search returns stale or low-quality data** → flag explicitly in brief, lower confidence rating, suggest user run again in 2–3 days
- **`portfolio-context.md` missing or empty** → halt, prompt user to fill it in (or run `portfolio-setup`)
- **docx generation fails, or no docx capability is available** → fall back to .md output, surface the issue, save both
- **Calendar/email tool fails or is unavailable** → save brief anyway, note in chat which notification step failed
- **Conflicting macro signals** → present 2 scenarios in macro section (bull vs. bear), have picks robust across both

---

## Style Rules

- Lead with the bottom line. Recommendation first, logic beneath.
- Direct, sharp prose. Vary sentence length. Active voice.
- No filler ("delve into", "navigate the complexities", "robust", "leverage", "tapestry", "not just X but Y").
- Cite sources or flag confidence level. Never fabricate.
- Surface assumptions and what was skipped (e.g., "did not analyze single-stock biotech given complexity vs. monthly cadence").
- Markdown structure inside the docx (headers, bullets, bold sparingly).
