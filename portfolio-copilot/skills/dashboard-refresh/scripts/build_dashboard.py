#!/usr/bin/env python3
"""
build_dashboard.py — multi-account personal portfolio dashboard.

Required inputs:
  --profile <json>      portfolio-profile.json — identity, risk tolerance,
                         target allocation, accounts, contributions,
                         constraints. See references/portfolio-profile.example.json.
  --accounts <json>     This month's holdings. Every broker/format (CSV, PDF,
                         PNG, private SPV) is read natively and written here
                         as a flat list of holdings; each entry carries
                         account/broker + a pre-computed `buckets` dollar map.
                         See references/manual-accounts.example.json.
  --out <html>           Output dashboard HTML path.

Optional inputs:
  --assumptions <json>   market-assumptions.json — shared "house view" market
                         data (sector growth, benchmarks, forecast rates).
                         Defaults to the plugin's shipped
                         references/market-assumptions.default.json.
  --sector-research <json>  Niche-sector deep-research cards. Defaults to none.
  --dir <month-folder>   Cross-checks every non-CSV/JSON/MD file in the folder
                         against the `source` tags on this month's holdings,
                         to catch a dropped statement that never made it into
                         --accounts. Does not parse anything itself.
  --metrics <json>       Also write this month's headline metrics here.
  --note <text>          Freeform note shown under "As of" in the header.
  --asof <text>          Freeform "as of" date/label for the header.

Dashboard layout: four tabs.
  • Key Insights      — momentum vs. last month, goals/milestones progress.
  • Portfolio Snapshot — net worth/gain KPIs, a "Where You Stand" summary,
                         risk concentration, sector/geo/asset-class exposure
                         vs. benchmarks and target, and niche-sector deep
                         research ("What's Moving Your Portfolio").
  • Suggested Actions  — ranked takeaways with concrete next steps.
  • Full Data Views    — 5-yr per-account forecast, full holdings table,
                         decision log.
Account filter chips at the top recompute everything for any subset.
"""

import argparse, glob, json, os, re, sys, shutil, subprocess, tempfile
from datetime import datetime

DEFAULT_ASSUMPTIONS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "references", "market-assumptions.default.json")

SCRIPT_VERSION = "2026.09.12.2"  # bump this whenever the template/logic changes

# --------------------------------------------------------------------------- #
GICS = ["Info Tech","Comm Services","Cons Disc","Health Care","Financials",
        "Industrials","Cons Staples","Energy","Utilities","Real Estate","Materials"]
SP500 = {"Info Tech":0.32,"Comm Services":0.095,"Cons Disc":0.105,"Health Care":0.115,
         "Financials":0.13,"Industrials":0.085,"Cons Staples":0.055,"Energy":0.035,
         "Utilities":0.025,"Real Estate":0.02,"Materials":0.02}
NDX = {"Info Tech":0.50,"Comm Services":0.16,"Cons Disc":0.13,"Health Care":0.055,
       "Industrials":0.045,"Cons Staples":0.045,"Financials":0.005,"Utilities":0.01}
VALUE = {"Financials":0.21,"Health Care":0.18,"Industrials":0.13,"Cons Staples":0.10,
         "Info Tech":0.09,"Energy":0.07,"Utilities":0.06,"Comm Services":0.06,
         "Cons Disc":0.05,"Real Estate":0.05,"Materials":0.04}
MIDCAP = {"Info Tech":0.18,"Industrials":0.155,"Cons Disc":0.13,"Financials":0.13,
          "Health Care":0.10,"Real Estate":0.07,"Materials":0.05,"Cons Staples":0.05,
          "Utilities":0.06,"Energy":0.04,"Comm Services":0.035}
SMVAL = {"Financials":0.23,"Industrials":0.19,"Cons Disc":0.13,"Real Estate":0.10,
         "Materials":0.07,"Info Tech":0.07,"Health Care":0.06,"Energy":0.06,
         "Cons Staples":0.04,"Utilities":0.03,"Comm Services":0.02}
BLEND = SP500
def one(s): return {s:1.0}

FUND_MAP = {
  "VTI":{"name":"Vanguard Total Stock Market ETF","asset":"us_equity","group":"US Broad Core","sectors":SP500},
  "SPY":{"name":"SPDR S&P 500 ETF","asset":"us_equity","group":"US Broad Core","sectors":SP500},
  "VOO":{"name":"Vanguard S&P 500 ETF","asset":"us_equity","group":"US Broad Core","sectors":SP500},
  "QQQ":{"name":"Invesco QQQ Trust","asset":"us_equity","group":"US Broad Core","sectors":NDX},
  "VTV":{"name":"Vanguard Value ETF","asset":"us_equity","group":"US Value & Size","sectors":VALUE},
  "VO":{"name":"Vanguard Mid-Cap ETF","asset":"us_equity","group":"US Value & Size","sectors":MIDCAP},
  "VB":{"name":"Vanguard Small-Cap ETF","asset":"us_equity","group":"US Value & Size","sectors":SMVAL},
  "VBR":{"name":"Vanguard Small-Cap Value ETF","asset":"us_equity","group":"US Value & Size","sectors":SMVAL},
  "VUG":{"name":"Vanguard Growth ETF","asset":"us_equity","group":"US Value & Size","sectors":NDX},
  "VIG":{"name":"Vanguard Dividend Appreciation ETF","asset":"us_equity","group":"US Value & Size","sectors":BLEND},
  "VGT":{"name":"Vanguard Information Tech ETF","asset":"us_equity","group":"Technology","sectors":one("Info Tech")},
  "XLK":{"name":"Technology Select Sector SPDR","asset":"us_equity","group":"Technology","sectors":one("Info Tech")},
  "SMH":{"name":"VanEck Semiconductor ETF","asset":"us_equity","group":"Technology","sectors":one("Info Tech")},
  "SOXX":{"name":"iShares Semiconductor ETF","asset":"us_equity","group":"Technology","sectors":one("Info Tech")},
  "VHT":{"name":"Vanguard Health Care ETF","asset":"us_equity","group":"Health Care","sectors":one("Health Care")},
  "XLV":{"name":"Health Care Select Sector SPDR","asset":"us_equity","group":"Health Care","sectors":one("Health Care")},
  "IHI":{"name":"iShares US Medical Devices ETF","asset":"us_equity","group":"Health Care","sectors":one("Health Care")},
  "LLY":{"name":"Eli Lilly & Co","asset":"us_equity","group":"Health Care","sectors":one("Health Care")},
  "VIS":{"name":"Vanguard Industrials ETF","asset":"us_equity","group":"Industrials","sectors":one("Industrials")},
  "XLI":{"name":"Industrial Select Sector SPDR","asset":"us_equity","group":"Industrials","sectors":one("Industrials")},
  "XLF":{"name":"Financial Select Sector SPDR","asset":"us_equity","group":"Financials & Fintech","sectors":one("Financials")},
  "VFH":{"name":"Vanguard Financials ETF","asset":"us_equity","group":"Financials & Fintech","sectors":one("Financials")},
  "XYZ":{"name":"Block Inc","asset":"us_equity","group":"Financials & Fintech","sectors":{"Financials":0.5,"Info Tech":0.5}},
  "XLE":{"name":"Energy Select Sector SPDR","asset":"us_equity","group":"Energy","sectors":one("Energy")},
  "IXC":{"name":"iShares Global Energy ETF","asset":"us_equity","group":"Energy","sectors":one("Energy")},
  "VDE":{"name":"Vanguard Energy ETF","asset":"us_equity","group":"Energy","sectors":one("Energy")},
  "XLU":{"name":"Utilities Select Sector SPDR","asset":"us_equity","group":"Utilities","sectors":one("Utilities")},
  "XLRE":{"name":"Real Estate Select Sector SPDR","asset":"us_equity","group":"Real Estate","sectors":one("Real Estate")},
  "VNQ":{"name":"Vanguard Real Estate ETF","asset":"us_equity","group":"Real Estate","sectors":one("Real Estate")},
  "USRT":{"name":"iShares Core US REIT ETF","asset":"us_equity","group":"Real Estate","sectors":one("Real Estate")},
  "VXUS":{"name":"Vanguard Total Intl Stock ETF","asset":"intl_equity","group":"International","sectors":{}},
  "VEA":{"name":"Vanguard FTSE Developed Markets ETF","asset":"intl_equity","group":"International","sectors":{}},
  "IXUS":{"name":"iShares Core MSCI Total Intl ETF","asset":"intl_equity","group":"International","sectors":{}},
  "VWO":{"name":"Vanguard FTSE Emerging Markets ETF","asset":"intl_equity","group":"International","sectors":{}},
  "IEMG":{"name":"iShares Core MSCI Emerging Markets ETF","asset":"intl_equity","group":"International","sectors":{}},
  "BND":{"name":"Vanguard Total Bond Market ETF","asset":"bond","group":"Bonds","sectors":{}},
  "AGG":{"name":"iShares Core US Aggregate Bond ETF","asset":"bond","group":"Bonds","sectors":{}},
  "VGIT":{"name":"Vanguard Intermediate-Term Treasury ETF","asset":"bond","group":"Bonds","sectors":{}},
  "BNDX":{"name":"Vanguard Total Intl Bond ETF","asset":"bond","group":"Bonds","sectors":{}},
  "TIP":{"name":"iShares TIPS Bond ETF","asset":"bond","group":"Bonds","sectors":{}},
  "USFR":{"name":"WisdomTree Floating Rate Treasury ETF","asset":"bond","group":"Bonds","sectors":{}},
  "SGOV":{"name":"iShares 0-3 Month Treasury ETF","asset":"bond","group":"Bonds","sectors":{}},
  "IAU":{"name":"iShares Gold Trust","asset":"gold","group":"Gold / Alternatives","sectors":{}},
  "GLD":{"name":"SPDR Gold Shares","asset":"gold","group":"Gold / Alternatives","sectors":{}},
}

# The following are all populated at runtime by load_config() from
# portfolio-profile.json (personal — accounts, targets, constraints) and
# market-assumptions.json (shared house view — benchmarks, sector growth,
# forecast rates). Declared here as module-level globals, not local
# variables, because render_html() and load_decision_log() below read them
# by name — see load_config()'s docstring for why.
RECOMMENDED = None
CONTRIBUTIONS = None
CONTRIB_LABELS = None
VALUE_MARKS = None
FORECAST_OVERRIDES = None
STOCK_SYMS = None
ACCOUNT_FLEXIBILITY = None
GOALS = None
SECTOR_RESEARCH = None
CONCENTRATION_WATCH = None
LIQUIDITY_HORIZON = None
US_INTL_BENCH = None
ASSET_TARGET = None
ANALYST_AGGR = None
SECTOR_GROWTH = None
BENCH_SOURCES = None
FORECAST_RATES = None
MARKET_BENCHMARK = None

GROUP_ORDER = ["US Broad Core","US Value & Size","Technology","Financials & Fintech",
               "Health Care","Industrials","Energy","Utilities","Real Estate",
               "Target-Date","International","Bonds","Gold / Alternatives",
               "Private / Alternatives","Cash"]
BUCKET_ORDER = GICS + ["Intl ex-US","Bonds","Gold","Private","Cash"]
BUCKET_COLORS = {
  "Info Tech":"#2563eb","Comm Services":"#ea580c","Cons Disc":"#db2777","Health Care":"#0891b2",
  "Financials":"#7c3aed","Industrials":"#65a30d","Cons Staples":"#0d9488","Energy":"#ca8a04",
  "Utilities":"#9333ea","Real Estate":"#e11d48","Materials":"#92400e","Intl ex-US":"#64748b",
  "Bonds":"#0f766e","Gold":"#b8860b","Private":"#475569","Cash":"#94a3b8",
}

# Populated by load_config(): FORECAST_RATES (5-yr annual total return
# assumptions by asset class, from market-assumptions.json), CONTRIBUTIONS /
# CONTRIB_LABELS (monthly $ per account and its short display name, from
# portfolio-profile.json's `accounts`), VALUE_MARKS (one-off dated marks
# applied to a holding's CURRENT value — see apply_value_marks() below for
# why the `effectiveMonth` field on each mark matters and must never be
# dropped), all sourced from portfolio-profile.json.

def apply_value_marks(holdings, month_key=None):
    """Mutates holdings in place per VALUE_MARKS; returns the note strings for
    any mark that actually matched a holding this month.

    Every mark carries an `effectiveMonth` — the month it was decided in.
    Without a month gate, a mark like a pre-IPO fair-value estimate on a
    private holding would silently re-apply to every EARLIER month too,
    including a backfilled one, contaminating the trend history with a
    present-day judgment call the account did not actually carry at that
    prior date. `month_key < effectiveMonth` skips the mark entirely for that
    build, so a rebuilt/backfilled month reflects what was true then, not
    what's true now."""
    notes=[]
    for acct, mark in VALUE_MARKS.items():
        eff=mark.get("effectiveMonth")
        if eff and month_key and month_key<eff: continue
        matched=[h for h in holdings if h["account"]==acct]
        for h in matched:
            old_val=h["value"]; new_val=mark["markedValue"]
            if abs(old_val-new_val) < 0.005: continue
            factor = (new_val/old_val) if old_val else 1.0
            h["gl"]=h.get("gl",0.0)+(new_val-old_val)
            h["value"]=new_val
            h["buckets"]={k:v*factor for k,v in h["buckets"].items()}
            h["valueMarked"]=True  # so the UI can label this "(marked)" vs "(at cost)"
            h["markOriginalValue"]=old_val  # lets the UI compute the markup delta directly,
                                             # without assuming anything about gl's prior meaning
            # "(private, at cost)" is now stale/misleading — strip it before
            # appending the clearer, accurate label.
            h["name"]=h["name"].replace("(private, at cost)","").strip()
            if "MARKED" not in h["name"]:
                h["name"]=h["name"]+" — MARKED ~"+("%.0f"%factor)+"x, pre-IPO est."
        if matched: notes.append(mark["note"])
    return notes

# FORECAST_OVERRIDES schema (populated from portfolio-profile.json's
# `forecastOverrides`, keyed by account name matching `holdings[].account`):
# one-off, dated overrides to the 5-Year Net-Worth Forecast — layered ONLY on
# top of the forecast math (growth rate and/or contribution schedule), never
# on the account's CURRENT displayed value (VALUE_MARKS is for that).
#   markMultiple  — multiply the account's current (already-marked) value by
#                   this factor *only* for the compounding starting balance
#                   (not the displayed "Now" figure).
#   rateClass     — force this FORECAST_RATES bucket instead of the account's
#                   blended-by-holdings rate (e.g. "equity" once a private
#                   stake converts to public stock).
#   skipMonths    — reduce the 60-month contribution schedule by this many
#                   months (contributions paused, then resume at the same
#                   monthly amount for the remainder of the 5-yr window).
#   note          — dated, sourced footnote shown under the forecast table.
# Edit only in portfolio-profile.json — never hand-adjust fcAccount()'s
# numbers for a one-off.

