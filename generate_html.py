"""
generate_html.py
Fetches NGX equities data and writes a self-contained index.html
suitable for GitHub Pages hosting.

Usage:
    python generate_html.py          # fetch live data → docs/index.html
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

DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)
OUTPUT = DOCS_DIR / "index.html"

# ── My Portfolio ─────────────────────────────────────────────────────────────
# Add or remove tickers/company names here to personalise your watchlist.
PORTFOLIO_STOCKS = [
    "AFRIPRUD",       # African Prudential
    "UNIVINSURE",     # Universal Insurance
    "CUTIX",          # Cutix (Cables)
    "SOVRENINS",      # Sovereign Trust Insurance [MRF]
]


# ── Data helpers ──────────────────────────────────────────────────────────────

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
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>NGX Equities Tracker</title>
<link rel="icon" href="https://ngxgroup.com/wp-content/uploads/2019/11/Nigerian-Exchange-Group-Logo-1.png"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{{
    --green:#1a6b3c; --green-light:#e8f5ee; --red:#c0392b; --red-light:#fdf2f2;
    --gold:#f39c12; --bg:#f4f6f8; --card:#fff; --text:#1a1a2e; --muted:#6c757d;
    --radius:12px; --shadow:0 2px 12px rgba(0,0,0,.08);
  }}
  *{{box-sizing:border-box; margin:0; padding:0;}}
  body{{font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); padding-bottom:40px;}}

  /* ── Header ── */
  header{{background:linear-gradient(135deg,#1a3a2a 0%,#1a6b3c 100%);
    color:#fff; padding:20px 16px 16px; text-align:center;}}
  header img{{height:38px; margin-bottom:8px;}}
  header h1{{font-size:1.5rem; font-weight:700; letter-spacing:-.5px;}}
  header p{{font-size:.82rem; opacity:.8; margin-top:4px;}}
  .badge{{display:inline-block; background:rgba(255,255,255,.18);
    border-radius:20px; padding:3px 12px; font-size:.78rem; margin-top:8px;}}

  /* ── Layout ── */
  .container{{max-width:1100px; margin:0 auto; padding:16px;}}
  .section-title{{font-size:1.1rem; font-weight:700; color:var(--text);
    margin:24px 0 12px; padding-left:10px;
    border-left:4px solid var(--green);}}

  /* ── KPI row ── */
  .kpi-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:4px;}}
  @media(min-width:600px){{.kpi-grid{{grid-template-columns:repeat(6,1fr);}}}}
  .kpi{{background:var(--card); border-radius:var(--radius); padding:14px 8px;
    text-align:center; box-shadow:var(--shadow);}}
  .kpi .val{{font-size:1.4rem; font-weight:800; line-height:1;}}
  .kpi .lbl{{font-size:.7rem; color:var(--muted); margin-top:4px; text-transform:uppercase; letter-spacing:.5px;}}
  .kpi.green .val{{color:var(--green);}}
  .kpi.red   .val{{color:var(--red);}}
  .kpi.gold  .val{{color:var(--gold);}}

  /* ── Two-column grid ── */
  .two-col{{display:grid; grid-template-columns:1fr; gap:16px;}}
  @media(min-width:768px){{.two-col{{grid-template-columns:1fr 1fr;}}}}

  /* ── Card ── */
  .card{{background:var(--card); border-radius:var(--radius);
    box-shadow:var(--shadow); overflow:hidden;}}
  .card-header{{padding:12px 16px; font-weight:700; font-size:.95rem;
    display:flex; align-items:center; gap:8px;}}
  .card-header.green{{background:var(--green-light); color:var(--green);}}
  .card-header.red  {{background:var(--red-light);   color:var(--red);}}
  .card-body{{padding:12px 16px;}}
  canvas{{max-height:220px;}}

  /* ── Table ── */
  table{{width:100%; border-collapse:collapse; font-size:.82rem;}}
  th{{background:#f1f3f5; color:var(--muted); font-weight:600;
    text-align:right; padding:7px 10px; font-size:.72rem; text-transform:uppercase;}}
  th:first-child{{text-align:left;}}
  td{{padding:7px 10px; border-bottom:1px solid #f0f0f0; text-align:right;}}
  td:first-child{{text-align:left; font-weight:600;}}
  tr:last-child td{{border-bottom:none;}}
  .up  {{color:var(--green); font-weight:700;}}
  .dn  {{color:var(--red);   font-weight:700;}}
  .neu {{color:var(--muted);}}

  /* ── Rec cards ── */
  .rec-grid{{display:grid; grid-template-columns:repeat(2,1fr); gap:12px;}}
  @media(min-width:600px){{.rec-grid{{grid-template-columns:repeat(3,1fr);}}}}
  @media(min-width:900px){{.rec-grid{{grid-template-columns:repeat(5,1fr);}}}}
  .rec-card{{background:var(--card); border-radius:var(--radius);
    box-shadow:var(--shadow); padding:16px 12px; text-align:center;
    border-top:4px solid var(--green);}}
  .rec-card.watch{{border-top-color:var(--gold);}}
  .rec-sym  {{font-size:1rem; font-weight:800; margin-bottom:4px;}}
  .rec-price{{font-size:1.5rem; font-weight:800; color:var(--green); margin:4px 0;}}
  .rec-price.dn{{color:var(--red);}}
  .rec-pct  {{font-size:.9rem; margin-bottom:8px;}}
  .rec-row  {{font-size:.75rem; color:var(--muted); margin:3px 0;}}
  .rec-row b{{color:var(--text);}}
  .signal{{display:inline-block; margin-top:10px; padding:4px 14px;
    border-radius:20px; font-size:.75rem; font-weight:700;
    background:var(--green); color:#fff;}}
  .signal.watch{{background:var(--gold);}}

  /* ── Portfolio cards ── */
  .port-grid{{display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin-bottom:8px;}}
  @media(min-width:600px){{.port-grid{{grid-template-columns:repeat(3,1fr);}}}}
  @media(min-width:900px){{.port-grid{{grid-template-columns:repeat(4,1fr);}}}}
  .port-card{{background:var(--card); border-radius:var(--radius); box-shadow:var(--shadow);
    padding:16px 12px; text-align:center; border-top:4px solid var(--green);}}
  .port-sym  {{font-size:1rem; font-weight:800; margin-bottom:4px;}}
  .port-price{{font-size:1.5rem; font-weight:800; margin:6px 0;}}
  .port-chg  {{font-size:1rem; font-weight:700; margin-bottom:10px;}}
  .port-row  {{font-size:.75rem; color:var(--muted); margin:3px 0;}}
  .port-row b{{color:var(--text);}}  .port-signal{{display:inline-block; margin-top:10px; padding:5px 14px;
    border-radius:20px; font-size:.78rem; font-weight:700; color:#fff;}}
  .port-signal.sell{{background:#c0392b;}}
  .port-signal.consider{{background:#e67e22;}}
  .port-signal.watch{{background:#f39c12; color:#333;}}
  .port-signal.hold{{background:#7f8c8d;}}
  .port-signal.keep{{background:#1a6b3c;}}
  .port-reason{{font-size:.7rem; color:var(--muted); margin-top:6px; line-height:1.4; font-style:italic;}}
  /* ── Footer ── */
  footer{{text-align:center; color:var(--muted); font-size:.75rem; margin-top:32px;}}
  footer a{{color:var(--green); text-decoration:none;}}
  .update-btn{{display:inline-block; margin-top:10px;
    background:var(--green); color:#fff; border:none; border-radius:20px;
    padding:8px 22px; font-size:.85rem; cursor:pointer; text-decoration:none;}}
</style>
</head>
<body>

<header>
  <img src="https://ngxgroup.com/wp-content/uploads/2019/11/Nigerian-Exchange-Group-Logo-1.png" alt="NGX"/>
  <h1>NGX Equities Tracker</h1>
  <p>Nigerian Exchange — Live Market Intelligence</p>
  <div class="badge">🕐 Updated: {updated}</div>
</header>

<div class="container">

  <!-- KPIs -->
  <div class="section-title">Market Overview</div>
  <div class="kpi-grid">
    <div class="kpi"><div class="val">{total}</div><div class="lbl">Total Stocks</div></div>
    <div class="kpi green"><div class="val">{advancing}</div><div class="lbl">Advancing ▲</div></div>
    <div class="kpi red">  <div class="val">{declining}</div><div class="lbl">Declining ▼</div></div>
    <div class="kpi">      <div class="val">{unchanged}</div><div class="lbl">Unchanged —</div></div>
    <div class="kpi {avg_color}"><div class="val">{avg_chg}</div><div class="lbl">Avg Change</div></div>
    <div class="kpi gold"> <div class="val">{snapshots}</div><div class="lbl">Snapshots</div></div>
  </div>

  <!-- Gainers & Losers -->
  <div class="two-col" style="margin-top:24px;">

    <!-- Gainers -->
    <div class="card">
      <div class="card-header green">🟢 Top {top_n} Gainers</div>
      <div class="card-body">
        <canvas id="gainChart"></canvas>
        <table style="margin-top:12px;">
          <thead><tr>
            <th>Symbol</th><th>Prev ₦</th><th>Close ₦</th><th>Change</th><th>% Chg</th>
          </tr></thead>
          <tbody id="gainBody"></tbody>
        </table>
      </div>
    </div>

    <!-- Losers -->
    <div class="card">
      <div class="card-header red">🔴 Top {top_n} Losers</div>
      <div class="card-body">
        <canvas id="lossChart"></canvas>
        <table style="margin-top:12px;">
          <thead><tr>
            <th>Symbol</th><th>Prev ₦</th><th>Close ₦</th><th>Change</th><th>% Chg</th>
          </tr></thead>
          <tbody id="lossBody"></tbody>
        </table>
      </div>
    </div>

  </div>

  <!-- My Portfolio -->
  <div class="section-title">📊 My Portfolio</div>
  <div class="port-grid" id="portGrid"></div>

  <!-- Recommendations -->
  <div class="section-title">💡 Buy Recommendations</div>
  <p style="font-size:.8rem;color:var(--muted);margin-bottom:12px;">{rec_note}</p>
  <div class="rec-grid" id="recGrid"></div>

  <div style="font-size:.75rem;color:var(--muted);margin-top:14px;line-height:1.7;">
    <b>Score guide:</b> STRONG BUY ≥30 pts &nbsp;|&nbsp; BUY ≥15 pts &nbsp;|&nbsp; WATCH ≥5 pts<br/>
    <b>Factors:</b> Price momentum (40%) · Trend consistency (20%) · Volume confirmation (10%) · Recent momentum (30%); −15 pts for 3 consecutive down-sessions
  </div>

</div>

<footer>
  <p>Data sourced from <a href="https://ngxgroup.com/exchange/data/equities-price-list/" target="_blank">ngxgroup.com</a> · Prices delayed ~30 min</p>
  <p style="margin-top:4px;">Auto-refreshed hourly via GitHub Actions</p>
</footer>

<script>
const GAINERS    = {gainers_json};
const LOSERS     = {losers_json};
const RECS       = {recs_json};
const PORTFOLIO  = {portfolio_json};
const PORT_MISS    = {missing_json};
const PORT_SIGNALS = {signals_json};

// ── Gainers table & chart ──
const gainBody = document.getElementById('gainBody');
GAINERS.forEach((r,i) => {{
  gainBody.innerHTML += `<tr>
    <td>${{r.Company}}</td>
    <td>${{r.Prev_Close?.toFixed(2) ?? '-'}}</td>
    <td>${{r.Close?.toFixed(2) ?? '-'}}</td>
    <td class="up">+${{r.Change?.toFixed(2) ?? '0'}}</td>
    <td class="up">+${{r.Pct_Change?.toFixed(2) ?? '0'}}%</td>
  </tr>`;
}});

new Chart(document.getElementById('gainChart'), {{
  type:'bar',
  data:{{
    labels: GAINERS.map(r=>r.Company),
    datasets:[{{
      data: GAINERS.map(r=>r.Pct_Change),
      backgroundColor:'rgba(26,107,60,0.75)',
      borderRadius:5,
    }}]
  }},
  options:{{
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{title:{{display:true,text:'% Change'}}}},
      x:{{ticks:{{maxRotation:45,font:{{size:10}}}}}}
    }},
    responsive:true,
    maintainAspectRatio:true,
  }}
}});

// ── Losers table & chart ──
const lossBody = document.getElementById('lossBody');
LOSERS.forEach(r => {{
  lossBody.innerHTML += `<tr>
    <td>${{r.Company}}</td>
    <td>${{r.Prev_Close?.toFixed(2) ?? '-'}}</td>
    <td>${{r.Close?.toFixed(2) ?? '-'}}</td>
    <td class="dn">${{r.Change?.toFixed(2) ?? '0'}}</td>
    <td class="dn">${{r.Pct_Change?.toFixed(2) ?? '0'}}%</td>
  </tr>`;
}});

new Chart(document.getElementById('lossChart'), {{
  type:'bar',
  data:{{
    labels: LOSERS.map(r=>r.Company),
    datasets:[{{
      data: LOSERS.map(r=>r.Pct_Change),
      backgroundColor:'rgba(192,57,43,0.75)',
      borderRadius:5,
    }}]
  }},
  options:{{
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{title:{{display:true,text:'% Change'}}}},
      x:{{ticks:{{maxRotation:45,font:{{size:10}}}}}}
    }},
    responsive:true,
    maintainAspectRatio:true,
  }}
}});

// ── My Portfolio cards ──
const portGrid = document.getElementById('portGrid');
if (PORTFOLIO.length === 0 && PORT_MISS.length > 0) {{
  portGrid.innerHTML = "<p style='color:var(--muted);font-size:.85rem;'>No portfolio stocks found in today&apos;s data.</p>";
}} else {{
  PORTFOLIO.forEach(r => {{
    const pct  = r.Pct_Change ?? 0;
    const sign = pct >= 0 ? '+' : '';
    const cls  = pct > 0 ? 'up' : pct < 0 ? 'dn' : 'neu';
    const borderCol = pct > 0 ? 'var(--green)' : pct < 0 ? 'var(--red)' : 'var(--muted)';
    const sig  = PORT_SIGNALS[r.Company] || {{}};
    const sigText = sig.signal || 'HOLD';
    const sigReason = sig.reason || '';
    const sigCls = sigText === 'SELL' ? 'sell'
                 : sigText === 'CONSIDER SELLING' ? 'consider'
                 : sigText === 'WATCH CLOSELY' ? 'watch'
                 : sigText === 'KEEP' ? 'keep' : 'hold';
    const sessions = sig.sessions ? sig.sessions + ' sessions' : 'today only';
    const netChg   = sig.net_change_pct != null ? (sig.net_change_pct >= 0 ? '+' : '') + sig.net_change_pct.toFixed(2) + '%' : '\u2014';
    portGrid.innerHTML += `
      <div class="port-card" style="border-top-color:${{borderCol}}">
        <div class="port-sym">${{r.Company}}</div>
        <div class="port-price ${{cls}}">&#8358;${{r.Close?.toFixed(2) ?? '\u2014'}}</div>
        <div class="port-chg ${{cls}}">${{sign}}${{pct.toFixed(2)}}% today</div>
        <div class="port-row">Prev Close: <b>&#8358;${{r.Prev_Close?.toFixed(2) ?? '\u2014'}}</b></div>
        <div class="port-row">High / Low: <b>&#8358;${{r.High?.toFixed(2) ?? '\u2014'}} / &#8358;${{r.Low?.toFixed(2) ?? '\u2014'}}</b></div>
        <div class="port-row">Vol: <b>${{r.Volume ? r.Volume.toLocaleString() : '\u2014'}}</b> &nbsp; Trades: <b>${{r.Trades ?? '\u2014'}}</b></div>
        <div class="port-row">Trend (${{sessions}}): <b>${{netChg}}</b></div>
        <div><span class="port-signal ${{sigCls}}">${{sigText}}</span></div>
        <div class="port-reason">${{sigReason}}</div>
      </div>`;
  }});
  PORT_MISS.forEach(name => {{
    portGrid.innerHTML += `
      <div class="port-card" style="border-top-color:var(--muted);opacity:.55">
        <div class="port-sym">${{name}}</div>
        <div style="font-size:.8rem;color:var(--muted);margin-top:10px;">Not found in today&apos;s data</div>
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
  const cons     = r.consistency != null ? (r.consistency*100).toFixed(0)+'%' : '—';
  const score    = r.Score?.toFixed(1) ?? '—';
  const vol      = r.Volume ? r.Volume.toLocaleString() : '—';
  const sign     = pct >= 0 ? '+' : '';
  const priceClass = pct >= 0 ? '' : 'dn';
  const watchClass = isBuy   ? '' : 'watch';
  const sigClass   = isBuy   ? '' : 'watch';

  recGrid.innerHTML += `
  <div class="rec-card ${{watchClass}}">
    <div class="rec-sym">${{r.Company}}</div>
    <div class="rec-price ${{priceClass}}">₦${{r.Close?.toFixed(2) ?? '—'}}</div>
    <div class="rec-pct ${{pct>=0?'up':'dn'}}">${{sign}}${{pct.toFixed(2)}}%</div>
    <div class="rec-row">Score: <b>${{score}}</b></div>
    <div class="rec-row">Momentum: <b>${{mom>=0?'+':''}}${{typeof mom==='number'?mom.toFixed(1):'—'}}%</b></div>
    <div class="rec-row">Consistency: <b>${{cons}}</b></div>
    <div class="rec-row">Volume: <b>${{vol}}</b></div>
    <div><span class="signal ${{sigClass}}">${{signal}}</span></div>
  </div>`;
}});
</script>
</body>
</html>
"""


