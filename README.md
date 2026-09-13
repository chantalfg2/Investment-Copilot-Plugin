# portfolio-copilot

A monthly personal-portfolio dashboard refresh and ranked investment research
brief, calibrated to a user-defined profile — not any one person's accounts.

## What it does

- **Dashboard refresh** — reads every account statement you drop in for the
  month (any broker, CSV/PDF/PNG), aggregates them, and generates an HTML
  dashboard with look-through sector exposure, risk concentration, a 5-year
  forecast, and allocation-vs-target gaps.
- **Monthly brief** — a five-phase MECE research process that turns those
  gaps into a ranked, sourced top-5 investment brief, saved as a `.docx`.

## Install

You received this as a folder (unzipped, or cloned from a repo) — call that
folder `<plugin-folder>` below. In Claude Code:

```
/plugin marketplace add <plugin-folder>
/plugin install portfolio-copilot@portfolio-copilot-marketplace
```

Confirm it took: `/plugin list` should show `portfolio-copilot` as installed.
That's it — no separate build step, no dependencies to install yourself.

*(If `<plugin-folder>` lives in a GitHub repo instead of a local folder, the
first command becomes `/plugin marketplace add owner/repo` — same second
command either way.)*

## First run

Open or create a project folder — this is where your personal data will
live, completely separate from the plugin's own files (see below). Then just
say **"set up my portfolio"**. This triggers the `portfolio-setup` skill,
which interviews you step by step and builds everything else: it never
assumes your risk tolerance, accounts, or targets.

## Where your data lives vs. the plugin

```
<plugin-folder>                      the plugin itself — never edit by hand
├── .claude-plugin/marketplace.json
└── portfolio-copilot/
    ├── agents/portfolio-copilot.md
    └── skills/{dashboard-refresh,monthly-brief,portfolio-setup}/...

<your project folder>                created by portfolio-setup, all yours
├── portfolio-profile.json     your risk tolerance, accounts, targets, constraints
├── portfolio-context.md       monthly-refreshed holdings/exposures
├── market-assumptions.json    your editable copy of the shared market-data defaults
├── decision-log.json          your log of deliberate modeling choices
├── sector-research.json       your saved sector deep-research
├── holdings/                  your actual account statements
├── dashboards/                your generated dashboards
└── briefs/                    your generated briefs
```

**Nothing personal ever lives inside the plugin's own folder.** That's
deliberate: updating the plugin later never risks touching your data, and
your data never accidentally ships if you pass the plugin along to someone
else.

## Monthly use

Two prompts, run whenever you like (or scheduled — see below):

- **"Refresh the dashboard"** — after dropping this month's statements into
  `holdings/<Month YYYY>/`.
- **"Run the monthly brief"** — after the dashboard is current; reads its
  gaps to produce that month's ranked picks.

## Privacy

Your statements and portfolio data stay local to your project folder —
nothing is uploaded by the plugin itself. If that folder syncs to cloud
storage (iCloud, Dropbox, etc.), your data travels with that sync like any
other file. See `holdings/README.md` (created during setup) for more detail.

## Scheduling

The plugin doesn't configure recurring runs itself — that's a cloud feature
of the environment it runs in (typically a `schedule` skill/routine).
`portfolio-setup`'s last step prints the exact two prompts to hand to that
scheduler: one for the monthly dashboard refresh, one for the monthly brief.

## Updating

Because all personal data lives outside the plugin's own folder, updating is
safe by construction — your `portfolio-profile.json`, `holdings/`,
`dashboards/`, and `briefs/` are never touched by a plugin update.

- **Local-folder install:** replace `<plugin-folder>`'s contents with the
  new version, then run `/plugin marketplace update portfolio-copilot-marketplace`.
- **GitHub install:** `/plugin marketplace update portfolio-copilot-marketplace`
  pulls the latest commit directly.

## Troubleshooting

- **`/plugin list` doesn't show `portfolio-copilot`** — re-run the two
  install commands above; a typo in `<plugin-folder>`'s path is the most
  common cause.
- **Skill doesn't seem to trigger** ("set up my portfolio" does nothing) —
  check `/plugin` → Installed tab for errors, and confirm you're on a recent
  Claude Code version (`claude update`).
- **Something else looks off** — `/plugin` → Errors tab surfaces load
  failures directly.