def load_config(profile_path, assumptions_path=None, sector_research_path=None):
    """Populate the module-level config globals declared above from
    portfolio-profile.json (personal — accounts, targets, contributions,
    constraints) and market-assumptions.json (shared house view — sector
    growth, benchmarks, forecast rates). Kept as globals rather than passed
    through function signatures because render_html() and
    load_decision_log() already read them that way — this is the smallest
    change that lets both keep working unmodified. Call this once, before
    render_html()."""
    global RECOMMENDED, CONTRIBUTIONS, CONTRIB_LABELS, ACCOUNT_FLEXIBILITY
    global STOCK_SYMS, GOALS, VALUE_MARKS, FORECAST_OVERRIDES, CONCENTRATION_WATCH
    global LIQUIDITY_HORIZON, US_INTL_BENCH, ASSET_TARGET, ANALYST_AGGR
    global SECTOR_GROWTH, BENCH_SOURCES, FORECAST_RATES, SECTOR_RESEARCH
    global MARKET_BENCHMARK

    profile = json.load(open(profile_path))
    accounts = profile.get("accounts", [])

    RECOMMENDED = profile["recommendedAllocation"]
    CONTRIBUTIONS = {a["name"]: a["monthlyContribution"] for a in accounts if a.get("monthlyContribution")}
    CONTRIB_LABELS = {a["name"]: a.get("contribLabel") or a["name"] for a in accounts}
    ACCOUNT_FLEXIBILITY = {a["name"]: {"tag": a.get("flexibility", "flexible"),
                                        "note": a.get("flexibilityNote", "")} for a in accounts}
    STOCK_SYMS = set(profile.get("individualStockSymbols", []))
    GOALS = profile.get("goals", {})
    VALUE_MARKS = profile.get("valueMarks", {})
    FORECAST_OVERRIDES = profile.get("forecastOverrides", {})
    CONCENTRATION_WATCH = profile.get("concentrationWatch", [])
    LIQUIDITY_HORIZON = (profile.get("user", {}) or {}).get("liquidityHorizon") or {"note": "", "windowStartDate": None}

    # Asset-class target (Equity/Bonds/Cash/Gold-Alt) is DERIVED from the
    # user's own recommendedAllocation, never shipped as a separate
    # market-assumptions default — it's presented on the dashboard as "your
    # target," so it must always agree with the same sector-level targets
    # driving the Sector Positioning chart, including after the user edits
    # recommendedAllocation. Two independently-maintained copies of "the
    # target" is exactly the kind of drift this plugin is meant to prevent.
    equity_us = sum(RECOMMENDED.get(k, 0) for k in GICS)
    ASSET_TARGET = {
        "Equity": round(equity_us + RECOMMENDED.get("Intl ex-US", 0), 1),
        "Bonds": RECOMMENDED.get("Bonds", 0),
        "Cash": RECOMMENDED.get("Cash", 0),
        "Gold/Alt": RECOMMENDED.get("Gold / Alt", 0),
    }

    assumptions = json.load(open(assumptions_path or DEFAULT_ASSUMPTIONS_PATH))
    US_INTL_BENCH = assumptions["usIntlBenchmark"]
    ANALYST_AGGR = assumptions["analystAggressiveWeights"]
    SECTOR_GROWTH = assumptions["sectorGrowth"]
    BENCH_SOURCES = assumptions["benchSources"]
    FORECAST_RATES = assumptions["forecastRates"]
    # Market benchmark (e.g. S&P 500 return) for the Momentum panel's "vs the
    # market" comparison — shared "update this by hand periodically" market
    # data, same cadence/category as sectorGrowth/analystAggressiveWeights, so
    # it lives here rather than in portfolio-profile.json. Optional: an older
    # market-assumptions.json (or the shipped default before a user fills it
    # in) may omit it entirely, or ship it with an empty `asof`/zero `pct` as
    # a neutral placeholder — the dashboard JS treats a missing `asof` as
    # "not set" and skips the market comparison rather than showing a bogus
    # "compared to 0% over ''" line.
    MARKET_BENCHMARK = assumptions.get("marketBenchmark") or \
        {"pct": 0, "periodLabel": "", "asof": "", "sources": []}

    if sector_research_path and os.path.exists(sector_research_path):
        SECTOR_RESEARCH = json.load(open(sector_research_path))
    else:
        SECTOR_RESEARCH = []

# --------------------------------------------------------------------------- #
def classify(sym, desc):
    if sym in FUND_MAP: return dict(FUND_MAP[sym]), None
    up=desc.upper()
    def mk(asset,group,sectors): return {"name":_title(desc),"asset":asset,"group":group,"sectors":sectors}
    if any(k in up for k in ("BOND","TREASURY","AGGREGATE","FIXED INC","MUNI","TIPS","T-BILL","FLOATING RATE")):
        return mk("bond","Bonds",{}), f"{sym}: unknown ticker — guessed BOND"
    if "GOLD" in up: return mk("gold","Gold / Alternatives",{}), f"{sym}: unknown — guessed GOLD"
    if any(k in up for k in ("SILVER","COMMODIT","OIL FUND")): return mk("gold","Gold / Alternatives",{}), f"{sym}: unknown — guessed COMMODITY"
    if any(k in up for k in ("INTERNATIONAL","INTL","EX-US","EX US","EMERGING","EAFE","DEVELOPED MARKETS","WORLD EX","ACWX")):
        return mk("intl_equity","International",{}), f"{sym}: unknown — guessed INTERNATIONAL"
    kw=[(("SEMICONDUCTOR","TECHNOLOGY","INFORMATION TECH","SOFTWARE","INTERNET"),"Info Tech","Technology"),
        (("HEALTH","PHARMA","BIOTECH","MEDICAL"),"Health Care","Health Care"),
        (("FINANCIAL","BANK","INSURANCE"),"Financials","Financials & Fintech"),
        (("ENERGY","OIL","GAS"),"Energy","Energy"),
        (("INDUSTRIAL","AEROSPACE","DEFENSE"),"Industrials","Industrials"),
        (("UTILIT",),"Utilities","Utilities"),
        (("REAL ESTATE","REIT"),"Real Estate","Real Estate"),
        (("MATERIAL","MINING","AGRICULTURE"),"Materials","US Broad Core"),
        (("COMMUNICATION","TELECOM"),"Comm Services","US Broad Core")]
    for kws,sec,grp in kw:
        if any(k in up for k in kws): return mk("us_equity",grp,one(sec)), f"{sym}: unknown — guessed {sec}"
    return mk("us_equity","US Broad Core",SP500), f"{sym}: unknown — treated as US broad"

def _title(desc):
    p=desc.split(); return " ".join(p[1:]).title() if len(p)>1 else desc

def category_label(info):
    a=info["asset"]
    return {"intl_equity":"International","bond":"Fixed income","gold":"Gold"}.get(a) or \
        ("US broad" if info["group"]=="US Broad Core" else
         "US style/size" if info["group"]=="US Value & Size" else info["group"])

def buckets_for(value, info):
    a=info["asset"]
    if a=="us_equity":
        tw=sum(info["sectors"].values()) or 1.0
        return {s:round(value*w/tw,2) for s,w in info["sectors"].items()}
    if a=="intl_equity": return {"Intl ex-US":round(value,2)}
    if a=="bond": return {"Bonds":round(value,2)}
    if a=="gold": return {"Gold":round(value,2)}
    return {"Cash":round(value,2)}

def kind_of(sym, buckets):
    ks=set(buckets)
    if ks=={"Cash"}: return "cash"
    if ks=={"Private"}: return "private"
    return "stock" if sym in STOCK_SYMS else "fund"

def make_holding(sym,name,account,broker,qty,price,value,gl,group,buckets,cat,source=None):
    cost=value-gl
    glp=(gl/cost*100) if cost else 0.0
    return {"sym":sym,"name":name,"account":account,"broker":broker,
            "qty":qty,"price":round(price,2) if price else None,
            "value":round(value,2),"gl":round(gl,2),"glp":round(glp,2),
            "group":group,"cat":cat,"buckets":buckets,"kind":kind_of(sym,buckets),
            "source":source}

def load_holdings_json(path):
    """Load this month's holdings from --accounts (manual-accounts.json) —
    the sole holdings input. Every broker/format (CSV, PDF, PNG, private SPV)
    is read natively by Claude and written here as a flat list; each entry
    either carries a pre-computed `buckets` dollar map (the normal case) or
    falls back to the classify()/buckets_for() ETF-ticker lookup below when
    `buckets` is omitted."""
    out=[]
    for h in json.load(open(path)):
        src=h.get("source")  # which statement file this holding's numbers came from —
                              # cross-checked against the month folder in main()'s
                              # completeness scan. None/missing is allowed but gets
                              # flagged, since it means nothing can verify this row.
        if "buckets" in h:
            out.append(make_holding(h.get("sym","?"),h.get("name","?"),h["account"],
                h.get("broker","Other"),h.get("qty"),h.get("price"),h["value"],h.get("gl",0.0),
                h.get("group","Other"),{k:round(v,2) for k,v in h["buckets"].items()},
                h.get("cat",h.get("group","Other")),source=src))
        else:
            info,_=classify(h.get("sym",""),h.get("name",h.get("sym","")))
            out.append(make_holding(h.get("sym","?"),info["name"],h["account"],h.get("broker","Other"),
                h.get("qty"),h.get("price"),h["value"],h.get("gl",0.0),info["group"],
                buckets_for(h["value"],info),category_label(info),source=src))
    return out

# --------------------------------------------------------------------------- #
def validate_buckets(holdings):
    """Every holding's `buckets` dollar map must sum to its `value` — if it
    doesn't, every sector/geo percentage downstream (KPIs, charts, gap flags)
    is silently wrong with no visible sign. Returns a list of warning strings;
    does not mutate or drop anything, so a bad row still shows up (with a
    flagged number) rather than vanishing."""
    issues=[]
    for h in holdings:
        bsum=sum((h.get("buckets") or {}).values())
        diff=bsum-h["value"]
        if abs(diff)>0.05:
            issues.append(f'Bucket mismatch — {h["sym"]} ({h["account"]}): buckets sum to '
                          f'${bsum:,.2f}, expected ${h["value"]:,.2f} (diff ${diff:+,.2f}) — '
                          f'sector percentages involving this holding will be off')
    return issues

def verify_js_syntax(html):
    """Extract the dashboard's inline <script> block and run `node --check`
    against it. This is the single check that would have caught both bugs
    fixed on 2026-09-09 (a missing brace that blanked the whole dashboard,
    and a silent sort-order bug) before they ever reached the artifact.
    Returns (ok, message). If Node isn't installed, the check is SKIPPED
    (ok=True) rather than failed, so the build still completes on a machine
    without Node — but the skip is recorded as a warning so it's visible."""
    m=re.search(r'<script>(.*?)</script>\s*</body>', html, re.S)
    if not m:
        return False, "verify_js_syntax: could not locate the inline <script> block in generated HTML"
    js=m.group(1)
    node=shutil.which("node")
    if not node:
        return True, "SKIPPED: node not found on PATH — JS syntax check not run (install Node.js to enable this safety net)"
    fd,path=tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: f.write(js)
        r=subprocess.run([node,"--check",path],capture_output=True,text=True)
    finally:
        os.unlink(path)
    if r.returncode==0:
        return True, "JS syntax check passed (node --check)"
    return False, "JS SYNTAX ERROR in generated dashboard — build stopped:\n"+(r.stderr or r.stdout or "(no output)")

def compute_aggregates(holdings):
    """Single place that computes the headline numbers (total, sector %s,
    largest single-stock %) — used both for this month's metrics.json AND
    for building the trend series, so the two can never drift apart."""
    from collections import defaultdict
    acc=defaultdict(float); bt=defaultdict(float); by_sym=defaultdict(float)
    for h in holdings:
        acc[h["account"]]+=h["value"]
        for k,v in h["buckets"].items(): bt[k]+=v
        if h["kind"]=="stock": by_sym[h["sym"]]+=h["value"]
    total=sum(h["value"] for h in holdings)
    equity=sum(bt[k] for k in GICS)+bt.get("Intl ex-US",0)
    largest_sym,largest_val=(max(by_sym.items(),key=lambda kv:kv[1]) if by_sym else (None,0.0))
    return {
        "total":round(total,2),
        "accounts":{a:round(v,2) for a,v in acc.items()},
        "buckets":{k:round(v,2) for k,v in bt.items()},
        "tech_pct":round(bt["Info Tech"]/total*100,1) if total else 0,
        "intl_eq_pct":round(bt.get("Intl ex-US",0)/equity*100,1) if equity else 0,
        "bonds_pct":round(bt.get("Bonds",0)/total*100,1) if total else 0,
        "largest_stock_sym":largest_sym,
        "largest_stock_pct":round(largest_val/total*100,1) if total and largest_sym else None,
    }

def month_key_from_path(path):
    m=re.search(r"(\d{4}-\d{2})", os.path.basename(path or ""))
    return m.group(1) if m else datetime.now().strftime("%Y-%m")

def load_trend_history(dashboards_dir, exclude_month=None):
    """Read every dashboards/YYYY-MM-metrics.json that already exists (older
    months may lack fields added later — tolerate missing keys rather than
    erroring, so history doesn't break when the schema grows)."""
    if not dashboards_dir or not os.path.isdir(dashboards_dir): return []
    out=[]
    for path in sorted(glob.glob(os.path.join(dashboards_dir,"*-metrics.json"))):
        mk=month_key_from_path(path)
        if exclude_month and mk==exclude_month: continue
        try: d=json.load(open(path))
        except Exception: continue
        out.append({"month":mk,"total":d.get("total"),"tech_pct":d.get("tech_pct"),
                    "intl_eq_pct":d.get("intl_eq_pct"),"bonds_pct":d.get("bonds_pct"),
                    "largest_stock_pct":d.get("largest_stock_pct"),
                    "largest_stock_sym":d.get("largest_stock_sym"),
                    "accounts":d.get("accounts") or {}})
    out.sort(key=lambda r:r["month"])
    return out

def build_trend(history, month_key, agg, value_notes=None):
    """Append this month's point to prior history and flag when the account
    set changed vs. the immediately-prior month, or a value mark applied —
    either one makes a jump NOT organic growth, and a momentum panel that
    doesn't say so is misleading by omission."""
    current={"month":month_key,"total":agg["total"],"tech_pct":agg["tech_pct"],
             "intl_eq_pct":agg["intl_eq_pct"],"bonds_pct":agg["bonds_pct"],
             "largest_stock_pct":agg["largest_stock_pct"],
             "largest_stock_sym":agg["largest_stock_sym"],"accounts":agg["accounts"]}
    points=[p for p in history if p["month"]!=month_key]+[current]
    points.sort(key=lambda r:r["month"])
    caveats=[]
    if len(points)>=2:
        prev,cur=points[-2],points[-1]
        prev_accts=set((prev.get("accounts") or {}).keys())
        cur_accts=set((cur.get("accounts") or {}).keys())
        new_accts=cur_accts-prev_accts
        if new_accts:
            added_val=sum((cur.get("accounts") or {}).get(a,0) for a in new_accts)
            caveats.append(f"{cur['month']} vs {prev['month']}: {len(new_accts)} newly-tracked "
                            f"account(s) added ~${added_val:,.0f} ({', '.join(sorted(new_accts))}) — "
                            f"not organic growth, compare structurally rather than headline-to-headline.")
        if value_notes:
            caveats.append(f"{cur['month']} also applies {len(value_notes)} deliberate value-mark "
                            f"adjustment(s) (see the amber assumption note above) — part of this "
                            f"month's change is a re-estimate, not market movement or contributions.")
    return {"points":points,"caveats":caveats}

