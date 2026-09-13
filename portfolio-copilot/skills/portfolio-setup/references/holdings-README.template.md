# Holdings — Statement Drop Folder

**Purpose:** Drop your monthly account statements and exports here. The
`dashboard-refresh` skill reads the latest month's files at runtime and
refreshes `../portfolio-context.md` (Sections 2 & 3) with your current
holdings and exposures before generating the brief.

Files are organized into one subfolder per month, and mixed formats (CSV,
PDF, PNG) are accepted from any broker — there's no CSV auto-parser tied to
a specific provider's column layout; every statement is read directly and
written into that month's `manual-accounts.json`.

---

## Folder Structure

```
holdings/
├── README.md                          ← this file
├── <Recurring Private Holding>.csv    ← a one-time/private holding that
│                                         isn't part of a monthly statement
│                                         drop can live at the root (optional)
├── January 2027/                      ← one subfolder per month: "Month YYYY"
│   ├── brokerage-statement.csv
│   ├── 401k-statement.pdf
│   └── hsa-statement.png
└── February 2027/
    ├── brokerage-statement.csv
    ├── 401k-statement.pdf
    └── hsa-statement.png
```

**Rules:**

- **One subfolder per month, named `Month YYYY`** (e.g., `February 2027`).
  Drop every account's statement for that month inside it.
- **`dashboard-refresh` reads the most recent month folder** (latest
  `Month YYYY`). Older folders stay as an audit trail.
- **A recurring private/illiquid holding** (an SPV, a non-brokerage account)
  that isn't part of a monthly statement drop can live at the `holdings/`
  root instead of inside a month folder — it's read every run regardless.
- Filenames inside a month folder can be descriptive — nothing parses them
  by strict pattern; you read each one and transcribe it yourself.

---

## Monthly Workflow (~5 min)

1. **Before your brief date** each month, create a new `Month YYYY` folder
   and drop in each account's latest statement (CSV export, PDF, or a clear
   screenshot — whatever each provider makes easiest).
2. **Update `../portfolio-context.md` Section 1** with this month's deploy
   amount — the statements can't tell us how much you're investing.
3. **Run `dashboard-refresh`**, which reads every statement in the latest
   month folder, writes `manual-accounts.json`, and refreshes the dashboard
   and `portfolio-context.md`.

---

## Accepted Formats

| Format | Best for | How it's read |
|--------|----------|----------------|
| **CSV** | Any broker with a clean export | Read directly and transcribed |
| **PDF** | Statements without a clean CSV export | Read directly (text/tables) |
| **PNG / screenshot** | Accounts with no export option at all | Read directly off the image |

Any of the three works equally well — there's no preference for CSV over
PDF/PNG, since every format goes through the same manual-read step. Just make
sure ticker/fund names, quantities, and dollar values are legible.

---

## What `dashboard-refresh` Does With These Files

1. Finds the most recent `Month YYYY` subfolder and reads every statement
   inside it, plus any recurring holding at the `holdings/` root.
2. Reads each file (CSV / PDF / PNG) and writes one entry per holding into
   that month's `manual-accounts.json` — see
   `skills/dashboard-refresh/references/manual-accounts.example.json`.
3. Runs the aggregator script, which consolidates duplicated positions and
   computes sector, geography, and concentration exposures.
4. Refreshes `../portfolio-context.md` **Section 2 (Current Holdings)** and
   **Section 3 (Current Exposures)**.
5. Preserves your manually-maintained Section 1 (monthly amount), Section 4
   (preferences), Section 5 (constraints), Section 6 (audit trail).

---

## Privacy Note

These statements contain account-level financial data. They live only in
this folder on your local machine — never uploaded externally by this
plugin. If you sync this project folder to cloud storage (iCloud, Dropbox,
etc.), these files travel with that sync. For stricter handling, exclude
`holdings/` from any sync and delete statements you no longer need for
records.

---

## Archive

Past `Month YYYY` folders are kept as an audit trail. Clear folders older
than ~12 months unless you need them for tax records.