# ── Generator ─────────────────────────────────────────────────────────────────

def generate(df: pd.DataFrame, snapshots: list, top_n: int = 10, rec_n: int = 5) -> None:
    now_str = datetime.now().strftime("%d %b %Y, %H:%M WAT")

    gainers = get_top_gainers(df, n=top_n)
    losers  = get_top_losers(df,  n=top_n)
    recs    = generate_recommendations(df, snapshots, top_n=rec_n)
    port_df, port_missing = find_portfolio_stocks(df, PORTFOLIO_STOCKS)

    # Compute SELL/HOLD/KEEP signals for each matched portfolio stock
    port_signals = {}
    for _, row in port_df.iterrows():
        sig = score_portfolio_stock(row["Company"], row, snapshots)
        port_signals[row["Company"]] = sig

    total     = len(df)
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
        updated      = now_str,
        total        = total,
        advancing    = advancing,
        declining    = declining,
        unchanged    = unchanged,
        avg_chg      = avg_str,
        avg_color    = avg_color,
        snapshots    = len(snapshots),
        top_n        = top_n,
        rec_note     = rec_note,
        gainers_json   = json.dumps(to_records(gainers),   ensure_ascii=False),
        losers_json    = json.dumps(to_records(losers),    ensure_ascii=False),
        recs_json      = json.dumps(to_records(recs),      ensure_ascii=False),
        portfolio_json = json.dumps(to_records(port_df) if not port_df.empty else [], ensure_ascii=False),
        missing_json   = json.dumps(port_missing,                                      ensure_ascii=False),
        signals_json   = json.dumps(port_signals,                                      ensure_ascii=False),
    )

    OUTPUT.write_text(html, encoding="utf-8")
    logger.info(f"HTML written to {OUTPUT.resolve()}")


# ── Entry point ────────────────────────────────────────────────────────────────

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

    snapshots = load_snapshots(last_n=24)
    generate(df, snapshots, top_n=args.top, rec_n=args.rec)
    print(f"\nOK  docs/index.html generated -- {len(df)} stocks processed.")
    print("   Push to GitHub and enable Pages -> branch: main, folder: /docs\n")


if __name__ == "__main__":
    main()