def load_decision_log(path, holdings, contributions):
    """Read decision-log.json (a plain list the user/Claude appends to over
    time) and resolve each entry's `watchMetric`, where one is set, against
    THIS month's live data — so the log shows not just what was decided but
    what's happened since, without needing separate manual upkeep.

    `watchMetric` is a structured object, not a hardcoded string keyword, so
    a new user's accounts never require touching this function:
      {"type":"contribution","account":"<name>"}  -> that account's $/mo
      {"type":"holdingValue","account":"<name>"}  -> that account's current value
    """
    if not path or not os.path.exists(path): return []
    try: entries=json.load(open(path))
    except Exception: return []
    by_acct={h["account"]:h for h in holdings}  # last one wins; fine for single-holding accounts
    for e in entries:
        wm=e.get("watchMetric")
        if not wm: continue
        acct=wm.get("account")
        if wm.get("type")=="contribution":
            e["current_value"]=f"${contributions.get(acct,0.0):,.0f}/mo"
        elif wm.get("type")=="holdingValue":
            h=by_acct.get(acct)
            e["current_value"]=f"${h['value']:,.0f}" if h else "not held this month"
    return entries

def render_html(holdings, asof, note, assumptions, value_notes=None, trend=None, decision_log=None):
    accounts=[]
    for h in holdings:
        if h["account"] not in accounts: accounts.append(h["account"])
    data={"holdings":holdings,"accounts":accounts,"recommended":RECOMMENDED,
          "bucketOrder":BUCKET_ORDER,"bucketColors":BUCKET_COLORS,"gics":GICS,
          "groupOrder":GROUP_ORDER,"asof":asof or "latest statements","note":note,
          "assumptions":assumptions,"valueNotes":value_notes or [],
          "forecastRates":FORECAST_RATES,"research":SECTOR_RESEARCH,
          "contributions":CONTRIBUTIONS,"contribLabels":CONTRIB_LABELS,
          "forecastOverrides":FORECAST_OVERRIDES,
          "usIntlBench":US_INTL_BENCH,"assetTarget":ASSET_TARGET,
          "analystAggr":ANALYST_AGGR,"sectorGrowth":SECTOR_GROWTH,"benchSources":BENCH_SOURCES,
          "marketBenchmark":MARKET_BENCHMARK,
          "accountFlex":ACCOUNT_FLEXIBILITY,"goals":GOALS,
          "concentrationWatch":CONCENTRATION_WATCH or [],"liquidityHorizon":LIQUIDITY_HORIZON or {"note":"","windowStartDate":None},
          "trend":trend or {"points":[],"caveats":[]},"decisionLog":decision_log or [],
          "scriptVersion":SCRIPT_VERSION,"buildTime":datetime.now().strftime("%Y-%m-%d %H:%M")}
    return HTML_TEMPLATE.replace("/*__DATA__*/null", json.dumps(data))

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js"></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap">
<style>
:root{color-scheme:dark;
/* Dark-navy shell with white content tiles and a single vermillion accent
   carrying every interactive/highlight role. White tiles rather than
   tinted-on-dark surfaces, since a plain white card reads easier at a
   glance. Semantic states (good/bad/caution/under) are unrelated to brand
   identity and stay on their own distinct hues. The Portfolio Snapshot
   tab's charts (sector donut, benchmarks, sector positioning) intentionally
   keep their own hardcoded chart colors rather than theme variables — their
   over/under/neutral color coding should stay stable even if this theme is
   re-skinned again later. */
--r:4px;
--paper:#0a1120;--surface:#ffffff;--surface-hi:#f5f7fb;
--ink:#101d34;--ink-soft:#4c5b73;--ink-faint:#7a8499;
--line:#e6e9f0;--line-soft:#dde1ea;
--ink-shell:#eef2fa;--ink-shell-soft:#8a96ac;
--clay:#ff7a5c;--clay-solid:#f2503a;--clay-bg:#fde1da;--clay-deep:#b8371f;--clay-ink:#101d34;
--moss:#157a3d;--moss-solid:#1f7a43;--moss-bg:#d7f0dd;
--rust:#b91c1c;--rust-solid:#b33030;--rust-bg:#f8d9d9;
--ash:#375168;
--amber:#b45309;--amber-solid:#8a5c14;--amber-bg:#f6e2c3;
}
*{box-sizing:border-box}
body{margin:0;padding:20px 14px;background:var(--paper);color:var(--ink);font-family:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-size:14px;line-height:1.45}
@media(max-width:600px){body{padding:10px 6px}}
/* The central page is one consistent light zone (the page shell stays dark
   in the margins outside it on wide screens) rather than white tiles
   floating with dark gaps between them — h1/.sub/.tabbar/.foot use the
   regular dark ink tokens like everything else inside .wrap. */
.wrap{max-width:1080px;margin:0 auto;padding:20px 24px 36px;background:var(--surface-hi);border-radius:16px}
h1{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:21px;margin:0 0 2px;letter-spacing:-.01em;color:var(--ink)}
h2{font-family:'IBM Plex Mono',monospace;font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-soft);margin:0 0 8px;font-weight:600}
.sub{color:var(--ink-soft);font-size:12.5px;margin:0 0 12px}
.badge{display:inline-block;background:var(--clay-bg);color:var(--clay-deep);border:1px solid var(--line);border-radius:var(--r);padding:2px 10px;font-size:11px;font-weight:600;vertical-align:middle;font-family:'IBM Plex Mono',monospace;letter-spacing:.02em}
.grid{display:grid;gap:10px}.cards{grid-template-columns:repeat(4,1fr)}.two{grid-template-columns:1.05fr 1fr}.three{grid-template-columns:repeat(3,1fr)}
@media(max-width:760px){.cards{grid-template-columns:repeat(2,1fr)}.two,.three{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:13px 16px;margin-bottom:12px}
.kpi .label{font-family:'IBM Plex Mono',monospace;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-soft)}.kpi .val{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:22px;margin-top:4px;font-variant-numeric:tabular-nums;color:var(--ink)}.kpi .hint{font-size:11px;color:var(--ink-faint);margin-top:3px}
.pos{color:var(--moss)}.neg{color:var(--rust)}.over{color:var(--rust)}.under{color:var(--ash)}
.flagbox{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--amber);border-radius:var(--r);padding:10px 14px;margin-bottom:8px}
.flagbox b{font-family:'IBM Plex Mono',monospace;text-transform:uppercase;font-size:11px;letter-spacing:.05em;color:var(--ink-soft)}.flagbox p,.flagbox li{margin:4px 0 0;color:var(--ink-soft);font-size:12.5px}.flagbox ul{margin:4px 0 0;padding-left:18px}.flagbox li{margin:0 0 3px}
.tk{border:1px solid var(--line);border-left:4px solid var(--clay);border-radius:var(--r);padding:11px 14px;margin-bottom:9px}
.tk h4{margin:0 0 4px;font-size:14px;font-weight:700;color:var(--ink)}.tk p{margin:0 0 6px;color:var(--ink-soft);font-size:12.5px}
.tk .act{font-size:12.5px}.tk .act b{color:var(--clay-deep)}.tk ul{margin:3px 0 0;padding-left:18px}.tk li{font-size:12.5px;margin-bottom:3px;color:var(--ink-soft)}
table{width:100%;border-collapse:collapse;font-size:12.8px;font-family:'IBM Plex Mono',monospace;font-variant-numeric:tabular-nums}th,td{padding:6px 9px;text-align:right;border-bottom:1px solid var(--line-soft);white-space:nowrap;color:var(--ink)}
th{color:var(--ink-soft);font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.05em;cursor:pointer;user-select:none}
th.l,td.l{text-align:left;font-family:'IBM Plex Sans',sans-serif}th.nos{cursor:default}th:hover{color:var(--ink)}tbody tr:hover{background:var(--surface-hi)}
tr.grouphd td{background:var(--line-soft);font-weight:700;color:var(--ink)}tr.grouphd:hover td{background:var(--line-soft)}
tr.child td{background:var(--surface);color:var(--ink-soft);font-size:12px}tr.child td.l{padding-left:26px}
.tick{font-weight:700;color:var(--ink)}.muted{color:var(--ink-faint);font-size:11px}.acctcell{color:var(--ink-soft);font-size:11px}
.exp{display:inline-block;width:14px;color:var(--ink-faint);font-weight:700}
.bar-wrap{display:flex;flex-direction:column;gap:14px;margin-top:4px}.bench{font-size:12.5px}
.bench .row1{display:flex;justify-content:space-between;margin-bottom:4px}
.bench .track{position:relative;height:18px;background:var(--line-soft);border-radius:var(--r);overflow:hidden}
.bench .fill{position:absolute;top:0;left:0;height:100%;border-radius:var(--r)}.bench .target{position:absolute;top:-3px;height:24px;width:2px;background:var(--ink)}
.bench .tlab{font-size:10.5px;color:var(--ink-soft)}.foot{color:var(--ink-faint);font-size:11.5px;margin-top:12px;line-height:1.5}
.notefoot{background:var(--surface);color:var(--ink-faint);font-size:11.5px;line-height:1.5;margin:0 0 10px;padding:10px 14px;border-radius:var(--r)}.notefoot b{color:var(--ink-soft);font-weight:600}
.donut-row{display:flex;gap:22px;align-items:center;flex-wrap:wrap}
.legend{display:flex;flex-direction:column;flex-wrap:wrap;max-height:280px;gap:7px 18px;margin-top:0;font-size:12px;font-family:'IBM Plex Mono',monospace;color:var(--ink-soft)}.legend span{display:flex;align-items:center;gap:6px}
@media(max-width:640px){.legend{flex-direction:row;flex-wrap:wrap;max-height:none;margin-top:10px}}
.dot{width:10px;height:10px;border-radius:2px;display:inline-block}
.toggle{display:inline-flex;border:1px solid var(--line);border-radius:var(--r);overflow:hidden;margin-bottom:12px}
.toggle button{background:var(--surface);border:0;padding:6px 14px;font-size:12.5px;cursor:pointer;color:var(--ink-soft);font-weight:600;font-family:'IBM Plex Sans',sans-serif}.toggle button.active{background:var(--clay);color:var(--clay-ink)}
.delta-pill{font-weight:700}
.filter{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:11px 14px;margin-bottom:10px}
.filter-head{cursor:pointer;user-select:none}
.filter-head #filterChevron{color:var(--ink-faint);font-size:11px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);border-radius:var(--r);padding:4px 10px;font-size:12.5px;font-family:'IBM Plex Sans',sans-serif;cursor:pointer;user-select:none;background:var(--surface);color:var(--ink-soft)}
.chip.on{background:var(--clay-bg);border-color:var(--clay);color:var(--clay-deep);font-weight:600}
.chip .sw{width:9px;height:9px;border-radius:50%;background:var(--line)}.chip.on .sw{background:var(--clay)}
.chip .amt{color:var(--ink-faint);font-size:11px}.chip.on .amt{color:var(--clay-deep)}
.linkbtn{background:none;border:0;color:var(--clay-deep);font-size:12px;cursor:pointer;padding:0;margin-left:4px;font-family:'IBM Plex Sans',sans-serif;font-weight:600}
.tabbar{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:12px}
.tabbar button{background:none;border:0;border-bottom:2px solid transparent;padding:7px 14px;font-size:14px;font-weight:600;color:var(--ink-soft);cursor:pointer;margin-bottom:-1px;font-family:'IBM Plex Sans',sans-serif}
.tabbar button.active{color:var(--clay-deep);border-bottom-color:var(--clay)}
.tile{border:1px solid var(--line);border-radius:var(--r);padding:9px 11px}
.tile .t{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.05em}.tile .v{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:18px;margin-top:3px;font-variant-numeric:tabular-nums;color:var(--ink)}.tile .s{font-size:11px;color:var(--ink-faint);margin-top:2px}
.rcard{border:1px solid var(--line);border-left:4px solid var(--clay);border-radius:var(--r);padding:11px 14px}
.rcard h3{margin:0 0 2px;font-size:15px;font-weight:700;color:var(--ink)}.rcard .tag{font-family:'IBM Plex Mono',monospace;text-transform:uppercase;letter-spacing:.03em;font-size:10.5px;font-weight:700;color:#fff;border-radius:var(--r);padding:2px 9px;display:inline-block;margin-bottom:8px}
.rcard .hl{font-size:12.5px;color:var(--ink-soft);line-height:1.5;margin:0 0 9px}
.rcard .sw{background:var(--line-soft);border-radius:var(--r);padding:9px 11px;font-size:12.5px;color:var(--ink)}.rcard .sw b{color:var(--clay-deep)}
.rcard .src{margin-top:8px;font-size:11px;color:var(--ink-faint)}.rcard .src a{color:var(--ink-soft)}
.hidden{display:none}
.subh{font-family:'IBM Plex Mono',monospace;text-transform:uppercase;letter-spacing:.04em;font-size:11px;font-weight:600;color:var(--ink-soft);margin-bottom:6px;text-align:center}
.callout{background:var(--line-soft);border-radius:var(--r);padding:11px 14px;font-size:12.5px;color:var(--ink);border-left:3px solid var(--clay)}
.gtag{display:inline-block;font-size:11.5px;color:var(--ink-soft);background:var(--line-soft);border-radius:var(--r);padding:3px 9px;margin:0 6px 6px 0}
.mtile .spark{display:block;margin-top:6px}
.mdelta{font-weight:700}.mdelta.up{color:var(--moss)}.mdelta.down{color:var(--rust)}.mdelta.flat{color:var(--ink-faint)}
.dlog{border-left:3px solid var(--line);padding:6px 0 6px 12px;margin-bottom:8px}
.dlog .ddate{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--ink-faint)}
.dlog h4{margin:2px 0 4px;font-size:13.5px;font-weight:700;color:var(--ink)}
.dlog p{margin:2px 0;font-size:12.5px;color:var(--ink-soft)}
.dlog .dcur{display:inline-block;background:var(--line-soft);border-radius:var(--r);padding:2px 8px;font-size:11.5px;font-weight:600;margin-top:4px;color:var(--ink)}
.goalbar{background:var(--line-soft);border-radius:var(--r);height:10px;overflow:hidden;margin:6px 0}
.goalbar .fill{background:var(--moss);height:100%}
.goalbar .fill.over{background:var(--clay)}
.flexTag{display:inline-block;font-size:10.5px;font-weight:600;border-radius:var(--r);padding:1px 7px;margin-left:6px;vertical-align:middle;font-family:'IBM Plex Mono',monospace}
.flexTag.flexible{background:var(--moss-bg);color:var(--moss)}
.flexTag.restricted{background:var(--amber-bg);color:var(--amber)}
.flexTag.cash,.flexTag.illiquid{background:var(--line-soft);color:var(--ink-soft)}
.flexTag.watch{background:var(--rust-bg);color:var(--rust)}
/* Portfolio Health synthesis — the single "am I on track" verdict, always
   visible above the tab bar regardless of which tab is open. Outranks every
   card below it visually: bigger padding, a solid verdict pill, tinted fill
   instead of a flat surface. Verdict pill backgrounds use the "-solid" dark
   shades (moss-solid/amber-solid/clay-solid), not the bright text shades —
   white text needs a dark-enough background to stay readable. */
