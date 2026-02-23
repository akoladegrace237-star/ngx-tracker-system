"""
generate_html.py
Fetches NGX equities data and writes a self-contained index.html
suitable for GitHub Pages hosting.

Usage:
    python generate_html.py          # fetch live data → index.html
    python generate_html.py --cached # use latest saved snapshot (no browser)
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from analyzer import (
    generate_recommendations,
    get_top_gainers,
    get_top_losers,
    load_snapshots,
    save_snapshot,
    score_portfolio_stock,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DOCS_DIR = Path(".")
OUTPUT = DOCS_DIR / "index.html"

# ── My Portfolio ────────────────────────────────────────────────────────────
# Edit qty, buy_price, and stop_loss_pct for each stock you own.
# stop_loss_pct = how many % below your buy price triggers a SELL alert
PORTFOLIO_CONFIG = {
    "AFRIPRUD":  {"qty": 13200,  "buy_price": 15.00, "stop_loss_pct": 10},
    "UNIVINSURE":{"qty": 542000, "buy_price": 1.10,  "stop_loss_pct": 8 },
    "CUTIX":     {"qty": 185000, "buy_price": 2.60,  "stop_loss_pct": 10},
    "SOVRENINS": {"qty": 200000, "buy_price": 1.00,  "stop_loss_pct": 12},
}

PORTFOLIO_STOCKS = list(PORTFOLIO_CONFIG.keys())


# ── Data helpers ─────────────────────────────────────────────────────────────

def to_records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records"))


def find_portfolio_stocks(df: pd.DataFrame, names: list) -> tuple:
    """Return (matched_df, missing_names) using case-insensitive partial matching."""
    matched_rows, missing = [], []
    for name in names:
        mask = df["Company"].str.upper().str.contains(name.strip().upper(), na=False)
        hits = df[mask]
        if not hits.empty:
            matched_rows.append(hits.iloc[0])
        else:
            missing.append(name)
    matched_df = pd.DataFrame(matched_rows) if matched_rows else pd.DataFrame()
    return matched_df, missing


def _get_config_for(company: str) -> dict:
    """Find the PORTFOLIO_CONFIG entry that matches a company name (partial, case-insensitive)."""
    for key, cfg in PORTFOLIO_CONFIG.items():
        if company.upper().startswith(key.upper()):
            return cfg
    return {}


def load_data(use_cache: bool) -> pd.DataFrame:
    if use_cache:
        snaps = load_snapshots(last_n=1)
        if snaps:
            logger.info("Using cached snapshot.")
            return snaps[-1]
        logger.warning("No cached snapshot found — fetching live data.")

    from scraper import get_equities_data
    df = get_equities_data()
    if not df.empty:
        save_snapshot(df)
    return df


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/>
<title>NGX Equities Tracker</title>
<link rel="icon" href="https://ngxgroup.com/wp-content/uploads/2019/11/Nigerian-Exchange-Group-Logo-1.png"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{{
    --green:#1a6b3c; --green-light:#e8f5ee; --red:#c0392b; --red-light:#fdf2f2;
    --gold:#f39c12; --gold-light:#fef9ec; --bg:#f0f2f5; --card:#fff;
    --text:#1a1a2e; --muted:#6c757d; --border:#e8eaed;
    --radius:14px; --shadow:0 2px 16px rgba(0,0,0,.07);
    --header-h:60px; --nav-h:56px;
  }}
  *{{box-sizing:border-box; margin:0; padding:0;}}
  html{{scroll-behavior:smooth;}}
  body{{
    font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
    background:var(--bg); color:var(--text);
    padding-top:var(--header-h);
    padding-bottom:calc(var(--nav-h) + env(safe-area-inset-bottom, 0px));
  }}

  /* ── Sticky header ── */
  .top-bar{{
    position:fixed; top:0; left:0; right:0; z-index:100;
    height:var(--header-h);
    background:linear-gradient(135deg,#1a3a2a 0%,#1a6b3c 100%);
    color:#fff; display:flex; align-items:center;
    padding:0 16px; gap:10px;
    box-shadow:0 2px 12px rgba(0,0,0,.25);
  }}
  .top-bar img{{height:30px; flex-shrink:0;}}
  .top-bar-text{{flex:1; min-width:0;}}
  .top-bar-text h1{{font-size:1rem; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
  .top-bar-text p{{font-size:.7rem; opacity:.75; margin-top:1px;}}
  .top-bar-badge{{
    background:rgba(255,255,255,.18); border-radius:20px;
    padding:4px 10px; font-size:.68rem; white-space:nowrap; flex-shrink:0;
  }}

  /* ── Bottom nav ── */
  .bottom-nav{{
    position:fixed; bottom:0; left:0; right:0; z-index:100;
    height:var(--nav-h);
    background:#fff; border-top:1px solid var(--border);
    display:flex; align-items:stretch;
    padding-bottom:env(safe-area-inset-bottom, 0px);
    box-shadow:0 -2px 12px rgba(0,0,0,.08);
  }}
  .bottom-nav a{{
    flex:1; display:flex; flex-direction:column; align-items:center;
    justify-content:center; text-decoration:none; color:var(--muted);
    font-size:.62rem; font-weight:600; letter-spacing:.3px; gap:3px;
    transition:color .15s;
    -webkit-tap-highlight-color:transparent;
  }}
  .bottom-nav a:active{{color:var(--green); background:var(--green-light);}}
  .bottom-nav a span.icon{{font-size:1.25rem; line-height:1;}}

  /* ── Layout ── */
  .container{{max-width:1100px; margin:0 auto; padding:12px 12px 0;}}

  /* ── Section title ── */
  .section-title{{
    font-size:1rem; font-weight:700; color:var(--text);
    margin:20px 0 10px; padding:10px 12px;
    border-left:4px solid var(--green);
    background:var(--card); border-radius:0 var(--radius) var(--radius) 0;
    box-shadow:var(--shadow);
  }}

  /* ── KPI row ── */
  .kpi-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:4px;}}
  @media(min-width:600px){{.kpi-grid{{grid-template-columns:repeat(6,1fr);}}}}
  .kpi{{
    background:var(--card); border-radius:var(--radius); padding:12px 6px;
    text-align:center; box-shadow:var(--shadow);
  }}
  .kpi .val{{font-size:1.3rem; font-weight:800; line-height:1;}}
  .kpi .lbl{{font-size:.62rem; color:var(--muted); margin-top:4px;
    text-transform:uppercase; letter-spacing:.4px; line-height:1.2;}}
  .kpi.green .val{{color:var(--green);}}
  .kpi.red   .val{{color:var(--red);}}
  .kpi.gold  .val{{color:var(--gold);}}

  /* -- Tooltip -- */
  .kpi[data-tip]{{position:relative; cursor:help;}}
  .kpi[data-tip]::after{{
    content:attr(data-tip);
    position:absolute; bottom:calc(100% + 7px); left:50%; transform:translateX(-50%);
    background:rgba(30,30,30,.92); color:#fff; font-size:.66rem; font-weight:400;
    padding:7px 10px; border-radius:7px; white-space:normal; max-width:170px;
    text-align:center; line-height:1.45; z-index:100; pointer-events:none;
    opacity:0; transition:opacity .18s; box-shadow:0 2px 10px rgba(0,0,0,.25);
    letter-spacing:0; text-transform:none;
  }}
  .kpi[data-tip]:hover::after,
  .kpi[data-tip].tip-open::after{{opacity:1;}}

  /* ── Two-column grid ── */
  .two-col{{display:grid; grid-template-columns:1fr; gap:12px;}}
  @media(min-width:768px){{.two-col{{grid-template-columns:1fr 1fr;}}}}

  /* ── Card ── */
  .card{{background:var(--card); border-radius:var(--radius); box-shadow:var(--shadow); overflow:hidden;}}
  .card-header{{
    padding:12px 14px; font-weight:700; font-size:.9rem;
    display:flex; align-items:center; gap:8px;
  }}
  .card-header.green{{background:var(--green-light); color:var(--green);}}
  .card-header.red  {{background:var(--red-light);   color:var(--red);}}
  .card-body{{padding:10px 12px;}}
  canvas{{max-height:200px; width:100% !important;}}

  /* ── Scrollable table wrapper ── */
  .table-wrap{{overflow-x:auto; -webkit-overflow-scrolling:touch; margin-top:10px;}}
  table{{width:100%; border-collapse:collapse; font-size:.8rem; min-width:300px;}}
  th{{
    background:#f1f3f5; color:var(--muted); font-weight:600; white-space:nowrap;
    text-align:right; padding:8px 10px; font-size:.68rem; text-transform:uppercase;
    position:sticky; top:0;
  }}
  th:first-child{{text-align:left;}}
  td{{padding:8px 10px; border-bottom:1px solid #f0f0f0; text-align:right; white-space:nowrap;}}
  td:first-child{{text-align:left; font-weight:700; max-width:120px; overflow:hidden; text-overflow:ellipsis;}}
  tr:last-child td{{border-bottom:none;}}
  tr:active td{{background:#f8f9fa;}}
  .up {{color:var(--green); font-weight:700;}}
  .dn {{color:var(--red);   font-weight:700;}}
  .neu{{color:var(--muted);}}

  /* ── Hide less important table cols on small screens ── */
  @media(max-width:480px){{
    .hide-mobile{{display:none;}}
  }}

  /* -- Collapsible card -- */
  .card-header{{cursor:pointer; user-select:none; -webkit-tap-highlight-color:transparent;}}
  .card-header .arrow{{margin-left:auto; font-size:.85rem; transition:transform .25s; display:inline-block;}}
  .card-body.collapsed{{display:none;}}

  /* ── Portfolio cards ── */
  .port-grid{{display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:8px;}}
  @media(min-width:540px){{.port-grid{{grid-template-columns:repeat(3,1fr);}}}}
  @media(min-width:900px){{.port-grid{{grid-template-columns:repeat(4,1fr);}}}}
  .port-card{{
    background:var(--card); border-radius:var(--radius); box-shadow:var(--shadow);
    padding:14px 10px; text-align:center; border-top:4px solid var(--green);
  }}
  .port-sym  {{font-size:.9rem; font-weight:800; margin-bottom:2px; word-break:break-all;}}
  .port-price{{font-size:1.4rem; font-weight:800; margin:5px 0;}}
  .port-chg  {{font-size:.85rem; font-weight:700; margin-bottom:8px;}}
  .port-row  {{font-size:.7rem; color:var(--muted); margin:3px 0; line-height:1.3;}}
  .port-row b{{color:var(--text);}}
  .port-signal{{
    display:inline-block; margin-top:8px; padding:5px 12px;
    border-radius:20px; font-size:.72rem; font-weight:700; color:#fff;
  }}
  .port-signal.sell    {{background:#c0392b;}}
  .port-signal.consider{{background:#e67e22;}}
  .port-signal.watch   {{background:#f39c12; color:#333;}}
  .port-signal.hold    {{background:#7f8c8d;}}
  .port-signal.keep    {{background:#1a6b3c;}}
  .port-reason{{font-size:.65rem; color:var(--muted); margin-top:5px; line-height:1.4; font-style:italic;}}

  /* ── Stop-loss alert banner ── */
  .stop-loss-alert{{
    background:#fdf2f2; border:1px solid #c0392b; border-radius:8px;
    padding:6px 10px; margin-top:8px; font-size:.68rem;
    color:#c0392b; font-weight:700;
  }}
  .stop-loss-warn{{
    background:#fef9ec; border:1px solid #f39c12; border-radius:8px;
    padding:6px 10px; margin-top:8px; font-size:.68rem;
    color:#e67e22; font-weight:700;
  }}

  /* ── Rec cards ── */
  .rec-grid{{display:grid; grid-template-columns:1fr 1fr; gap:10px;}}
  @media(min-width:600px){{.rec-grid{{grid-template-columns:repeat(3,1fr);}}}}
  @media(min-width:900px){{.rec-grid{{grid-template-columns:repeat(5,1fr);}}}}
  .rec-card{{
    background:var(--card); border-radius:var(--radius);
    box-shadow:var(--shadow); padding:14px 10px; text-align:center;
    border-top:4px solid var(--green);
  }}
  .rec-card.watch{{border-top-color:var(--gold);}}
  .rec-sym  {{font-size:.9rem; font-weight:800; margin-bottom:4px; word-break:break-all;}}
  .rec-price{{font-size:1.3rem; font-weight:800; color:var(--green); margin:4px 0;}}
  .rec-price.dn{{color:var(--red);}}
  .rec-pct  {{font-size:.85rem; margin-bottom:6px;}}
  .rec-row  {{font-size:.7rem; color:var(--muted); margin:3px 0;}}
  .rec-row b{{color:var(--text);}}
  .signal{{
    display:inline-block; margin-top:8px; padding:4px 12px;
    border-radius:20px; font-size:.72rem; font-weight:700;
    background:var(--green); color:#fff;
  }}
  .signal.watch{{background:var(--gold); color:#333;}}

  /* ── Score guide ── */
  .score-guide{{
    font-size:.72rem; color:var(--muted); margin-top:12px;
    background:var(--card); border-radius:var(--radius);
    padding:10px 14px; box-shadow:var(--shadow); line-height:1.8;
  }}

  /* ── All Stocks table ── */
  .all-stocks-toolbar{{
    display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; align-items:center;
  }}
  .all-stocks-toolbar input{{
    flex:1; min-width:160px; padding:8px 12px; border:1px solid var(--border);
    border-radius:8px; font-size:.82rem; outline:none;
  }}
  .all-stocks-toolbar select{{
    padding:8px 10px; border:1px solid var(--border);
    border-radius:8px; font-size:.82rem; outline:none; background:#fff;
  }}
  .all-stocks-toolbar .stock-count{{
    font-size:.75rem; color:var(--muted); white-space:nowrap;
  }}
  #allStocksTable th{{cursor:pointer; user-select:none;}}
  #allStocksTable th:hover{{background:#e8eaed;}}
  .rank-badge{{
    display:inline-block; width:22px; height:22px; border-radius:50%;
    background:var(--green); color:#fff; font-size:.65rem;
    font-weight:800; line-height:22px; text-align:center;
  }}
  .rank-badge.top3{{background:var(--gold); color:#333;}}
  .rank-badge.bot3{{background:var(--red);}}

  /* ── Footer ── */
  footer{{
    text-align:center; color:var(--muted); font-size:.72rem;
    margin-top:24px; padding:16px;
  }}
  footer a{{color:var(--green); text-decoration:none;}}
</style>
</head>
<body>

<!-- Sticky top bar -->
<div class="top-bar">
  <img src="https://ngxgroup.com/wp-content/uploads/2019/11/Nigerian-Exchange-Group-Logo-1.png" alt="NGX"/>
  <div class="top-bar-text">
    <h1>NGX Equities Tracker</h1>
    <p>Nigerian Exchange — Live Intelligence</p>
  </div>
  <div class="top-bar-badge">&#128336; {updated}</div>
</div>

<div class="container">

  <!-- KPIs -->
  <div id="overview" style="scroll-margin-top:70px;">
    <div class="section-title">&#128200; Market Overview</div>
    <div class="kpi-grid">
      <div class="kpi" data-tip="Total NGX equities tracked in today's session"><div class="val">{total}</div><div class="lbl">Total<br/>Stocks</div></div>
      <div class="kpi green" data-tip="Stocks that closed HIGHER than their previous close"><div class="val">{advancing}</div><div class="lbl">Advancing<br/>&#9650;</div></div>
      <div class="kpi red"   data-tip="Stocks that closed LOWER than their previous close"><div class="val">{declining}</div><div class="lbl">Declining<br/>&#9660;</div></div>
      <div class="kpi"       data-tip="Stocks whose price did not move from the previous close"><div class="val">{unchanged}</div><div class="lbl">Unchanged<br/>&#8212;</div></div>
      <div class="kpi {avg_color}" data-tip="Average % price change across all stocks today"><div class="val">{avg_chg}</div><div class="lbl">Avg<br/>Change</div></div>
      <div class="kpi gold"  data-tip="Hourly snapshots used for trend signals (~1 per trading hour, max 168 = 7 days)"><div class="val">{snapshots}</div><div class="lbl">History<br/>Snaps</div></div>
    </div>
  </div>

  <!-- My Portfolio -->
  <div id="portfolio" style="scroll-margin-top:70px;">
    <div class="section-title">&#128202; My Portfolio</div>
    <div class="port-grid" id="portGrid"></div>
  </div>

  <!-- Gainers & Losers -->
  <div id="markets" style="scroll-margin-top:70px;">
    <div class="section-title">&#128200; Top Movers</div>
    <div class="two-col">

      <div class="card">
        <div class="card-header green" onclick="toggleCard('gainBody_wrap','gainArrow')">&#129001; Top {top_n} Gainers <span class="arrow" id="gainArrow">&#9660;</span></div>
        <div class="card-body" id="gainBody_wrap">
          <canvas id="gainChart"></canvas>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Symbol</th>
                <th class="hide-mobile">Prev &#8358;</th>
                <th>Close &#8358;</th>
                <th class="hide-mobile">Chg</th>
                <th>% Chg</th>
              </tr></thead>
              <tbody id="gainBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header red" onclick="toggleCard('lossBody_wrap','lossArrow')">&#128308; Top {top_n} Losers <span class="arrow" id="lossArrow">&#9660;</span></div>
        <div class="card-body" id="lossBody_wrap">
          <canvas id="lossChart"></canvas>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Symbol</th>
                <th class="hide-mobile">Prev &#8358;</th>
                <th>Close &#8358;</th>
                <th class="hide-mobile">Chg</th>
                <th>% Chg</th>
              </tr></thead>
              <tbody id="lossBody"></tbody>
            </table>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- Recommendations -->
  <div id="recs" style="scroll-margin-top:70px;">
    <div class="section-title">&#128161; Buy Recommendations</div>
    <p style="font-size:.75rem;color:var(--muted);margin-bottom:10px;padding:0 4px;">{rec_note}</p>
    <div class="rec-grid" id="recGrid"></div>
    <div class="score-guide">
      <b>Signal guide:</b> STRONG BUY &#8805;30pts &nbsp;&#183;&nbsp; BUY &#8805;15pts &nbsp;&#183;&nbsp; WATCH &#8805;5pts<br/>
      <b>Factors:</b> Momentum (40%) &middot; Consistency (20%) &middot; Volume (10%) &middot; Recent trend (30%); &minus;15pts for 3 down-sessions in a row
    </div>
  </div>

  <!-- All Stocks -->
  <div id="allstocks" style="scroll-margin-top:70px;">
    <div class="section-title">&#128196; All NGX Stocks — Ranked by Performance</div>
    <div class="all-stocks-toolbar">
      <input type="text" id="stockSearch" placeholder="&#128269; Search company name..." oninput="filterStocks()"/>
      <select id="sortCol" onchange="sortStocks()">
        <option value="rank">Rank (% Change)</option>
        <option value="name">Name A–Z</option>
        <option value="close">Close Price</option>
        <option value="volume">Volume</option>
      </select>
      <span class="stock-count" id="stockCount"></span>
    </div>
    <div class="card">
      <div class="table-wrap">
        <table id="allStocksTable">
          <thead><tr>
            <th onclick="sortByCol('rank')">#</th>
            <th onclick="sortByCol('name')" style="text-align:left">Company</th>
            <th onclick="sortByCol('close')">Close &#8358;</th>
            <th onclick="sortByCol('pct')">% Chg</th>
            <th onclick="sortByCol('change')" class="hide-mobile">Chg &#8358;</th>
            <th onclick="sortByCol('high')" class="hide-mobile">High</th>
            <th onclick="sortByCol('low')" class="hide-mobile">Low</th>
            <th onclick="sortByCol('volume')">Volume</th>
          </tr></thead>
          <tbody id="allStocksBody"></tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<footer>
  <p>Data from <a href="https://ngxgroup.com/exchange/data/equities-price-list/" target="_blank">ngxgroup.com</a> &middot; Prices delayed ~30 min</p>
  <p style="margin-top:4px;">Auto-refreshed hourly via GitHub Actions</p>
</footer>

<!-- Bottom nav -->
<nav class="bottom-nav">
  <a href="#overview"><span class="icon">&#128200;</span>Overview</a>
  <a href="#portfolio"><span class="icon">&#128202;</span>Portfolio</a>
  <a href="#markets"><span class="icon">&#128308;</span>Movers</a>
  <a href="#recs"><span class="icon">&#128161;</span>Picks</a>
  <a href="#allstocks"><span class="icon">&#128196;</span>All</a>
</nav>

<script>
function toggleCard(bodyId, arrowId) {{
  const body  = document.getElementById(bodyId);
  const arrow = document.getElementById(arrowId);
  const isNowCollapsed = body.classList.toggle('collapsed');
  arrow.style.transform = isNowCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)';
}}

const GAINERS     = {gainers_json};
const LOSERS      = {losers_json};
const RECS        = {recs_json};
const PORTFOLIO   = {portfolio_json};
const PORT_MISS   = {missing_json};
const PORT_SIGNALS = {signals_json};
const ALL_STOCKS  = {all_stocks_json};

// ── Gainers table & chart ──
const gainBody = document.getElementById('gainBody');
GAINERS.forEach((r,i) => {{
  gainBody.innerHTML += `<tr>
    <td>${{r.Company}}</td>
    <td class="hide-mobile">${{r.Prev_Close?.toFixed(2) ?? '-'}}</td>
    <td>${{r.Close?.toFixed(2) ?? '-'}}</td>
    <td class="up hide-mobile">+${{r.Change?.toFixed(2) ?? '0'}}</td>
    <td class="up">+${{r.Pct_Change?.toFixed(2) ?? '0'}}%</td>
  </tr>`;
}});

new Chart(document.getElementById('gainChart'), {{
  type:'bar',
  data:{{
    labels: GAINERS.map(r=>r.Company),
    datasets:[{{ data: GAINERS.map(r=>r.Pct_Change), backgroundColor:'rgba(26,107,60,0.75)', borderRadius:5 }}]
  }},
  options:{{
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{title:{{display:true,text:'% Change'}},ticks:{{font:{{size:10}}}}}},
      x:{{ticks:{{maxRotation:45,font:{{size:9}}}}}}
    }},
    responsive:true, maintainAspectRatio:true,
  }}
}});

// ── Losers table & chart ──
const lossBody = document.getElementById('lossBody');
LOSERS.forEach(r => {{
  lossBody.innerHTML += `<tr>
    <td>${{r.Company}}</td>
    <td class="hide-mobile">${{r.Prev_Close?.toFixed(2) ?? '-'}}</td>
    <td>${{r.Close?.toFixed(2) ?? '-'}}</td>
    <td class="dn hide-mobile">${{r.Change?.toFixed(2) ?? '0'}}</td>
    <td class="dn">${{r.Pct_Change?.toFixed(2) ?? '0'}}%</td>
  </tr>`;
}});

new Chart(document.getElementById('lossChart'), {{
  type:'bar',
  data:{{
    labels: LOSERS.map(r=>r.Company),
    datasets:[{{ data: LOSERS.map(r=>r.Pct_Change), backgroundColor:'rgba(192,57,43,0.75)', borderRadius:5 }}]
  }},
  options:{{
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{title:{{display:true,text:'% Change'}},ticks:{{font:{{size:10}}}}}},
      x:{{ticks:{{maxRotation:45,font:{{size:9}}}}}}
    }},
    responsive:true, maintainAspectRatio:true,
  }}
}});

// ── My Portfolio cards ──
const portGrid = document.getElementById('portGrid');
if (PORTFOLIO.length === 0 && PORT_MISS.length > 0) {{
  portGrid.innerHTML = "<p style='color:var(--muted);font-size:.85rem;'>No portfolio stocks found in today&apos;s data.</p>";
}} else {{
  PORTFOLIO.forEach(r => {{
    const pct       = r.Pct_Change ?? 0;
    const sign      = pct >= 0 ? '+' : '';
    const cls       = pct > 0 ? 'up' : pct < 0 ? 'dn' : 'neu';
    const borderCol = pct > 0 ? 'var(--green)' : pct < 0 ? 'var(--red)' : 'var(--muted)';
    const sig       = PORT_SIGNALS[r.Company] || {{}};
    const sigText   = sig.signal || 'HOLD';
    const sigReason = sig.reason || '';
    const sigCls    = sigText === 'SELL' ? 'sell'
                    : sigText === 'CONSIDER SELLING' ? 'consider'
                    : sigText === 'WATCH CLOSELY' ? 'watch'
                    : sigText === 'KEEP' ? 'keep' : 'hold';
    const sessions  = sig.sessions ? sig.sessions + ' sessions' : 'today only';
    const netChg    = sig.net_change_pct != null
                    ? (sig.net_change_pct >= 0 ? '+' : '') + sig.net_change_pct.toFixed(2) + '%'
                    : '\u2014';

    // ── P&L block ──
    const qty       = r._qty       || 0;
    const buyPrice  = r._buy_price  || 0;
    const stopLossPct = r._stop_loss_pct || 10;
    let plHtml = '';
    let stopHtml = '';

    if (qty > 0 && buyPrice > 0 && r.Close) {{
      const cost   = qty * buyPrice;
      const curVal = qty * r.Close;
      const pl     = curVal - cost;
      const plPct  = (pl / cost * 100);
      const plCls  = pl >= 0 ? 'up' : 'dn';
      const plSign = pl >= 0 ? '+' : '';
      const fmt2   = (n) => n.toLocaleString(undefined, {{minimumFractionDigits:2, maximumFractionDigits:2}});

      plHtml = `
        <div class="port-row" style="border-top:1px solid #f0f0f0;margin-top:6px;padding-top:6px;">
          Shares: <b>${{qty.toLocaleString()}}</b>
        </div>
        <div class="port-row">Buy price: <b>&#8358;${{buyPrice.toFixed(2)}}</b></div>
        <div class="port-row">Cost basis: <b>&#8358;${{fmt2(cost)}}</b></div>
        <div class="port-row">Market value: <b>&#8358;${{fmt2(curVal)}}</b></div>
        <div class="port-row ${{plCls}}">P&amp;L: <b>${{plSign}}&#8358;${{fmt2(Math.abs(pl))}} (${{plSign}}${{plPct.toFixed(1)}}%)</b></div>`;

      // ── Stop-loss alert ──
      const lossFromBuy = ((r.Close - buyPrice) / buyPrice) * 100;
      const stopLossPrice = buyPrice * (1 - stopLossPct / 100);
      if (lossFromBuy <= -stopLossPct) {{
        stopHtml = `<div class="stop-loss-alert">&#128680; STOP-LOSS BREACHED! Down ${{Math.abs(lossFromBuy).toFixed(1)}}% from buy price. Consider selling.</div>`;
      }} else if (lossFromBuy <= -(stopLossPct * 0.7)) {{
        stopHtml = `<div class="stop-loss-warn">&#9888; Approaching stop-loss (${{stopLossPct}}%). Currently ${{lossFromBuy.toFixed(1)}}% from buy price. Stop at &#8358;${{stopLossPrice.toFixed(2)}}.</div>`;
      }}
    }} else if (qty > 0) {{
      plHtml = `<div class="port-row" style="border-top:1px solid #f0f0f0;margin-top:6px;padding-top:6px;">Shares held: <b>${{qty.toLocaleString()}}</b></div>`;
    }}

    portGrid.innerHTML += `
      <div class="port-card" style="border-top-color:${{borderCol}}">
        <div class="port-sym">${{r.Company}}</div>
        <div class="port-price ${{cls}}">&#8358;${{r.Close?.toFixed(2) ?? '\u2014'}}</div>
        <div class="port-chg ${{cls}}">${{sign}}${{pct.toFixed(2)}}% today</div>
        <div class="port-row">High/Low: <b>&#8358;${{r.High?.toFixed(2) ?? '\u2014'}} / &#8358;${{r.Low?.toFixed(2) ?? '\u2014'}}</b></div>
        <div class="port-row">Vol: <b>${{r.Volume ? r.Volume.toLocaleString() : '\u2014'}}</b></div>
        <div class="port-row">Trend (${{sessions}}): <b>${{netChg}}</b></div>
        ${{plHtml}}
        ${{stopHtml}}
        <div><span class="port-signal ${{sigCls}}">${{sigText}}</span></div>
        <div class="port-reason">${{sigReason}}</div>
      </div>`;
  }});
  PORT_MISS.forEach(name => {{
    portGrid.innerHTML += `
      <div class="port-card" style="border-top-color:var(--muted);opacity:.5">
        <div class="port-sym">${{name}}</div>
        <div style="font-size:.75rem;color:var(--muted);margin-top:10px;">Not traded today</div>
      </div>`;
  }});
}}

// ── Recommendation cards ──
const recGrid = document.getElementById('recGrid');
RECS.forEach(r => {{
  const signal   = r.Recommendation || 'WATCH';
  const isBuy    = signal.includes('BUY');
  const pct      = r.Pct_Change ?? 0;
  const mom      = r['momentum_%'] ?? pct;
  const score    = r.Score?.toFixed(1) ?? '\u2014';
  const vol      = r.Volume ? r.Volume.toLocaleString() : '\u2014';
  const sign     = pct >= 0 ? '+' : '';
  const priceClass = pct >= 0 ? '' : 'dn';
  const watchClass = isBuy ? '' : 'watch';
  const sigClass   = isBuy ? '' : 'watch';
  recGrid.innerHTML += `
  <div class="rec-card ${{watchClass}}">
    <div class="rec-sym">${{r.Company}}</div>
    <div class="rec-price ${{priceClass}}">&#8358;${{r.Close?.toFixed(2) ?? '\u2014'}}</div>
    <div class="rec-pct ${{pct>=0?'up':'dn'}}">${{sign}}${{pct.toFixed(2)}}%</div>
    <div class="rec-row">Score: <b>${{score}}</b></div>
    <div class="rec-row">Mom: <b>${{mom>=0?'+':''}}${{typeof mom==='number'?mom.toFixed(1):'\u2014'}}%</b></div>
    <div class="rec-row">Vol: <b>${{vol}}</b></div>
    <div><span class="signal ${{sigClass}}">${{signal}}</span></div>
  </div>`;
}});

// Tap a KPI to show its tooltip on mobile (auto-dismisses after 3s)
document.querySelectorAll(".kpi[data-tip]").forEach(el => {{
  el.addEventListener("click", () => {{
    el.classList.toggle("tip-open");
    setTimeout(() => el.classList.remove("tip-open"), 3000);
  }});
}});

// ── All Stocks ranked table ──
let _filteredStocks = [...ALL_STOCKS];
let _sortKey = 'rank';
let _sortAsc = true;

function renderAllStocks() {{
  const tbody = document.getElementById('allStocksBody');
  const total = ALL_STOCKS.length;
  tbody.innerHTML = '';
  _filteredStocks.forEach((r, i) => {{
    const origRank = ALL_STOCKS.indexOf(r) + 1;
    const pct    = r.Pct_Change ?? 0;
    const sign   = pct >= 0 ? '+' : '';
    const cls    = pct > 0 ? 'up' : pct < 0 ? 'dn' : 'neu';
    const badgeCls = origRank <= 3 ? 'top3' : origRank > total - 3 ? 'bot3' : '';
    tbody.innerHTML += `<tr>
      <td><span class="rank-badge ${{badgeCls}}">${{origRank}}</span></td>
      <td style="text-align:left">${{r.Company}}</td>
      <td>${{r.Close?.toFixed(2) ?? '\u2014'}}</td>
      <td class="${{cls}}">${{sign}}${{pct.toFixed(2)}}%</td>
      <td class="${{cls}} hide-mobile">${{sign}}${{r.Change?.toFixed(2) ?? '0'}}</td>
      <td class="hide-mobile">${{r.High?.toFixed(2) ?? '\u2014'}}</td>
      <td class="hide-mobile">${{r.Low?.toFixed(2) ?? '\u2014'}}</td>
      <td>${{r.Volume ? r.Volume.toLocaleString() : '\u2014'}}</td>
    </tr>`;
  }});
  document.getElementById('stockCount').textContent =
    _filteredStocks.length === total
      ? total + ' stocks'
      : _filteredStocks.length + ' of ' + total + ' stocks';
}}

function filterStocks() {{
  const q = document.getElementById('stockSearch').value.trim().toUpperCase();
  _filteredStocks = q
    ? ALL_STOCKS.filter(r => r.Company.toUpperCase().includes(q))
    : [...ALL_STOCKS];
  sortStocks(false);
  renderAllStocks();
}}

function sortByCol(key) {{
  if (_sortKey === key) {{ _sortAsc = !_sortAsc; }}
  else {{ _sortKey = key; _sortAsc = key === 'rank' || key === 'name'; }}
  const keyMap = {{
    rank:   r => ALL_STOCKS.indexOf(r),
    name:   r => r.Company,
    close:  r => -(r.Close ?? 0),
    pct:    r => -(r.Pct_Change ?? 0),
    change: r => -(r.Change ?? 0),
    high:   r => -(r.High ?? 0),
    low:    r => -(r.Low ?? 0),
    volume: r => -(r.Volume ?? 0),
  }};
  const fn = keyMap[key] || keyMap['rank'];
  _filteredStocks.sort((a, b) => {{
    const av = fn(a), bv = fn(b);
    if (av < bv) return _sortAsc ? -1 : 1;
    if (av > bv) return _sortAsc ? 1 : -1;
    return 0;
  }});
  renderAllStocks();
}}

function sortStocks(doRender = true) {{
  const key = document.getElementById('sortCol')?.value || _sortKey;
  const keyMap = {{
    rank:   r => ALL_STOCKS.indexOf(r),
    name:   r => r.Company,
    close:  r => -(r.Close ?? 0),
    pct:    r => -(r.Pct_Change ?? 0),
    volume: r => -(r.Volume ?? 0),
  }};
  const fn = keyMap[key] || keyMap['rank'];
  _filteredStocks.sort((a, b) => {{
    const av = fn(a), bv = fn(b);
    return av < bv ? -1 : av > bv ? 1 : 0;
  }});
  if (doRender) renderAllStocks();
}}

// Initial render on page load
renderAllStocks();
</script>
</body>
</html>
"""


