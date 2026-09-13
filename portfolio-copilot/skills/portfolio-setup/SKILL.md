---
name: portfolio-setup
description: >-
  One-time onboarding for a new portfolio-copilot installation: creates the
  project's data folders, builds portfolio-profile.json by asking the user
  questions (never assuming values), and hands off scheduling instructions
  for the two recurring jobs. Use on first run, when portfolio-profile.json
  is missing, or when the user asks to reconfigure their profile.
---

# Portfolio Setup

Turns an empty (or partially set up) project folder into a working
`portfolio-copilot` installation. Everything this skill creates lives in the
**project** directory the user is working in — never inside the installed
plugin directory.

## How to run this interview

This is a guided, step-by-step conversation, not a form to fill out in one
shot — Steps 1–3 below happen as a back-and-forth, not a single message.

- **One question per message.** Never bundle two or more of Step 3's items
  into a single message, even if they seem related.
- **Say where things stand.** Reference which step you're on (e.g. "Step 4
  of 11 — accounts") so the user always knows how much is left.
- **Acknowledge each answer briefly before moving on** — a short confirming
  line, not a restatement of everything they said.
- **Explain why a question matters when it isn't self-evident**, in one
  sentence, before asking it — e.g. why account "flexibility" affects later
  recommendations. Skip the explanation when the question is obvious (e.g.
  asking for a name).
- **Offer a sensible default when one exists** (e.g. the shipped target
  allocation, 3 max funds/month) so the user can accept it in one word
  instead of composing an answer from scratch.
- **Tone: helpful and professional throughout.** Direct, plain language, no
  filler ("delve into," "leverage," "robust," "navigate the complexities"),
  no over-apologizing, no false enthusiasm. This is someone's financial
  setup — treat it with the same care and precision as the monthly brief
  itself, not as a casual chat.
- **Never invent an answer to move faster.** If the user is unsure or wants
  to skip a question, record it as "not set" and move on — don't fill the
  gap with a guess.

## Step 1 — Detect state

Check whether `portfolio-profile.json` already exists in the working
directory.

- **Missing** → this is a fresh setup. Continue to Step 2.
- **Exists** → ask the user whether they want to start fresh, reconfigure
  specific fields, or just add/remove an account. Don't overwrite silently.

## Step 2 — Create the folder skeleton

Idempotent — skip anything that already exists.

- `holdings/` with a `README.md` written from
  `references/holdings-README.template.md`.
- `dashboards/`, `briefs/` — empty directories.
- `decision-log.json` — `[]`.
- `sector-research.json` — `[]`.

## Step 3 — Interview the user

Work through these eleven items **in order, one message each** — treat each
numbered item below as its own conversational turn, not a checklist to
recite. **Never assume a value** — an empty or "not set" field is always
better than an invented one.

1. **Name** (for file/prose personalization only).
2. **Risk tolerance** — free text, e.g. "moderate-to-aggressive growth."
3. **Life stage / liquidity horizon** — any near-term liquidity need (a home
   purchase, a planned life event, an upcoming large expense)? If yes, ask
   for an approximate date. If no, note "no known near-term liquidity need."
4. **Investment horizon** in years (defaults to a long retirement horizon if
   the user has no near-term need).
5. **Vehicle preference** — ETF-first, or open to individual stocks? Max
   funds deployed per month (default 3 if the user has no preference).
6. **Accounts** — for each one: name, broker, flexibility
   (`flexible`/`restricted`/`cash`/`illiquid` — explain the distinction: a
   401(k) plan menu is `restricted`, a savings account is `cash`, a full
   brokerage is `flexible`), typical monthly contribution if any, a short
   display label.
7. **Concentration watch** — any single stock the user wants flagged
   prominently (most commonly employer stock)? Symbol, display label,
   whether it's employer-linked. Fine to leave empty.
8. **Target allocation** — offer the plugin's shipped default (a moderate-
   aggressive growth split; show it) and let the user accept it or override
   sector-by-sector.
9. **Standing constraints/exclusions** (e.g. "avoid direct exposure to X").
10. **Notification email** for calendar/email draft steps.
11. **Goals** (optional) — any concrete target the user already has from an
    external source (e.g. a 401(k) provider's retirement projection). Skip
    entirely if none — a missing goal renders as "not set," never invented.

## Step 4 — Write `portfolio-profile.json`

Write it to the project root using the schema in
`../dashboard-refresh/references/portfolio-profile.example.json`. Copy
`../dashboard-refresh/references/market-assumptions.default.json` into the
project root as `market-assumptions.json` — an editable local copy, not a
dependency on the plugin's shipped file going forward.

## Step 5 — Write `portfolio-context.md`

Write it from `references/portfolio-context.template.md`, with:
- Sections 2 & 3 left stubbed ("not yet refreshed") — `dashboard-refresh`
  populates these on its first run.
- Sections 1, 4, 5, 6 filled in from the interview answers, as prose sourced
  from the same numbers just written to `portfolio-profile.json` — the two
  files should never disagree on day one.

## Step 6 — Offer a project `CLAUDE.md`

Ask whether the user wants a project-level `CLAUDE.md` written. If yes, write
a generic version that points at `portfolio-profile.json` as the source of
truth for risk tolerance/targets/constraints, rather than hardcoding any of
those values into the instructions file itself — that's exactly the pattern
that made a prior version of this system hard to hand to anyone else.

## Step 7 — Hand off scheduling

This skill does not configure scheduling itself — that's a cloud feature
outside the plugin's file scope, typically managed through a `schedule`
skill/routine in this environment. Print the following as literal,
copy-pasteable text for the user to hand to that scheduler themselves,
filling in `<project path>` with this project's actual path:

> **Dashboard refresh** — cron for a day shortly after your statements
> typically arrive each month. Prompt: `Run the portfolio-copilot agent's
> dashboard-refresh skill against <project path>.`
>
> **Monthly brief** — cron for your preferred brief day/time (e.g. the 30th
> at 8:00 AM in your timezone). Prompt: `Run the portfolio-copilot agent's
> monthly-brief skill against <project path>.`

## Step 8 — Confirm and summarize

Close with a short, professional summary, not a victory lap: list every
file/folder created, in plain language. Explicitly tell the user: **real
statements belong only in this project's `holdings/` folder — never inside
the installed plugin's own directory.** A plugin update later is safe by
construction, since nothing personal lives there. End by telling them what
happens next (drop this month's statements into `holdings/`, then run
`dashboard-refresh`) so they know their next concrete step.