.synthesis{border:1px solid var(--line);border-left:6px solid var(--clay);border-radius:var(--r);padding:13px 18px;margin-bottom:10px}
.synthesis .verdict{display:inline-flex;align-items:center;font-family:'IBM Plex Mono',monospace;text-transform:uppercase;letter-spacing:.05em;font-size:11.5px;font-weight:700;border-radius:var(--r);padding:4px 13px;margin-bottom:7px;color:#fff}
.synthesis p{margin:0;font-size:13.5px;line-height:1.6;color:var(--ink)}
.synthesis.ok{background:var(--moss-bg);border-left-color:var(--moss)}.synthesis.ok .verdict{background:var(--moss-solid)}
.synthesis.mixed{background:var(--amber-bg);border-left-color:var(--amber)}.synthesis.mixed .verdict{background:var(--amber-solid)}
.synthesis.attn{background:var(--clay-bg);border-left-color:var(--clay)}.synthesis.attn .verdict{background:var(--clay-solid)}
/* Momentum verdict — one judgment sentence above the raw trend tiles, same
   ok/mixed/attn language as the synthesis banner so the two never disagree
   in tone. Text-on-tint here, so it uses the bright shades, not -solid. */
.mverdict{font-size:13px;font-weight:600;margin:0 0 8px;padding:7px 12px;border-radius:var(--r)}
.mverdict.ok{background:var(--moss-bg);color:var(--moss)}
.mverdict.mixed{background:var(--amber-bg);color:var(--amber)}
.mverdict.attn{background:var(--clay-bg);color:var(--clay-deep)}
/* "What drove the change" — a plain bulleted breakdown, not a bordered
   callout box, since this is routine context (numbers that always add up
   to the total), not a warning that needs a flag. */
.factors{margin:0 0 12px}
.factors .fhead{font-family:'IBM Plex Mono',monospace;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-faint);margin-bottom:4px}
.factors ul{margin:0;padding-left:18px}
.factors li{font-size:12.5px;color:var(--ink-soft);margin-bottom:3px}
.factors li b{color:var(--ink)}
/* Takeaway cards get promoted visual weight: numbered badge + brighter fill
   than a plain .card, so they outrank reference material (Decision Log,
   Research) they now sit above. Badge is a rounded square, not a circle,
   to match the page's one corner-radius scale. */
.tk{background:var(--surface-hi);border-left-width:5px}
.tk .pnum{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:var(--r);color:#fff;font-family:'IBM Plex Mono',monospace;font-size:10.5px;font-weight:700;margin-right:7px;vertical-align:middle}
/* Quiet reference cards (Decision Log, Research): no box, no elevation — a
   hairline divider instead, so they read as background material rather than
   competing with the takeaways above them. */
.card-quiet{background:var(--surface);border:0;border-top:1px solid var(--line);border-radius:0;padding:14px 16px 4px;margin-bottom:12px}
</style></head><body><div class="wrap">
<h1>Portfolio Dashboard <span class="badge" id="asof"></span></h1>
<p class="sub" id="sub"></p>

<div class="filter">
  <div class="filter-head" id="filterHead" style="display:flex;justify-content:space-between;align-items:center;gap:6px">
    <h2 style="margin:0">Accounts <span class="muted" id="acctSummary"></span></h2>
    <span class="exp" id="filterChevron">&#9656;</span>
  </div>
  <div id="filterBody" class="hidden">
    <div style="display:flex;justify-content:flex-end;gap:4px;margin:8px 0 2px"><button class="linkbtn" id="selAll">Select all</button><button class="linkbtn" id="selNone">Clear</button></div>
    <div class="chips" id="acctChips"></div>
  </div>
</div>

<div class="tabbar">
  <button data-t="keyinsights" class="active">Key Insights</button>
  <button data-t="snapshot">Portfolio Snapshot</button>
  <button data-t="actions">Suggested Actions</button>
  <button data-t="data">Full Data Views</button>
</div>

<!-- ================= KEY INSIGHTS — on track? what needs to change? ================= -->
<div id="tab-keyinsights">
  <div id="valueNotes"></div>
  <div id="synthesis"></div>

  <div class="card">
    <h2>Momentum — Is It Working?</h2>
    <div id="momentumVerdict"></div>
    <p class="muted" id="momentumIntro" style="margin:0 0 12px"></p>
    <div id="momentumCaveats"></div>
    <div class="grid three" id="momentumTiles"></div>
  </div>

  <div class="card">
    <h2>Goals &amp; Milestones</h2>
    <div id="goalsPanel"></div>
  </div>
</div>

<!-- ================= PORTFOLIO SNAPSHOT — where the money sits today ================= -->
<div id="tab-snapshot" class="hidden">
  <div class="grid cards">
    <div class="card kpi" style="margin:0"><div class="label">Net Worth (selected)</div><div class="val" id="kTotal"></div><div class="hint" id="kTotalHint"></div></div>
    <div class="card kpi" style="margin:0"><div class="label">Projected 2031 (base)</div><div class="val" id="kProj"></div><div class="hint" id="kProjHint"></div></div>
    <div class="card kpi" style="margin:0"><div class="label">Biggest Single Stock</div><div class="val" id="kConc"></div><div class="hint" id="kConcHint"></div><div id="kConcFlag" style="margin-top:5px"></div></div>
    <div class="card kpi" style="margin:0"><div class="label">Unrealized Gain</div><div class="val" id="kGain"></div><div class="hint" id="kGainHint"></div></div>
  </div>

  <div class="card"><h2>Where You Stand</h2><p id="snapshotAnalysis" style="margin:0;font-size:13px;line-height:1.6;color:var(--ink-soft)"></p></div>

  <div class="card">
    <h2>Where Your Risk Is Concentrated</h2>
    <div class="grid three" id="riskTiles"></div>
    <p class="muted" id="riskNote" style="margin-top:12px"></p>
  </div>

  <div class="card"><h2>Sector Exposure (look-through)</h2><div class="donut-row"><div style="flex:1 1 260px;min-width:220px;height:280px"><canvas id="sectorChart"></canvas></div><div class="legend" id="sectorLegend"></div></div></div>

  <div class="card">
    <h2>Strategic Benchmarks — You vs the Market</h2>
    <div class="grid three">
      <div><div class="subh">US vs International (of equity)</div><div style="height:160px"><canvas id="usIntlChart"></canvas></div><p class="muted" id="usIntlNote" style="margin-top:8px"></p></div>
      <div><div class="subh">Asset-Class Mix (of total)</div><div style="height:160px"><canvas id="assetChart"></canvas></div><p class="muted" id="assetNote" style="margin-top:8px"></p></div>
      <div><div class="subh">Top 3 Sectors vs Analyst (aggressive)</div><div style="height:160px"><canvas id="top3Chart"></canvas></div><p class="muted" id="top3Note" style="margin-top:8px"></p></div>
    </div>
    <p class="muted" id="benchSrc" style="margin-top:12px"></p>
  </div>

  <div class="card">
    <h2>Sector Positioning — Current vs Recommended</h2>
    <p class="muted" style="margin:6px 0 12px">How far each sector sits <b style="color:var(--rust)">above</b> or <b style="color:var(--ash)">below</b> your strategic target, in points of total portfolio. Bigger bar = bigger active bet. The tags below show the 2026 earnings-growth outlook, so you can see whether your tilts point where growth actually is.</p>
    <div style="height:430px"><canvas id="deltaChart"></canvas></div>
    <div id="growthStrip" style="margin-top:16px"></div>
    <div id="whyMatters" class="callout" style="margin-top:12px"></div>
    <p class="muted" id="recSrc" style="margin-top:10px"></p>
  </div>

  <div class="card card-quiet">
    <h2>What's Moving Your Portfolio</h2>
    <div class="grid three" id="research"></div>
  </div>
</div>

<!-- ================= SUGGESTED ACTIONS ================= -->
<div id="tab-actions" class="hidden">
  <div class="card"><h2>Investment Analysis — Top Takeaways &amp; Actions</h2><div id="analysis"></div></div>
</div>

<!-- ================= FULL DATA VIEWS — forecast, holdings, log, research ================= -->
<div id="tab-data" class="hidden">
  <div class="card">
    <h2>5-Year Net-Worth Forecast</h2>
    <p class="muted" style="margin:0 0 12px">Each account compounds its balance <b>plus monthly contributions</b> at a blended rate from its asset mix (equity 8%, bonds 4%, gold 3%, private 10%, cash 2% base; bear/bull flex equity &amp; private). Contributions (all scenarios): <span id="contribText"></span>. Excludes taxes, fees, raises, and future RSU grants. Projections, not promises.</p>
    <div class="grid three" id="fcTiles"></div>
    <div style="overflow-x:auto;margin-top:14px"><table id="fcTable"><thead><tr><th class="l nos">Account</th><th class="nos">Now</th><th class="nos">+ /mo</th><th class="nos">Blended rate</th><th class="nos">2031 (base)</th><th class="nos">2031 range</th></tr></thead><tbody></tbody></table></div>
    <div id="fcNotes" style="margin-top:10px"></div>
    <div class="callout" style="margin-top:14px">
      <b>What if you redirected more toward the international/bonds gap?</b>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px">
        <label class="muted" style="font-size:12.5px">Extra $/mo toward intl+bonds:
          <input type="number" id="whatIfExtra" value="0" min="0" step="50" style="width:90px;margin-left:6px;padding:4px 7px;border:1px solid var(--line);border-radius:6px;font-size:12.5px;background:var(--surface);color:var(--ink)">
        </label>
        <span id="whatIfResult" class="muted" style="font-size:12.5px"></span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2 style="margin:0 0 4px">Holdings <span class="muted" id="hcount"></span></h2>
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
      <div class="toggle" id="viewToggle" style="margin:0"><button data-v="symbol" class="active">By symbol</button><button data-v="group">By sector group</button><button data-v="account">By account</button></div>
      <label class="muted" style="font-size:12px">Sector: <select id="sectorFilter" style="font-size:12.5px;padding:4px 8px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink)"></select></label>
      <span style="flex:1"></span>
      <button class="linkbtn" id="expAll">Expand all</button><button class="linkbtn" id="collapseAll">Collapse all</button>
    </div>
    <p class="muted" id="symNote" style="margin:0 0 8px">Positions summed across accounts. Click a row with ▸ to break it out by account. Click any column header to sort.</p>
    <div style="overflow-x:auto"><table id="holdings"><thead><tr><th class="l" data-k="sym">Symbol</th><th class="l" data-k="name">Name</th><th data-k="value">Value</th><th data-k="wt">Weight</th><th data-k="gl">Unreal. G/L</th><th data-k="glp">G/L %</th></tr></thead><tbody></tbody></table></div>
  </div>

  <div class="card card-quiet">
    <h2>Decision Log — What You've Changed and Why</h2>
    <div id="decisionLog"></div>
  </div>
</div>

<p class="foot" id="foot"></p></div>
<script>
const D = /*__DATA__*/null;
const fmt0=n=>(n<0?"-$":"$")+Math.abs(Math.round(n)).toLocaleString();
const fmtK=n=>{n=Math.round(n);return (n<0?"-$":"$")+Math.abs(n).toLocaleString();};
const fmtP=n=>(n>=0?"+":"")+n.toFixed(1)+"%";
const REC=D.recommended, GICS=D.gics, FR=D.forecastRates;
const EQUITY_KEYS=GICS.concat(["Intl ex-US"]);
let selected=new Set(D.accounts);
let view="symbol", sortK="value", sortDir=-1, expanded=new Set(), expandedGroups=null, expandedAccts=null, sectorFilter="__all";
let sectorChart=null, usIntlChart=null, assetChart=null, top3Chart=null, deltaChart=null;
// Chart.js defaults to dark tick/legend text and near-black gridlines, both
// invisible on this dark shell — set the readable dark-mode equivalents
// once, globally, before any chart is created.
Chart.defaults.color="#4c576a";
Chart.defaults.borderColor="rgba(0,0,0,0.08)";

document.getElementById("asof").textContent="As of "+D.asof+(D.note?" — "+D.note:"");

// Deliberate, dated valuation/contribution assumptions that override raw
// statement data (a private mark ahead of an IPO, a paused contribution) —
// amber, not red: these aren't parsing problems, they're modeling choices
// the user asked for. Still surfaced prominently since they change the
// headline numbers.
if(D.valueNotes && D.valueNotes.length){
  document.getElementById("valueNotes").innerHTML=D.valueNotes.map(w=>`<p class="notefoot"><b>Assumption applied:</b> ${w}</p>`).join("");
}

// contributions sentence — generated from D.contributions so it can never
// drift out of sync with the numbers actually driving the forecast math.
(function(){
  const parts=Object.keys(D.contributions||{}).filter(a=>D.contributions[a]>0).map(a=>{
    const label=(D.contribLabels&&D.contribLabels[a])||a;
    return label+" +"+fmt0(D.contributions[a])+"/mo";
  });
  document.getElementById("contribText").textContent=parts.join(", ")||"none on file";
})();

// ---- momentum / trend — portfolio-wide, rendered once (not filtered by
// account selection — the whole point is comparing this month's TOTAL
// picture to prior months, not a filtered slice of it). ----
function sparkline(values, w, h){
  const vals=values.filter(v=>v!=null);
  if(vals.length<2) return "";
  const min=Math.min(...vals), max=Math.max(...vals), span=(max-min)||1;
  const step=w/(values.length-1);
  let pts=[];
  values.forEach((v,i)=>{ if(v!=null) pts.push(`${(i*step).toFixed(1)},${(h-((v-min)/span)*h).toFixed(1)}`); });
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" style="stroke:var(--clay)" stroke-width="2" points="${pts.join(" ")}"/></svg>`;
}
function renderMomentum(){
  const pts=(D.trend&&D.trend.points)||[];
  if(pts.length<2){
    document.getElementById("momentumCaveats").innerHTML="";
    document.getElementById("momentumIntro").textContent="Trend builds after 2+ months of saved dashboards — nothing to compare yet.";
    document.getElementById("momentumTiles").innerHTML="";
    return;
  }
  document.getElementById("momentumIntro").textContent=pts.length+" months on record ("+pts[0].month+" – "+pts[pts.length-1].month+"). Reading month-over-month, not just this snapshot.";
  // ---- verdict: is the TRAJECTORY improving or backsliding, in hard
  // numbers? Deliberately different vocabulary from the top Portfolio
  // Health banner ("On track" / "Needs attention"), which judges whether an
  // action-worthy gap is open RIGHT NOW. This one judges direction of
  // travel over time, and backs that judgment with a real number: the
  // dollar change is split into (a) newly-tracked accounts, (b) a value
  // markup, and (c) everything else — the closest honest read of real
  // growth — then, when a market benchmark is configured (D.marketBenchmark
  // — see MARKET_BENCHMARK, loaded from market-assumptions.json), compared
  // to that benchmark over the same stretch.
  (function(){
    const last=pts[pts.length-1], prev=pts[pts.length-2];
    const vEl=document.getElementById("momentumVerdict");
    const fEl=document.getElementById("momentumCaveats");
    if(!prev){ vEl.innerHTML=""; fEl.innerHTML=""; return; }
    const totalDelta=last.total-prev.total;
    const lastAccts=last.accounts||{}, prevAccts=prev.accounts||{};
    const newAcctNames=Object.keys(lastAccts).filter(a=>!(a in prevAccts));
    const newAcctsValue=newAcctNames.reduce((s,a)=>s+(lastAccts[a]||0),0);
    const markedRows=D.holdings.filter(h=>h.valueMarked);
    const markupAmt=markedRows.reduce((s,h)=>s+(h.value-(h.markOriginalValue==null?h.value:h.markOriginalValue)),0);
    const organicDelta=totalDelta-newAcctsValue-markupAmt;
    const organicPct=prev.total?organicDelta/prev.total*100:0;
    // A market benchmark is optional (market-assumptions.json may ship it
    // empty/unset) — treat it as "not configured" unless it carries a real
    // retrieval date, so the comparison degrades gracefully (skipped) rather
    // than rendering "up about 0% over ''" when nobody's filled it in yet.
    const mb=(D.marketBenchmark&&D.marketBenchmark.asof)?D.marketBenchmark:null;
    const beatMarket=mb&&organicPct>mb.pct;

    // ---- "what drove the change" — a plain bulleted breakdown that always
    // adds up to the full dollar change, instead of boxed caveat text. ----
    const factors=[];
    if(newAcctsValue>0.5) factors.push(`<b>${fmt0(newAcctsValue)}</b> from ${newAcctNames.length} newly-tracked account${newAcctNames.length===1?"":"s"} (${newAcctNames.join(", ")}), not new growth, just accounts we started tracking`);
    if(markupAmt>0.5) factors.push(`<b>${fmt0(markupAmt)}</b> from marking ${markedRows.map(h=>h.account).join(", ")} to an estimated value, a modeled estimate, not cash`);
    factors.push(`<b>${fmt0(organicDelta)}</b> (${organicPct>=0?"+":""}${organicPct.toFixed(1)}%) from everything else, your own contributions plus real market movement, the closest honest read of actual growth`);
    fEl.innerHTML=`<div class="factors"><div class="fhead">What drove the ${fmt0(totalDelta)} change since ${prev.month}</div><ul>${factors.map(f=>`<li>${f}</li>`).join("")}</ul>${mb?`<p class="notefoot">${mb.periodLabel||"Benchmark"} comparison: as of ${mb.asof}. Sources: ${mb.sources.map(s=>`<a href="${s[1]}" target="_blank">${s[0]}</a>`).join(" · ")}. Your number above includes contributions, not just market movement, so it's not a perfectly clean comparison.</p>`:""}</div>`;

    const techGapNow=last.tech_pct-REC["Info Tech"], techGapPrev=prev.tech_pct-REC["Info Tech"];
    const bondsGapNow=last.bonds_pct-REC["Bonds"], bondsGapPrev=prev.bonds_pct-REC["Bonds"];
    // "Worse" = moved FURTHER from target, whichever direction that is.
    // Comparing raw gap values (not their absolute distance from 0) was a
    // real bug: an overweight sector has a positive gap (so worse = gap
    // growing) but an underweight one has a negative gap (so worse = gap
    // shrinking, i.e. more negative) — the same ">" test silently called an
    // underweight "not worse" while it was quietly drifting further from
    // target.
    const techWorse=Math.abs(techGapNow)>Math.abs(techGapPrev)+0.1;
    const bondsWorse=Math.abs(bondsGapNow)>Math.abs(bondsGapPrev)+0.1;
    const totalPct=prev.total?totalDelta/prev.total*100:0;
    let cls,label;
    if(totalPct<-1){ cls="attn"; label="Trending down"; }
    else if(totalPct>1){ cls="ok"; label="Trending up"; }
    else { cls="mixed"; label="Trending steady"; }

    let concSentence;
    if(!techWorse&&!bondsWorse) concSentence="Portfolio concentrations in tech and bonds are both closing toward target.";
    else if(techWorse&&bondsWorse) concSentence="Tech and bonds both drifted further from target this month, worth a look.";
    else if(techWorse) concSentence="Tech drifted further from target this month; bonds held steady or improved.";
    else concSentence="Bonds drifted further from target this month; tech is closing in the right direction.";

    // Action count mirrors the tk array built in renderAll() (1 base
    // concentration-watch card + 1 conditional markup card + 2 fixed cards)
    // — kept in sync by hand since momentum is deliberately
    // portfolio-wide/unfiltered while tk respects the account filter, so the
    // two can't share one function.
    const actionCount=3+(markupAmt>0.5?1:0);

    const MNAMES=["January","February","March","April","May","June","July","August","September","October","November","December"];
    const monthLabel=m=>{const [y,mo]=m.split("-");return MNAMES[+mo-1]+" "+y;};
    const [prevY,prevMo]=prev.month.split("-"), [lastY,lastMo]=last.month.split("-");
    const periodLabel=prevY===lastY?`${MNAMES[+prevMo-1]} to ${monthLabel(last.month)}`:`${monthLabel(prev.month)} to ${monthLabel(last.month)}`;
    let msg=`Net worth grew ${totalPct>=0?"+":""}${totalPct.toFixed(1)}% from ${periodLabel}. `;
    msg+=`Part of that is newly-tracked accounts or a value markup, not market movement, see notes below. `;
    if(mb){
      msg+=`Once you back out the items below, the real change was about ${fmtK(organicDelta)} (${organicPct>=0?"+":""}${organicPct.toFixed(1)}%). The benchmark was up about ${mb.pct}% over the same stretch, so you came in ${beatMarket?"ahead of":"behind"} it this period. `;
    }
    msg+=concSentence+" ";
    msg+=`${actionCount} targeted action${actionCount===1?"":"s"} on the Suggested Actions tab could improve concentration risk and allocation balance in your portfolio.`;
    vEl.innerHTML=`<div class="mverdict ${cls}"><b>${label}.</b> ${msg}</div>`;
  })();
  const metrics=[
    {k:"total",label:"Net Worth",fmt:fmtK},
    {k:"tech_pct",label:"Tech %",fmt:v=>v.toFixed(1)+"%"},
    {k:"intl_eq_pct",label:"Intl % of equity",fmt:v=>v.toFixed(1)+"%"},
    {k:"bonds_pct",label:"Bonds %",fmt:v=>v.toFixed(1)+"%"},
    {k:"largest_stock_pct",label:"Largest stock %",fmt:v=>v.toFixed(1)+"%"},
  ];
  document.getElementById("momentumTiles").innerHTML=metrics.map(m=>{
    const series=pts.map(p=>p[m.k]);
    const last=series[series.length-1];
    const priorSeries=series.slice(0,-1);
    let prevIdx=null; for(let i=priorSeries.length-1;i>=0;i--){ if(priorSeries[i]!=null){ prevIdx=i; break; } }
    const prev=prevIdx!=null?series[prevIdx]:null;
    let deltaHtml="—";
    if(last!=null && prev!=null){
      const d=last-prev, dir=Math.abs(d)<0.05?"flat":(d>0?"up":"down");
      const arrow=dir==="flat"?"▬":(dir==="up"?"▲":"▼");
      deltaHtml=`<span class="mdelta ${dir}">${arrow} ${(d>=0?"+":"")+(m.k==="total"?fmt0(d):d.toFixed(1)+"pt")}</span> vs ${pts[prevIdx].month}`;
    }
    return `<div class="tile mtile"><div class="t">${m.label}</div><div class="v">${last!=null?m.fmt(last):"—"}</div><div class="s">${deltaHtml}</div>${sparkline(series,140,28)}</div>`;
  }).join("");
}
renderMomentum();

// ---- goals & milestones — only ever populated with a real, sourced target;
// an empty slot renders as "not set", never a guessed number. ----
function renderGoals(){
  const goals=D.goals||{};
  const keys=Object.keys(goals);
  let html=keys.map(k=>{
    const g=goals[k];
    const pct=g.target?Math.max(0,g.current/g.target*100):0, over=pct>=100;
    return `<div style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px"><b>${k}</b><span class="muted" style="font-size:12.5px">${fmtK(g.current)} of ${fmtK(g.target)} (${pct.toFixed(0)}%)</span></div>
      <div class="goalbar"><div class="fill ${over?"over":""}" style="width:${Math.min(100,pct)}%"></div></div>
      <p class="muted" style="font-size:11.5px;margin:4px 0 0">${g.source||""}</p>
      <p class="muted" style="font-size:11.5px;margin:2px 0 0">${g.note||""}</p>
    </div>`;
  }).join("");
  html+=`<p class="muted" style="font-size:11.5px;margin-top:4px">${keys.length?"Other goals":"No goals configured yet"} (e.g. a near-term liquidity target, a house down payment) aren't set — tell Claude the number and it'll show up here.</p>`;
  document.getElementById("goalsPanel").innerHTML=html;
}
renderGoals();

// ---- decision log — a dated record of deliberate choices (yours or the
// model's), what each was expected to do, and where the numbers stand now. ----
function renderDecisionLog(){
  const log=(D.decisionLog||[]).slice().sort((a,b)=>(b.date||"").localeCompare(a.date||""));
  document.getElementById("decisionLog").innerHTML=log.length ? log.map(e=>`
    <div class="dlog">
      <div class="ddate">${e.date||"undated"} · ${e.status||"active"}</div>
      <h4>${e.decision}</h4>
      <p>${e.rationale||""}</p>
      ${e.note?`<p class="muted">${e.note}</p>`:""}
      ${e.current_value?`<span class="dcur">Currently: ${e.current_value}</span>`:""}
    </div>`).join("") : `<p class="muted">No decisions logged yet.</p>`;
}
renderDecisionLog();

// tabs
document.querySelectorAll(".tabbar button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll(".tabbar button").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  ["keyinsights","snapshot","actions","data"].forEach(t=>document.getElementById("tab-"+t).classList.toggle("hidden",t!==b.dataset.t));
  if(b.dataset.t==="snapshot"){ [sectorChart,usIntlChart,assetChart,top3Chart,deltaChart].forEach(c=>c&&c.resize()); }
}));