# ── Generator ─────────────────────────────────────────────────────────────────

# ── Generator ─────────────────────────────────────────────────────────────────

def generate(df: pd.DataFrame, snapshots: list, top_n: int = 10, rec_n: int = 5) -> None:
    now_str = datetime.now().strftime("%d %b %Y, %H:%M WAT")

    gainers = get_top_gainers(df, n=top_n)
    losers  = get_top_losers(df,  n=top_n)
    recs    = generate_recommendations(df, snapshots, top_n=rec_n)

    # find_portfolio_stocks always returns a DataFrame (may be empty) + list
    port_df, port_missing = find_portfolio_stocks(df, PORTFOLIO_STOCKS)

    # ── Inject qty, buy_price, stop_loss_pct from PORTFOLIO_CONFIG ──
    if not port_df.empty:
        port_df = port_df.copy()
        port_df["_qty"]           = port_df["Company"].apply(lambda c: _get_config_for(c).get("qty",           0))
        port_df["_buy_price"]     = port_df["Company"].apply(lambda c: _get_config_for(c).get("buy_price",     0))
        port_df["_stop_loss_pct"] = port_df["Company"].apply(lambda c: _get_config_for(c).get("stop_loss_pct", 10))

    # ── Compute SELL/HOLD/KEEP signals ──
    port_signals = {}                                    # ← 4 spaces indent
    for _, row in port_df.iterrows():                    # ← 4 spaces indent
        sig = score_portfolio_stock(                     # ← 8 spaces indent
            row["Company"],
            row,
            snapshots,
            buy_price     = float(row.get("_buy_price",     0)),
            stop_loss_pct = float(row.get("_stop_loss_pct", 10)),
        )
        port_signals[row["Company"]] = sig               # ← 8 spaces indent

    total     = len(df)                                  # ← 4 spaces indent
    advancing = int((df["Pct_Change"] > 0).sum())
    declining = int((df["Pct_Change"] < 0).sum())
    unchanged = int((df["Pct_Change"] == 0).sum())
    avg_chg   = df["Pct_Change"].mean()
    avg_str   = f"{avg_chg:+.2f}%"
    avg_color = "green" if avg_chg >= 0 else "red"
    rec_note  = (
        f"Trend analysis based on {len(snapshots)} hourly snapshot(s). "
        "More snapshots improve signal accuracy."
    )

    html = HTML_TEMPLATE.format(
        updated        = now_str,
        total          = total,
        advancing      = advancing,
        declining      = declining,
        unchanged      = unchanged,
        avg_chg        = avg_str,
        avg_color      = avg_color,
        snapshots      = len(snapshots),
        top_n          = top_n,
        rec_note       = rec_note,
        gainers_json   = json.dumps(to_records(gainers),   ensure_ascii=False),
        losers_json    = json.dumps(to_records(losers),    ensure_ascii=False),
        recs_json      = json.dumps(to_records(recs),      ensure_ascii=False),
        portfolio_json = json.dumps(to_records(port_df) if not port_df.empty else [], ensure_ascii=False),
        missing_json   = json.dumps(port_missing,          ensure_ascii=False),
        signals_json   = json.dumps(port_signals,          ensure_ascii=False),
        all_stocks_json = json.dumps(
            to_records(
                df.sort_values("Pct_Change", ascending=False)
                  [["Company", "Close", "Pct_Change", "Change", "Volume", "High", "Low"]]
                  .reset_index(drop=True)
            ),
            ensure_ascii=False
        ),
    )

    OUTPUT.write_text(html, encoding="utf-8")
    logger.info(f"HTML written to {OUTPUT.resolve()}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true",
                        help="Use latest saved snapshot instead of fetching live data")
    parser.add_argument("--top",    type=int, default=10, help="Top N gainers/losers")
    parser.add_argument("--rec",    type=int, default=5,  help="Number of recommendations")
    args = parser.parse_args()

    df = load_data(use_cache=args.cached)
    if df.empty:
        logger.error("No data available. Aborting.")
        sys.exit(1)

    snapshots = load_snapshots(last_n=168)  # 7 days x 24 hrs
    generate(df, snapshots, top_n=args.top, rec_n=args.rec)
    print(f"\nOK  index.html generated -- {len(df)} stocks processed.")
    print("   Push to GitHub → Pages will auto-update.\n")


if __name__ == "__main__":
    main()