// account chips
function acctTotal(a){return D.holdings.filter(h=>h.account===a).reduce((s,h)=>s+h.value,0);}
function renderChips(){
  document.getElementById("acctSummary").textContent=`(${selected.size} of ${D.accounts.length} selected)`;
  document.getElementById("acctChips").innerHTML=D.accounts.map(a=>
    `<button type="button" class="chip ${selected.has(a)?'on':''}" aria-pressed="${selected.has(a)}" data-a="${a.replace(/"/g,'&quot;')}"><span class="sw"></span>${a} <span class="amt">${fmt0(acctTotal(a))}</span></button>`).join("");
  document.querySelectorAll("#acctChips .chip").forEach(c=>c.addEventListener("click",()=>{
    const a=c.dataset.a; if(selected.has(a))selected.delete(a); else selected.add(a);
    if(selected.size===0)selected.add(a); renderChips(); renderAll();
  }));
}
document.getElementById("selAll").onclick=()=>{selected=new Set(D.accounts);renderChips();renderAll();};
document.getElementById("selNone").onclick=()=>{selected=new Set([D.accounts[0]]);renderChips();renderAll();};
// Accounts accordion — collapsed by default so the filter (used
// occasionally) doesn't cost two rows of vertical space every visit; the
// summary count in the header stays visible either way.
document.getElementById("filterHead").addEventListener("click",()=>{
  const body=document.getElementById("filterBody"), open=!body.classList.contains("hidden");
  body.classList.toggle("hidden",open);
  document.getElementById("filterChevron").innerHTML=open?"&#9656;":"&#9662;";
});
document.getElementById("whatIfExtra").addEventListener("input",renderAll);

const sel=()=>D.holdings.filter(h=>selected.has(h.account));
function bucketTotals(rows){const bt={};rows.forEach(h=>{for(const k in h.buckets)bt[k]=(bt[k]||0)+h.buckets[k];});return bt;}

// forecast helpers — compound the balance AND monthly contributions (annuity FV)
const CONTRIB=D.contributions||{};
// One-off, dated overrides layered ONLY on the forecast (never on today's
// headline Net Worth KPI or any other tile — those keep reading `h.value`
// unmodified). See FORECAST_OVERRIDES in build_dashboard.py for sourcing.
const FCOV=D.forecastOverrides||{};
function classOf(k){ if(k==="Bonds")return"bond"; if(k==="Gold")return"gold"; if(k==="Private")return"private"; if(k==="Cash")return"cash"; return "equity"; }
function blendedRate(rows,scn){const val=rows.reduce((s,h)=>s+h.value,0);if(!val)return 0;const bt=bucketTotals(rows);let r=0;for(const k in bt)r+=bt[k]*FR[classOf(k)][scn];return r/val;}
function fcAccount(acct,scn){
  const r=D.holdings.filter(h=>h.account===acct);
  const dispVal=r.reduce((s,h)=>s+h.value,0); if(!dispVal)return{val:0,rate:0,proj:0,contrib:0,overridden:false};
  const ov=FCOV[acct]||{};
  const growthVal=dispVal*(ov.markMultiple||1);
  const rate=ov.rateClass ? FR[ov.rateClass][scn] : blendedRate(r,scn);
  const rm=Math.pow(1+rate,1/12)-1, C=CONTRIB[acct]||0;
  const periods=Math.max(0,60-(ov.skipMonths||0));
  const fvBal=growthVal*Math.pow(1+rate,5);
  const fvC=Math.abs(rm)>1e-9 ? C*((Math.pow(1+rm,periods)-1)/rm) : C*periods;
  // `val` stays the DISPLAYED current balance (unmarked) so the table's "Now"
  // column and Total row always match the rest of the dashboard; only the
  // compounding math (`proj`) sees the override.
  return {val:dispVal,rate,proj:fvBal+fvC,contrib:C,overridden:!!FCOV[acct]};
}
function fcTotal(accts,scn){let val=0,proj=0,contrib=0,wr=0;accts.forEach(a=>{const f=fcAccount(a,scn);val+=f.val;proj+=f.proj;contrib+=f.contrib;wr+=f.rate*f.val;});return{val,proj,contrib,rate:val?wr/val:0};}

function renderAll(){
  const rows=sel();
  const total=rows.reduce((s,h)=>s+h.value,0);
  const bt=bucketTotals(rows);
  const cash=bt["Cash"]||0, gl=rows.reduce((s,h)=>s+h.gl,0), cost=total-gl;
  const equity=EQUITY_KEYS.reduce((s,k)=>s+(bt[k]||0),0);
  const tech=bt["Info Tech"]||0, intl=bt["Intl ex-US"]||0, bonds=bt["Bonds"]||0;
  const intlEq=equity?intl/equity*100:0;

  document.getElementById("sub").innerHTML=selected.size+" of "+D.accounts.length+" accounts &middot; "+rows.length+" positions &middot; look-through estimates";

  // ---- forecast (sum of per-account projections incl. contributions) ----
  const selAccts=[...selected];
  const fBase=fcTotal(selAccts,"base"), fBear=fcTotal(selAccts,"bear"), fBull=fcTotal(selAccts,"bull");
  const monthlyContrib=selAccts.reduce((s,a)=>s+(CONTRIB[a]||0),0);

  // ---- KPIs ----
  document.getElementById("kTotal").textContent=fmtK(total);
  document.getElementById("kTotalHint").textContent=rows.length+" positions across "+selected.size+" acct(s)";
  document.getElementById("kProj").textContent=fmtK(fBase.proj);
  document.getElementById("kProjHint").textContent=fmtK(fBear.proj)+" – "+fmtK(fBull.proj)+" range";
  const g=document.getElementById("kGain");g.textContent=(gl>=0?"+":"")+fmt0(gl);g.className="val "+(gl>=0?"pos":"neg");
  document.getElementById("kGainHint").textContent=fmtP(cost?gl/cost*100:0)+" on cost";

  // ---- risk concentration (symbol / company level, not account) ----
  const byAcct={}; rows.forEach(h=>byAcct[h.account]=(byAcct[h.account]||0)+h.value);
  const agg=aggBySymbol(rows);
  const topPos=agg[0]||{sym:"—",value:0,kind:"fund"};
  const stocks=agg.filter(a=>a.kind==="stock");
  const topStock=stocks[0]||{sym:"—",value:0};
  const stockTotal=stocks.reduce((s,a)=>s+a.value,0);
  const top5Rows=agg.slice(0,5);
  const top5=top5Rows.reduce((s,a)=>s+a.value,0);
  const top5Syms=top5Rows.map(a=>a.sym).join(", ");
  const topSecKey=Object.keys(bt).filter(k=>k!=="Cash").sort((a,b)=>bt[b]-bt[a])[0]||"—";
  const priv=(bt["Private"]||0);
  // Private/illiquid holdings — named dynamically from whatever's actually in
  // `rows`, not hardcoded. A hardcoded account label here risks silently
  // mislabeling or hiding a second private holding, even a larger one —
  // same class of bug as the contributions sentence fixed elsewhere.
  const privRows=rows.filter(h=>h.kind==="private").sort((a,b)=>b.value-a.value);
  const privLabel=privRows.length ? privRows.map(h=>h.account+(h.valueMarked?" (marked, est.)":" (at cost)")).join(" + ") : "none currently";
  let cum=0,n50=0; for(const a of agg){cum+=a.value;n50++;if(cum>=total*0.5)break;}
  const isFund=topPos.kind!=="stock";
  document.getElementById("kConc").textContent=(total?topStock.value/total*100:0).toFixed(1)+"%";
  document.getElementById("kConcHint").textContent="in "+topStock.sym+" (largest single stock)";
  const concPct=total?topStock.value/total*100:0;
  // Concentration-watch symbols (e.g. employer stock) come entirely from
  // D.concentrationWatch (portfolio-profile.json) — never a hardcoded
  // ticker, so this works identically for any user, including one with no
  // watched symbol at all.
  const watchList=D.concentrationWatch||[];
  const watchHeld=watchList.map(w=>({...w,row:stocks.find(a=>a.sym===w.symbol)})).filter(w=>w.row&&w.row.value>0);
  const primaryWatch=watchHeld[0]||null;
  const topIsWatched=primaryWatch&&topStock.sym===primaryWatch.symbol;
  const concFlag=topIsWatched?(primaryWatch.employerLinked?"career-linked":"watched"):(concPct>5?"concentrated":null);
  document.getElementById("kConcFlag").innerHTML=concFlag?`<span class="flexTag watch">${concFlag}</span>`:"";
  const tiles=[
    ["Largest single stock",(total?topStock.value/total*100:0).toFixed(1)+"%",topStock.sym+" · "+fmt0(topStock.value)],
    ["In individual stocks",(total?stockTotal/total*100:0).toFixed(1)+"%",stocks.length+" single names"],
    ["Largest position",(total?topPos.value/total*100:0).toFixed(1)+"%",topPos.sym+(isFund?" · diversified fund":" · single stock")],
    ["Top sector (look-through)",(total?bt[topSecKey]/total*100:0).toFixed(1)+"%",topSecKey],
    ["Top 5 symbols","" +(total?(top5/total*100).toFixed(0):0)+"%",top5Syms+" · "+n50+" positions make up 50% of net worth"],
    ["Illiquid / private",(total?priv/total*100:0).toFixed(1)+"%",privLabel],
  ];
  document.getElementById("riskTiles").innerHTML=tiles.map(t=>`<div class="tile"><div class="t">${t[0]}</div><div class="v">${t[1]}</div><div class="s">${t[2]}</div></div>`).join("");
  document.getElementById("riskNote").innerHTML="Measured at the symbol level (a fund's sponsor isn't single-name risk): your biggest single-company bet is <b>"+topStock.sym+"</b> at "+(total?topStock.value/total*100:0).toFixed(1)+"% of net worth"+(topIsWatched&&primaryWatch.employerLinked?" — "+primaryWatch.label+", your employer, so paycheck and equity move together":"")+". Individual stocks are "+(total?stockTotal/total*100:0).toFixed(0)+"% of net worth; the rest is diversified funds. Your single largest line ("+topPos.sym+") is a "+(isFund?"diversified fund, not a concentration risk":"single stock")+". Top sector is <b>"+topSecKey+"</b> at "+(total?bt[topSecKey]/total*100:0).toFixed(0)+"%.";

  // ---- forecast tiles + table ----
  document.getElementById("fcTiles").innerHTML=[
    ["Bear 2031",fmtK(fBear.proj),(fBear.rate*100).toFixed(1)+"%/yr blended"],
    ["Base 2031",fmtK(fBase.proj),(fBase.rate*100).toFixed(1)+"%/yr blended"],
    ["Bull 2031",fmtK(fBull.proj),(fBull.rate*100).toFixed(1)+"%/yr blended"],
  ].map(t=>`<div class="tile"><div class="t">${t[0]}</div><div class="v">${t[1]}</div><div class="s">${t[2]}</div></div>`).join("");
  const accts=[...selected].filter(a=>byAcct[a]).sort((a,b)=>byAcct[b]-byAcct[a]);
  document.querySelector("#fcTable tbody").innerHTML=accts.map(a=>{
    const b=fcAccount(a,"base"),lo=fcAccount(a,"bear"),hi=fcAccount(a,"bull");
    const ov=FCOV[a];
    const nameCell=a+(b.overridden?' <sup title="Forecast-only adjustment — see note below">†</sup>':"");
    const contribHint=(ov&&ov.skipMonths)?` <span class="muted" style="font-size:11px">(paused ${ov.skipMonths}mo)</span>`:"";
    return `<tr><td class="l">${nameCell}</td><td>${fmtK(b.val)}</td><td>${b.contrib?"+"+fmtK(b.contrib)+contribHint:"—"}</td><td>${(b.rate*100).toFixed(1)}%</td><td>${fmtK(b.proj)}</td><td class="muted">${fmtK(lo.proj)} – ${fmtK(hi.proj)}</td></tr>`;
  }).join("")+`<tr class="grouphd"><td class="l">Total</td><td>${fmtK(fBase.val)}</td><td>+${fmtK(monthlyContrib)}</td><td>${(fBase.rate*100).toFixed(1)}%</td><td>${fmtK(fBase.proj)}</td><td>${fmtK(fBear.proj)} – ${fmtK(fBull.proj)}</td></tr>`;

  // footnotes for any account with an active forecast override, shown only
  // when that account is actually in the current selection.
  const activeNotes=accts.filter(a=>FCOV[a]&&FCOV[a].note);
  document.getElementById("fcNotes").innerHTML=activeNotes.length
    ? activeNotes.map(a=>`<p class="muted" style="font-size:12px;margin:4px 0"><b>† ${a}:</b> ${FCOV[a].note}</p>`).join("")
    : "";

  // ---- what-if: extra $/mo redirected toward the intl/bonds gap ----
  // Modeled at a 70% equity / 30% bond blended rate (matching the ETF mix
  // the Action above actually recommends — VXUS/VEA + a bond fund), applied
  // as its own 60-month ordinary annuity and added to the base projection.
  // This does NOT change any other tile — it's a standalone "what if" probe.
  (function(){
    const el=document.getElementById("whatIfExtra");
    const extra=Math.max(0,+el.value||0);
    const out=document.getElementById("whatIfResult");
    if(!extra){ out.textContent="Try an amount — e.g. $500/mo — to see the 2031 impact."; return; }
    const wiRate=0.7*FR.equity.base+0.3*FR.bond.base, wiRm=Math.pow(1+wiRate,1/12)-1;
    const wiFv=Math.abs(wiRm)>1e-9 ? extra*((Math.pow(1+wiRm,60)-1)/wiRm) : extra*60;
    out.innerHTML=`+${fmtK(wiFv)} to your 2031 base projection (modeled at a blended ${(wiRate*100).toFixed(1)}%/yr equity/bond rate) — new base total ≈ <b>${fmtK(fBase.proj+wiFv)}</b>.`;
  })();

  // ---- donut ----
  const donut=D.bucketOrder.filter(k=>(bt[k]||0)>0.5).map(k=>({n:k,v:bt[k],c:D.bucketColors[k]||"#888"}));
  if(sectorChart)sectorChart.destroy();
  sectorChart=new Chart(document.getElementById("sectorChart"),{type:"doughnut",
    data:{labels:donut.map(s=>s.n),datasets:[{data:donut.map(s=>s.v),backgroundColor:donut.map(s=>s.c),borderWidth:1,borderColor:"#ffffff"}]},
    options:{plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` ${c.label}: ${fmt0(c.raw)} (${(c.raw/total*100).toFixed(1)}%)`}}},cutout:"58%",responsive:true,maintainAspectRatio:false}});
  document.getElementById("sectorLegend").innerHTML=donut.map(s=>`<span><span class="dot" style="background:${s.c}"></span>${s.n} ${(s.v/total*100).toFixed(1)}%</span>`).join("");

  // ---- sector %s of total (for delta chart) ----
  const curPct={}; GICS.forEach(s=>curPct[s]=total?(bt[s]||0)/total*100:0);
  curPct["Intl ex-US"]=total?intl/total*100:0; curPct["Bonds"]=total?bonds/total*100:0;
  curPct["Gold / Alt"]=total?((bt["Gold"]||0)+(bt["Private"]||0))/total*100:0; curPct["Cash"]=total?cash/total*100:0;

  // ---- benchmark 1: US vs International (of equity) ----
  const usEq=GICS.reduce((s,k)=>s+(bt[k]||0),0);
  const usPct=equity?usEq/equity*100:0, intlPctEq=equity?intl/equity*100:0;
  if(usIntlChart)usIntlChart.destroy();
  usIntlChart=new Chart(document.getElementById("usIntlChart"),{type:"bar",
    data:{labels:["You","MSCI ACWI"],datasets:[{label:"US",data:[usPct,D.usIntlBench.US],backgroundColor:"#2563eb"},{label:"Intl",data:[intlPctEq,D.usIntlBench.Intl],backgroundColor:"#94a3b8"}]},
    options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,max:100,ticks:{callback:v=>v+"%"}},y:{stacked:true}},plugins:{legend:{position:"bottom"},tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${c.raw.toFixed(0)}%`}}}}});
  document.getElementById("usIntlNote").innerHTML=`<b>${usPct.toFixed(0)}% US</b> vs ${D.usIntlBench.US}% benchmark — ${Math.abs(usPct-D.usIntlBench.US)<3?"about in line":(usPct>D.usIntlBench.US?"over-tilted to the US":"under-weight US")}.`;

  // ---- benchmark 2: asset-class mix (of total) ----
  const am={Equity:equity,Bonds:bonds,Cash:cash,"Gold/Alt":(bt["Gold"]||0)+(bt["Private"]||0)};
  const amP=k=>total?am[k]/total*100:0;
  const aKeys=["Equity","Bonds","Cash","Gold/Alt"],aCol={Equity:"#2563eb",Bonds:"#0f766e",Cash:"#94a3b8","Gold/Alt":"#b8860b"};
  if(assetChart)assetChart.destroy();
  assetChart=new Chart(document.getElementById("assetChart"),{type:"bar",
    data:{labels:["You","Target"],datasets:aKeys.map(k=>({label:k,data:[amP(k),D.assetTarget[k]],backgroundColor:aCol[k]}))},
    options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,max:100,ticks:{callback:v=>v+"%"}},y:{stacked:true}},plugins:{legend:{position:"bottom"},tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${c.raw.toFixed(0)}%`}}}}});
  document.getElementById("assetNote").innerHTML=`Equity <b>${amP("Equity").toFixed(0)}%</b> vs ${D.assetTarget.Equity}%; bonds ${amP("Bonds").toFixed(0)}% vs ${D.assetTarget.Bonds}%.`;

  // ---- benchmark 3: top-3 sectors vs analyst aggressive (of equity) ----
  const eqPct=s=>equity?(bt[s]||0)/equity*100:0;
  const top3=GICS.slice().sort((a,b)=>(bt[b]||0)-(bt[a]||0)).slice(0,3);
  if(top3Chart)top3Chart.destroy();
  top3Chart=new Chart(document.getElementById("top3Chart"),{type:"bar",
    data:{labels:top3,datasets:[{label:"You",data:top3.map(eqPct),backgroundColor:"#2563eb"},{label:"Analyst aggr.",data:top3.map(s=>D.analystAggr[s]||0),backgroundColor:"#c3c9d1"}]},
    options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:v=>v+"%"}}},plugins:{legend:{position:"bottom"},tooltip:{callbacks:{label:c=>` ${c.dataset.label}: ${c.raw.toFixed(0)}%`}}}}});
  const t3=top3[0];
  document.getElementById("top3Note").innerHTML=`<b>${t3}</b> is ${eqPct(t3).toFixed(0)}% of equity vs analysts' ~${D.analystAggr[t3]||0}% even for aggressive books.`;
  document.getElementById("benchSrc").innerHTML="Benchmarks: "+[D.benchSources.acwi,D.benchSources.overweights].map(s=>`<a href="${s[1]}" target="_blank">${s[0]}</a>`).join(" · ")+". The aggressive sector view is a synthesized model, not one firm's portfolio.";

  // ---- delta chart: current vs recommended ----
  const dk=Object.keys(REC).map(k=>({k,c:curPct[k]||0,r:REC[k],d:+(((curPct[k]||0)-REC[k]).toFixed(1))})).sort((a,b)=>b.d-a.d);
  if(deltaChart)deltaChart.destroy();
  deltaChart=new Chart(document.getElementById("deltaChart"),{type:"bar",
    data:{labels:dk.map(o=>o.k),datasets:[{data:dk.map(o=>o.d),backgroundColor:dk.map(o=>o.d>0.5?"#b91c1c":o.d<-0.5?"#375168":"#c3c9d1")}]},
    options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,scales:{x:{ticks:{callback:v=>v+" pt"},grid:{color:"rgba(0,0,0,0.08)"}},y:{grid:{display:false}}},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>{const o=dk[c.dataIndex];return " current "+o.c.toFixed(1)+"% vs target "+o.r.toFixed(1)+"% ("+(o.d>0?"+":"")+o.d+" pts)";}}}}}});

  // ---- growth strip + why it matters ----
  document.getElementById("growthStrip").innerHTML=GICS.filter(s=>(bt[s]||0)>0).sort((a,b)=>(bt[b]||0)-(bt[a]||0)).map(s=>{const g=D.sectorGrowth[s]||{dir:"flat",note:""};const ic=g.dir==="up"?"▲":g.dir==="down"?"▼":"▬";const col=g.dir==="up"?"var(--moss)":g.dir==="down"?"var(--rust)":"var(--ink-faint)";return `<span class="gtag"><b style="color:${col}">${ic}</b> ${s} <span class="muted">· ${g.note}</span></span>`;}).join("");
  const over=dk[0], under=dk[dk.length-1], og=D.sectorGrowth[over.k], ug=D.sectorGrowth[under.k];
  document.getElementById("whyMatters").innerHTML=`<b>Why the deltas matter.</b> Biggest overweight: <b>${over.k} (+${over.d} pts)</b>${og?` — 2026: ${og.note}`:""}. Biggest gap: <b>${under.k} (${under.d} pts)</b>${ug&&ug.note?` — ${ug.note}`:""} — often the cheapest place to diversify. Health Care is the one sector with <i>declining</i> 2026 EPS, so a heavy tilt there fights the trend. A tilt only pays off when it lines up with where earnings actually grow.`;
  document.getElementById("recSrc").innerHTML=`Recommended = your target allocation from portfolio-profile.json (Equity ${D.assetTarget.Equity}% / Bonds ${D.assetTarget.Bonds}% / Gold-Alt ${D.assetTarget["Gold/Alt"]}% / Cash ${D.assetTarget.Cash}%). Sector growth context: `+[D.benchSources.earnings,D.benchSources.schwab].map(s=>`<a href="${s[1]}" target="_blank">${s[0]}</a>`).join(" · ")+".";

  // ---- "Where You Stand" — one paragraph tying the snapshot to goals AND
  // market benchmarks, so this tab doesn't leave the reader to synthesize
  // six separate charts into a verdict on their own. ----
  (function(){
    const usTilt=usPct-D.usIntlBench.US;
    const t3=top3[0], t3Gap=eqPct(t3)-(D.analystAggr[t3]||0);
    const goalKeys=Object.keys(D.goals||{});
    let goalSentence="No goals are set yet, so there's nothing to measure the plan against.";
    if(goalKeys.length){
      const gk=goalKeys[0], g=D.goals[gk];
      const pct=g.target?g.current/g.target*100:0;
      goalSentence=`Against your own goals, you're in good shape: ${gk.toLowerCase()} is at ${pct.toFixed(0)}% funded (${fmtK(g.current)} projected vs ${fmtK(g.target)} needed).`;
    }
    const biggestGap=Math.abs(dk[0].d)>=Math.abs(dk[dk.length-1].d)?dk[0]:dk[dk.length-1];
    document.getElementById("snapshotAnalysis").innerHTML=
      `Against the market, you're moderately tilted: <b>${usPct.toFixed(0)}% US</b> equity vs a ${D.usIntlBench.US}% world-market benchmark (${Math.abs(usTilt)<3?"close to in line":usTilt>0?`about ${Math.abs(usTilt).toFixed(0)}pt overweight US`:`about ${Math.abs(usTilt).toFixed(0)}pt underweight US`}), overall equity exposure at ${amP("Equity").toFixed(0)}% vs an ${D.assetTarget.Equity}% target, and your top sector (<b>${t3}</b>) running ${Math.abs(t3Gap).toFixed(0)}pt ${t3Gap>=0?"above":"below"} where an aggressive analyst book would sit. ${goalSentence} The single biggest gap on this page is <b>${biggestGap.k}</b> (${biggestGap.d>=0?"+":""}${biggestGap.d}pt vs target), which is what the Suggested Actions tab is built around, not a shortfall in the overall plan.`;
  })();

  // ---- investment analysis: top takeaways + actions (data-aware) ----
  const techPct=total?tech/total*100:0, bondsPct=total?bonds/total*100:0;
  const compoundOnly=total*Math.pow(1+fBase.rate,5);
  const growthMult=compoundOnly?fBase.proj/compoundOnly:1;
  // Holdings carrying a deliberate current-value mark (see VALUE_MARKS in
  // build_dashboard.py) — flagged here so a paper markup never reads as
  // liquidity in the takeaways, whatever account it's on in a given month.
  const markedRows=rows.filter(h=>h.valueMarked);
  const markupAmt=markedRows.reduce((s,h)=>s+(h.value-(h.markOriginalValue==null?h.value:h.markOriginalValue)),0);
  const markedAccts=[...new Set(markedRows.map(h=>h.account))].join(", ");
  // Each card carries a `sev` score (roughly "% of net worth this issue
  // touches") so the takeaways are RANKED by what the data says is biggest
  // this month, not fixed by where they happen to sit in this array. A
  // reinforcement card (nothing to fix, just confirming the engine's
  // working) gets a low fixed score so it naturally sinks unless every
  // other card is also quiet.
  const tk=[];
  // Concentration-watch takeaway — only emitted when a watched symbol is
  // actually held this month (primaryWatch, computed above from
  // D.concentrationWatch). A user with no watched symbol simply gets no
  // card here, rather than a stale or fabricated one.
  if(primaryWatch){
    const wRow=primaryWatch.row;
    const wPct=total?wRow.value/total*100:0;
    const wGlp=(wRow.value-wRow.gl)?wRow.gl/(wRow.value-wRow.gl)*100:0;
    const holdingAccounts=new Set(rows.filter(h=>h.sym===primaryWatch.symbol).map(h=>h.account));
    const contribActive=[...holdingAccounts].some(a=>(D.contributions[a]||0)>0);
    const employerClause=primaryWatch.employerLinked?", and you also work there":"";
    const employerBody=primaryWatch.employerLinked
      ?"a bad year here hits your job and your investments at the same time, that's what makes this different from an ordinary stock bet"
      :"this is a large enough single-stock bet that a bad year here would meaningfully dent your net worth on its own";
    tk.push({sev:wPct, tone:"var(--clay-solid)",
      h:`${primaryWatch.label} is your biggest single-stock risk${primaryWatch.employerLinked?", and it's tied to your paycheck too":""}`,
      d:`How it happened: ${primaryWatch.symbol} is your largest individual stock, <b>${wPct.toFixed(1)}% of your net worth</b> (${fmt0(wRow.value)}, currently ${wRow.gl>=0?"up":"down"} ${fmt0(Math.abs(wRow.gl))} / ${Math.abs(wGlp).toFixed(1)}% from what you paid)${employerClause}. What it means: ${employerBody}.`,
      a:[contribActive
           ? `Consider redirecting new contributions away from ${primaryWatch.symbol} as they vest — buying more just concentrates this same risk further.`
           : `New contributions toward ${primaryWatch.symbol} are already paused — that keeps this position from growing further; revisit once it shrinks as a share of net worth or the picture changes.`,
         `If you want to reduce this position, sell from a flexible account (see the account-flexibility tags in the forecast table) rather than one restricted to a single stock.`]});
  }
  if(markupAmt>0.5){
    tk.push({sev:total?markupAmt/total*100:0, tone:"#475569",h:"Part of this month's net worth number is a guess, not a fact",
      d:`How it happened: ${fmtK(markupAmt)} of your ${fmtK(total)} total is an estimate of what ${markedAccts||"a private holding"} is currently worth (see the note above) — not a number from an actual statement or trade. What it means: it's a reasonable guess, but it isn't cash, it isn't confirmed, and it'll move once a real number shows up. Treat <b>${fmtK(cash)}</b>, your actual cash across accounts, as the number you can count on for anything near-term.`,
      a:["Don't spend or plan against the full net worth total until that value is confirmed — use the cash figure instead.",
         "Once a real, confirmed price exists, swap this estimate for the real number."]});
  }
  // Gap size/direction pulled from `dk` — the SAME recommended-vs-current
  // delta data driving the Sector Positioning chart — instead of a
  // hardcoded target text that can silently go stale (this is exactly what
  // happened here: international flipped from underweight to overweight
  // after the June 2026 401(k) re-election, and a hand-typed "~28% target"
  // never caught up). Re-deriving it here means this takeaway can't drift
  // out of sync with the chart above it.
  const intlGap=dk.find(o=>o.k==="Intl ex-US")||{k:"Intl ex-US",c:0,r:REC["Intl ex-US"],d:0};
  const bondsGap=dk.find(o=>o.k==="Bonds")||{k:"Bonds",c:0,r:REC["Bonds"],d:0};
  const gapUsd=g=>total*Math.max(0,-g.d)/100;
  const intlGapUsd=gapUsd(intlGap), bondsGapUsd=gapUsd(bondsGap), combinedGapUsd=intlGapUsd+bondsGapUsd;
  // Pick the flexible account with the largest active contribution to point
  // the gap-closing action at — derived from D.accountFlex/D.contributions
  // (portfolio-profile.json), never a hardcoded account name, so this works
  // for any user's account lineup.
  const flexAccounts=Object.keys(D.accountFlex||{}).filter(a=>D.accountFlex[a].tag==="flexible"&&(D.contributions[a]||0)>0)
    .sort((a,b)=>(D.contributions[b]||0)-(D.contributions[a]||0));
  const gapAccountName=flexAccounts[0]||null;
  const gapFlex=gapAccountName?D.accountFlex[gapAccountName]:{tag:"flexible",note:"full brokerage"};
  const gapMonthly=gapAccountName?(D.contributions[gapAccountName]||0):0;
  const stillGap=intlGap.d<-0.5||bondsGap.d<-0.5;
  const monthsToClose=(gapMonthly&&combinedGapUsd>0)?Math.ceil(combinedGapUsd/gapMonthly):null;
  let tk3Headline;
  if(bondsGap.d<-0.5 && intlGap.d<-0.5) tk3Headline="You're still light on both international stocks and bonds, outside your 401(k)";
  else if(bondsGap.d<-0.5) tk3Headline="International caught up, bonds still need a nudge";
  else if(intlGap.d<-0.5) tk3Headline="Bonds look good, international still needs a nudge";
  else tk3Headline="International and bonds are basically where they should be";
  let tk3Body=`How it happened: <b>${intlGap.c.toFixed(1)}%</b> of your money is in international stocks (should be around ${intlGap.r}%) and <b>${bondsGap.c.toFixed(1)}%</b> is in bonds (should be around ${bondsGap.r}%). `;
  if(intlGap.d>0.5) tk3Body+=`International used to run light, but your 401(k)'s fund change in June fixed that on its own, so it's not somewhere to add more. `;
  if(bondsGap.d>0.5) tk3Body+=`Bonds have also drifted above where they need to be. `;
  const bothShort=bondsGap.d<-0.5&&intlGap.d<-0.5;
  if(stillGap){
    const parts=[]; if(bondsGap.d<-0.5)parts.push(bothShort?`bonds (${fmtK(bondsGapUsd)})`:"bonds"); if(intlGap.d<-0.5)parts.push(bothShort?`international (${fmtK(intlGapUsd)})`:"international");
    tk3Body+=`What it means: you're ${fmtK(combinedGapUsd)} short of target${bothShort?", split between":" in"} ${parts.join(" and ")}.`;
  } else {
    tk3Body+=`What it means: nothing to fix here this month.`;
  }
  const tk3Actions=[];
  if(stillGap){
    const bondsTheGap=bondsGap.d<-0.5, target=(bondsTheGap&&intlGap.d<-0.5)?"an international fund (VXUS/VEA) and a bond fund (BND/VGIT)":(bondsTheGap?"a bond fund (BND or VGIT)":"an international fund (VXUS/VEA plus an emerging-markets fund)");
    if(gapAccountName){
      tk3Actions.push(`Point your ${gapMonthly?fmt0(gapMonthly)+"/mo ":""}${gapAccountName} contribution at ${target} instead — that account can hold any stock or fund (<span class="flexTag ${gapFlex.tag}">${gapFlex.tag}</span>), so you can do this today without opening anything new.`);
    } else {
      tk3Actions.push(`Point your next taxable contribution at ${target} instead of adding to what you already hold.`);
    }
    if(monthsToClose) tk3Actions.push(`At that pace, this closes the remaining ${fmtK(combinedGapUsd)} gap in about ${monthsToClose} month${monthsToClose===1?"":"s"} (~${(monthsToClose/12).toFixed(1)} years) on its own.`);
    if(bondsTheGap){
      tk3Actions.push("Bear case: buying now locks in today's higher yield, but if rates keep rising, bond prices could still drift lower for a while before they stabilize, so don't be surprised by a paper loss even though the yield you're capturing is the attractive part.");
    }
  } else {
    tk3Actions.push("Nothing to do here this month, both are within half a point of target. We'll check again next month.");
  }
  const savingsActions=["Keep saving at the current pace. Send any extra toward the international/bonds gap above."];
  if(D.liquidityHorizon&&D.liquidityHorizon.note){
    savingsActions.push(`${D.liquidityHorizon.note} Your cash on hand (${fmtK(cash)}) is the number to check against that, not the headline net-worth total.`);
  }
  tk.push(
    {sev:stillGap?combinedGapUsd/total*100:0.1, tone:stillGap?"var(--amber-solid)":"var(--moss-solid)", h:tk3Headline, d:tk3Body, a:tk3Actions},
    {sev:0.5, tone:"var(--moss-solid)",h:"Your monthly saving is doing most of the work here",
     d:`How it happened: you're putting in roughly <b>${fmtK(monthlyContrib)}/mo</b> across your accounts. Just letting your current balance sit and grow would get you to ${fmtK(compoundOnly)} by 2031, adding your monthly contributions on top gets you to <b>${fmtK(fBase.proj)}</b> instead, about ${growthMult.toFixed(1)}x more. What it means: the habit of saving every month is doing more for your future than any single investment pick. The gap in the takeaway above is where the next extra dollar should go.`,
     a:savingsActions},
  );
  tk.sort((a,b)=>b.sev-a.sev);
  document.getElementById("analysis").innerHTML=tk.map((t,i)=>`<div class="tk" style="border-left-color:${t.tone}"><h4><span class="pnum" style="background:${t.tone}">${i+1}</span>${t.h}</h4><p>${t.d}</p><div class="act"><b>What to do</b><ul>${t.a.map(x=>`<li>${x}</li>`).join("")}</ul></div></div>`).join("");

  // ---- portfolio health synthesis: the one paragraph that answers "am I on
  // track, do I need to change anything" — always visible above the tab bar.
  // Verdict logic: a still-open intl/bonds gap or a net-worth drop this month
  // means attention; a markup/structural caveat with no open gap means mixed;
  // otherwise on track. Reuses the SAME stillGap/tk data driving the takeaway
  // cards above so this can't disagree with them.
  (function(){
    const nwPts=(D.trend&&D.trend.points)||[];
    const nwPrev=nwPts.length>1?nwPts[nwPts.length-2].total:null;
    const nwDelta=nwPrev!=null?total-nwPrev:null;
    const structural=(D.trend.caveats&&D.trend.caveats.length>0)||markupAmt>0.5;
    let cls,label;
    if(stillGap || (nwDelta!=null && nwDelta<0)){ cls="attn"; label="Needs attention"; }
    else if(structural){ cls="mixed"; label="Mixed"; }
    else { cls="ok"; label="On track"; }
    let p=`Net worth is <b>${fmtK(total)}</b>`+(nwDelta!=null?` (${nwDelta>=0?"+":""}${fmt0(nwDelta)} vs last month${structural?", partly reflecting newly-tracked accounts or a value markup rather than pure market movement":""})`:"")+`. `;
    if(primaryWatch){
      const wPct=total?primaryWatch.row.value/total*100:0;
      const holdingAccounts=new Set(rows.filter(h=>h.sym===primaryWatch.symbol).map(h=>h.account));
      const contribActive=[...holdingAccounts].some(a=>(D.contributions[a]||0)>0);
      p+=`Your standing concentration risk is ${primaryWatch.label} at <b>${wPct.toFixed(1)}% of net worth</b>`+(primaryWatch.employerLinked?" (career-linked, since your paycheck rides the same company)":"")+(contribActive?". ":" — new contributions toward it are already paused, so it's being managed, not growing. ");
    }
    if(stillGap){
      const parts=[]; if(bondsGap.d<-0.5)parts.push("bonds"); if(intlGap.d<-0.5)parts.push("international");
      p+=`The open gap this month is ${parts.join(" and ")} (${fmtK(combinedGapUsd)} short of target)`+(monthsToClose&&gapAccountName?`; the ${gapAccountName} contribution already points there and closes it in about ${monthsToClose} month${monthsToClose===1?"":"s"} if nothing else changes`:"")+". ";
    } else {
      p+="International and bonds are both within half a point of target this month, no rebalancing needed there. ";
    }
    if(markupAmt>0.5){ p+=`Treat cash (<b>${fmtK(cash)}</b>) as the number that covers near-term needs, not the headline total, since ${fmtK(markupAmt)} of it is an unverified pre-IPO markup.`; }
    document.getElementById("synthesis").innerHTML=`<div class="synthesis ${cls}"><span class="verdict">${label}</span><p>${p}</p></div>`;
  })();

  // ---- research (static) ----
  document.getElementById("research").innerHTML=D.research.map(r=>`<div class="rcard" style="border-left-color:${r.color}"><span class="tag" style="background:${r.color}">${r.tone}</span><h3>${r.name}</h3><p class="muted" style="margin:-2px 0 8px">As of ${r.asof||"unknown — flag this tile"}</p><p class="hl">${r.headline}</p><div class="sw"><b>So what:</b> ${r.sowhat}</div><div class="src">${r.sources.map(s=>`<a href="${s[1]}" target="_blank">${s[0]}</a>`).join(" · ")}</div></div>`).join("");

  renderHoldings(rows,total);
}

// ---- holdings ----
function aggBySymbol(rows){
  const m={};
  rows.forEach(h=>{const k=h.sym;if(!m[k])m[k]={sym:h.sym,name:h.name,cat:h.cat,group:h.group,kind:h.kind,value:0,gl:0,children:[]};m[k].value+=h.value;m[k].gl+=h.gl;m[k].children.push(h);});
  return Object.values(m).sort((a,b)=>b.value-a.value);
}
function glpOf(v,g){return (v-g)?g/(v-g)*100:0;}
function cmp(a,b){
  if(sortK==="sym"||sortK==="name")return ((a[sortK]||"")).localeCompare(b[sortK]||"")*sortDir;
  let x,y;
  if(sortK==="glp"){x=glpOf(a.value,a.gl);y=glpOf(b.value,b.gl);}
  else{const k=(sortK==="wt")?"value":sortK;x=a[k]||0;y=b[k]||0;}
  return (x-y)*sortDir;
}
function ensureExpState(){ if(expandedGroups===null)expandedGroups=new Set(D.groupOrder); if(expandedAccts===null)expandedAccts=new Set(D.accounts); }
function aggRow(a,total){
  const glp=glpOf(a.value,a.gl);const cls=a.gl>=0?"pos":"neg";
  const many=a.children.length>1;const open=expanded.has(a.sym);
  const exp=many?`<span class="exp">${open?"▾":"▸"}</span>`:`<span class="exp"></span>`;
  return `<tr data-sym="${a.sym}" style="cursor:${many?'pointer':'default'}"><td class="l tick">${exp}${a.sym}</td><td class="l">${a.name}<div class="muted">${a.cat}${many?" · "+a.children.length+" accounts":""}</div></td><td>${fmt0(a.value)}</td><td>${(a.value/total*100).toFixed(1)}%</td><td class="${cls}">${(a.gl>=0?"+":"")+fmt0(a.gl)}</td><td class="${cls}">${fmtP(glp)}</td></tr>`;
}
function childRows(a,total){
  return a.children.slice().sort(cmp).map(h=>{const cls=h.gl>=0?"pos":"neg";return `<tr class="child"><td class="l">${h.account}</td><td class="l muted">${h.qty?h.qty+" sh":""}${h.price?" @ $"+h.price.toLocaleString():""}</td><td>${fmt0(h.value)}</td><td>${(h.value/total*100).toFixed(1)}%</td><td class="${cls}">${(h.gl>=0?"+":"")+fmt0(h.gl)}</td><td class="${cls}">${fmtP(h.glp)}</td></tr>`;}).join("");
}
function plainRow(h,total){const cls=h.gl>=0?"pos":"neg";const px=h.price?` @ $${h.price.toLocaleString()}`:"";const sub=(view==="group"?h.account:h.cat)+px;return `<tr><td class="l tick">${h.sym}</td><td class="l">${h.name}<div class="muted">${sub}</div></td><td>${fmt0(h.value)}</td><td>${(h.value/total*100).toFixed(1)}%</td><td class="${cls}">${(h.gl>=0?"+":"")+fmt0(h.gl)}</td><td class="${cls}">${fmtP(h.glp)}</td></tr>`;}
function renderHoldings(rows,total){
  ensureExpState();
  const fr=sectorFilter==="__all"?rows:rows.filter(h=>h.group===sectorFilter);
  const uniq=new Set(fr.map(h=>h.sym)).size;
  document.getElementById("hcount").textContent=`(${uniq} unique position${uniq===1?"":"s"} · ${fr.length} lines)`;
  document.getElementById("symNote").style.display=view==="symbol"?"block":"none";
  const tb=document.querySelector("#holdings tbody");
  if(view==="symbol"){
    const agg=aggBySymbol(fr).sort(cmp);
    let html="";agg.forEach(a=>{html+=aggRow(a,total);if(expanded.has(a.sym)&&a.children.length>1)html+=childRows(a,total);});
    tb.innerHTML=html;
    tb.querySelectorAll("tr[data-sym]").forEach(tr=>tr.addEventListener("click",()=>{const s=tr.dataset.sym;if(expanded.has(s))expanded.delete(s);else expanded.add(s);renderHoldings(sel(),total);}));
  } else {
    const key=view==="group"?"group":"account";const order=view==="group"?D.groupOrder:D.accounts;const expSet=view==="group"?expandedGroups:expandedAccts;
    let html="";
    order.forEach(g=>{
      const mem=fr.filter(h=>h[key]===g).sort(cmp);if(!mem.length)return;
      const sv=mem.reduce((s,h)=>s+h.value,0),sg=mem.reduce((s,h)=>s+h.gl,0);const open=expSet.has(g);
      html+=`<tr class="grouphd" data-grp="${(""+g).replace(/"/g,'&quot;')}" style="cursor:pointer"><td class="l" colspan="2"><span class="exp">${open?"▾":"▸"}</span>${g} <span class="muted">(${mem.length})</span></td><td>${fmt0(sv)}</td><td>${(sv/total*100).toFixed(1)}%</td><td class="${sg>=0?'pos':'neg'}">${(sg>=0?"+":"")+fmt0(sg)}</td><td></td></tr>`;
      if(open)html+=mem.map(h=>plainRow(h,total)).join("");
    });
    tb.innerHTML=html;
    tb.querySelectorAll("tr[data-grp]").forEach(tr=>tr.addEventListener("click",()=>{const g=tr.dataset.grp;if(expSet.has(g))expSet.delete(g);else expSet.add(g);renderHoldings(sel(),total);}));
  }
}
const hTotal=()=>sel().reduce((s,h)=>s+h.value,0);
function populateSectorFilter(){
  const groups=D.groupOrder.filter(g=>D.holdings.some(h=>h.group===g));
  const el=document.getElementById("sectorFilter");
  el.innerHTML='<option value="__all">All sectors</option>'+groups.map(g=>`<option value="${g}">${g}</option>`).join("");
  el.addEventListener("change",()=>{sectorFilter=el.value;renderHoldings(sel(),hTotal());});
}
document.querySelectorAll("#holdings th").forEach(th=>th.addEventListener("click",()=>{const k=th.dataset.k;if(k===sortK)sortDir*=-1;else{sortK=k;sortDir=(k==="sym"||k==="name")?1:-1;}renderHoldings(sel(),hTotal());}));
document.querySelectorAll("#viewToggle button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll("#viewToggle button").forEach(x=>x.classList.remove("active"));b.classList.add("active");view=b.dataset.v;renderHoldings(sel(),hTotal());}));
document.getElementById("expAll").onclick=()=>{ensureExpState();if(view==="symbol")aggBySymbol(sel()).forEach(a=>{if(a.children.length>1)expanded.add(a.sym);});else if(view==="group")expandedGroups=new Set(D.groupOrder);else expandedAccts=new Set(D.accounts);renderHoldings(sel(),hTotal());};
document.getElementById("collapseAll").onclick=()=>{if(view==="symbol")expanded.clear();else if(view==="group")expandedGroups=new Set();else expandedAccts=new Set();renderHoldings(sel(),hTotal());};
populateSectorFilter();

document.getElementById("foot").innerHTML="Aggregated across all statements in the month folder. Look-through sector weights, forecast rates, and the recommended model are estimates — not investment advice. Forecasts assume steady annual returns and ignore future contributions, taxes, and fees. Sources: S&amp;P 500 GICS weights (S&amp;P DJI, 2026); Vanguard target-date methodology; sector citations inline.<br>Generated by build_dashboard.py "+D.scriptVersion+" on "+D.buildTime+".";
renderChips(); renderAll();
</script></body></html>"""

# --------------------------------------------------------------------------- #
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--profile",required=True,help="portfolio-profile.json")
    ap.add_argument("--accounts",required=True,help="This month's manual-accounts.json — the sole holdings input")
    ap.add_argument("--assumptions",help="market-assumptions.json (defaults to the plugin's shipped default)")
    ap.add_argument("--sector-research",help="Optional sector-research.json")
    ap.add_argument("--dir",help="Month folder — used only for the statement-completeness cross-check, not parsing")
    ap.add_argument("--out",required=True)
    ap.add_argument("--metrics"); ap.add_argument("--note",default="")
    ap.add_argument("--asof",help="Freeform 'as of' label for the header")
    args=ap.parse_args()

    load_config(args.profile, args.assumptions, args.sector_research)

    warnings=[]
    holdings=load_holdings_json(args.accounts) if os.path.exists(args.accounts) else []
    if not holdings:
        print("ERROR: no holdings in --accounts.",file=sys.stderr); sys.exit(2)
    asof=args.asof

    # Apply any deliberate, dated current-value marks (see VALUE_MARKS) before
    # anything downstream reads holding values — so the Net Worth KPI, donut,
    # holdings table, and risk tiles all pick up the marked value consistently
    # rather than the mark only showing up in one place. month_key is computed
    # here (not just below, by compute_aggregates) because apply_value_marks
    # needs it to gate marks by effectiveMonth — a backfilled/historical
    # month must not pick up a mark decided after that month happened.
    month_key=month_key_from_path(args.metrics or args.out)
    value_notes=apply_value_marks(holdings, month_key)

    # Folder-completeness check: a statement can sit in the month folder and
    # never make it into holdings (nobody hand-added it to --accounts) with
    # zero warning anywhere. Every holding is expected to carry a `source`
    # filename tag; this cross-checks every non-JSON/MD file in the folder
    # against the union of `source` values actually referenced by a holding —
    # real verification, not just a file listing.
    if args.dir and os.path.isdir(args.dir):
        all_files=sorted(f for f in glob.glob(os.path.join(args.dir,"*")) if os.path.isfile(f))
        unaccounted=[f for f in all_files if not f.lower().endswith((".json",".md"))
                 and not os.path.basename(f).startswith(".")]
        referenced=set()
        for h in holdings:
            s=h.get("source")
            if s: referenced.add(os.path.basename(s))
        unreferenced=[f for f in unaccounted if os.path.basename(f) not in referenced]
        if unreferenced:
            names=", ".join(os.path.basename(f) for f in unreferenced)
            warnings.append(f"{len(unreferenced)} statement file(s) in this month's folder have NO holding "
                             f"tagging them as a source — likely never made it into --accounts: {names}")
        no_source=[h for h in holdings if not h.get("source")]
        if no_source:
            syms=", ".join(f'{h["sym"]} ({h["account"]})' for h in no_source[:10])
            more=f" (+{len(no_source)-10} more)" if len(no_source)>10 else ""
            warnings.append(f"{len(no_source)} holding(s) have no source tag at all — can't be "
                             f"cross-checked against the folder: {syms}{more}")

    bucket_issues=validate_buckets(holdings)
    if bucket_issues:
        warnings.extend(bucket_issues)
        print("BUCKET VALIDATION WARNINGS:",file=sys.stderr)
        for w in bucket_issues: print("  -",w,file=sys.stderr)

    # Compute headline aggregates ONCE — feeds both this month's metrics.json
    # and the trend/momentum panel, so the two can never disagree with
    # each other the way two separate ad-hoc computations eventually would.
    agg=compute_aggregates(holdings)
    dashboards_dir=os.path.dirname(os.path.abspath(args.metrics)) if args.metrics else \
                   (os.path.dirname(os.path.abspath(args.out)) if args.out else None)
    project_root=os.path.dirname(dashboards_dir) if dashboards_dir else None
    history=load_trend_history(dashboards_dir, exclude_month=month_key)
    trend=build_trend(history, month_key, agg, value_notes)
    decision_log_path=os.path.join(project_root,"decision-log.json") if project_root else None
    decision_log=load_decision_log(decision_log_path, holdings, CONTRIBUTIONS)

    html=render_html(holdings,asof,args.note or "from statement snapshots",warnings,value_notes,
                      trend,decision_log)

    ok,msg=verify_js_syntax(html)
    if not ok:
        broken=args.out+".broken"
        open(broken,"w",encoding="utf-8").write(html)
        print(f"ERROR: {msg}",file=sys.stderr)
        print(f"Nothing written to {args.out} — broken output saved to {broken} for inspection.",file=sys.stderr)
        sys.exit(3)
    print(msg)
    if msg.startswith("SKIPPED"): warnings.append(msg)

    open(args.out,"w",encoding="utf-8").write(html)

    total=agg["total"]; acc=agg["accounts"]
    metrics={"total":agg["total"],"accounts":agg["accounts"],
             "tech_pct":agg["tech_pct"],"intl_eq_pct":agg["intl_eq_pct"],"bonds_pct":agg["bonds_pct"],
             "largest_stock_sym":agg["largest_stock_sym"],"largest_stock_pct":agg["largest_stock_pct"],
             "warnings":warnings,"valueNotes":value_notes}
    if args.metrics: json.dump(metrics,open(args.metrics,"w"),indent=2)
    print(f"Accounts ({len(acc)}):")
    for a,v in sorted(acc.items(),key=lambda x:-x[1]): print(f"  {a:32s} ${v:>12,.2f}")
    print(f"TOTAL ${total:,.2f} | Tech {metrics['tech_pct']}% | Intl {metrics['intl_eq_pct']}% eq | Bonds {metrics['bonds_pct']}%")
    if trend["caveats"]:
        print("TREND CAVEATS:"); [print("  -",c) for c in trend["caveats"]]
    if warnings:
        print("NOTES:"); [print("  -",w) for w in warnings]
    if value_notes:
        print("VALUE MARKS (assumption-based, not statement-confirmed):"); [print("  -",n) for n in value_notes]
    print(f"Wrote {args.out}")

if __name__=="__main__":
    main()
