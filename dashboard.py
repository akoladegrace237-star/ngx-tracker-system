"""
NGX Equities Tracking Dashboard
Run with:  streamlit run dashboard.py
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ── make local modules importable ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from scraper import get_equities_data
from analyzer import (
    get_top_gainers,
    get_top_losers,
    generate_recommendations,
    save_snapshot,
    load_snapshots,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NGX Equities Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a6b3c;
        margin-bottom: 0;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #666;
        margin-top: 0;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border-left: 4px solid #1a6b3c;
    }
    .gain-cell  { color: #1a7a3c; font-weight: 600; }
    .loss-cell  { color: #c0392b; font-weight: 600; }
    .buy-badge  { background:#1a7a3c; color:white; padding:2px 8px; border-radius:4px; font-size:0.75rem; }
    .watch-badge{ background:#e67e22; color:white; padding:2px 8px; border-radius:4px; font-size:0.75rem; }
    .stDataFrame { width: 100%; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://ngxgroup.com/wp-content/uploads/2019/11/Nigerian-Exchange-Group-Logo-1.png",
             width=200, use_container_width=False)
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    auto_refresh = st.toggle("Auto-refresh (hourly)", value=False)
    refresh_interval = st.slider("Refresh interval (minutes)", 15, 120, 60, step=15)
    top_n = st.slider("Top N gainers / losers", 5, 20, 10)
    rec_n = st.slider("Recommendations to show", 3, 10, 5)
    st.markdown("---")
    fetch_btn = st.button("🔄 Fetch Now", use_container_width=True, type="primary")
    st.markdown("---")
    st.markdown("**Data source**")
    st.markdown("[NGX Equities Price List](https://ngxgroup.com/exchange/data/equities-price-list/)")
    st.caption("Prices delayed 30 min per NGX policy.")

# ── Session state ─────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = None
if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = None
if "gainers" not in st.session_state:
    st.session_state.gainers = None
if "losers" not in st.session_state:
    st.session_state.losers = None
if "recs" not in st.session_state:
    st.session_state.recs = None
if "snapshots" not in st.session_state:
    st.session_state.snapshots = []

# ── Data fetching ─────────────────────────────────────────────────────────────
def do_fetch():
    with st.spinner("Fetching live data from NGX website... (this takes ~20s)"):
        df = get_equities_data()
    if df.empty:
        st.error("❌ Failed to fetch data. Check your internet connection and try again.")
        return
    save_snapshot(df)
    snaps = load_snapshots(last_n=24)
    gainers = get_top_gainers(df, n=top_n)
    losers  = get_top_losers(df,  n=top_n)
    recs    = generate_recommendations(df, snaps, top_n=rec_n)

    st.session_state.df        = df
    st.session_state.gainers   = gainers
    st.session_state.losers    = losers
    st.session_state.recs      = recs
    st.session_state.snapshots = snaps
    st.session_state.last_fetch = datetime.now()


# Auto-load on first visit
if st.session_state.df is None:
    do_fetch()

# Manual fetch button
if fetch_btn:
    do_fetch()

# Auto-refresh
if auto_refresh and st.session_state.last_fetch:
    elapsed = (datetime.now() - st.session_state.last_fetch).total_seconds() / 60
    if elapsed >= refresh_interval:
        do_fetch()
        st.rerun()

# ── Main content ──────────────────────────────────────────────────────────────
df      = st.session_state.df
gainers = st.session_state.gainers
losers  = st.session_state.losers
recs    = st.session_state.recs
snaps   = st.session_state.snapshots

st.markdown('<p class="main-title">📈 NGX Equities Tracking Dashboard</p>', unsafe_allow_html=True)
if st.session_state.last_fetch:
    st.markdown(f'<p class="sub-title">Last updated: {st.session_state.last_fetch.strftime("%A %d %B %Y, %H:%M:%S")} &nbsp;|&nbsp; {len(snaps)} historical snapshot(s) loaded</p>',
                unsafe_allow_html=True)

st.markdown("---")

if df is None or df.empty:
    st.info("No data yet. Click **Fetch Now** in the sidebar.")
    st.stop()

# ── Market Overview KPIs ──────────────────────────────────────────────────────
total     = len(df)
advancing = int((df["Pct_Change"] > 0).sum())
declining = int((df["Pct_Change"] < 0).sum())
unchanged = int((df["Pct_Change"] == 0).sum())
avg_chg   = df["Pct_Change"].mean()
total_vol = df["Volume"].sum()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Stocks",   f"{total}")
c2.metric("Advancing ▲",    f"{advancing}", delta=f"{advancing/total*100:.0f}%", delta_color="normal")
c3.metric("Declining ▼",    f"{declining}", delta=f"-{declining/total*100:.0f}%", delta_color="inverse")
c4.metric("Unchanged —",    f"{unchanged}")
c5.metric("Avg Change",     f"{avg_chg:+.2f}%", delta_color="normal" if avg_chg >= 0 else "inverse")
c6.metric("Total Volume",   f"{total_vol/1e6:.1f}M")

st.markdown("---")

# ── Top Gainers & Losers ──────────────────────────────────────────────────────
col_g, col_l = st.columns(2)

with col_g:
    st.subheader(f"🟢 Top {top_n} Gainers")
    if gainers is not None and not gainers.empty:
        fig_g = px.bar(
            gainers,
            x="Company",
            y="Pct_Change",
            color="Pct_Change",
            color_continuous_scale=["#a8d5b5", "#1a7a3c"],
            text=gainers["Pct_Change"].apply(lambda x: f"+{x:.2f}%"),
            labels={"Pct_Change": "% Change"},
            height=320,
        )
        fig_g.update_traces(textposition="outside")
        fig_g.update_layout(
            margin=dict(t=10, b=0, l=0, r=0),
            xaxis_title=None,
            yaxis_title="% Change",
            coloraxis_showscale=False,
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_g, use_container_width=True)

        display_g = gainers[["Company", "Prev_Close", "Close", "Change", "Pct_Change", "Volume"]].copy()
        display_g["Pct_Change"] = display_g["Pct_Change"].apply(lambda x: f"+{x:.2f}%")
        display_g["Change"]     = display_g["Change"].apply(lambda x: f"+{x:.2f}")
        display_g.columns       = ["Symbol", "Prev ₦", "Close ₦", "Change", "% Change", "Volume"]
        st.dataframe(display_g, use_container_width=True, hide_index=True)


with col_l:
    st.subheader(f"🔴 Top {top_n} Losers")
    if losers is not None and not losers.empty:
        fig_l = px.bar(
            losers,
            x="Company",
            y="Pct_Change",
            color="Pct_Change",
            color_continuous_scale=["#c0392b", "#fadbd8"],
            text=losers["Pct_Change"].apply(lambda x: f"{x:.2f}%"),
            labels={"Pct_Change": "% Change"},
            height=320,
        )
        fig_l.update_traces(textposition="outside")
        fig_l.update_layout(
            margin=dict(t=10, b=0, l=0, r=0),
            xaxis_title=None,
            yaxis_title="% Change",
            coloraxis_showscale=False,
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_l, use_container_width=True)

        display_l = losers[["Company", "Prev_Close", "Close", "Change", "Pct_Change", "Volume"]].copy()
        display_l["Pct_Change"] = display_l["Pct_Change"].apply(lambda x: f"{x:.2f}%")
        display_l["Change"]     = display_l["Change"].apply(lambda x: f"{x:.2f}")
        display_l.columns       = ["Symbol", "Prev ₦", "Close ₦", "Change", "% Change", "Volume"]
        st.dataframe(display_l, use_container_width=True, hide_index=True)

st.markdown("---")

# ── Bubble chart: Volume vs % Change ─────────────────────────────────────────
st.subheader("📊 Market Map — Volume vs Price Change")
plot_df = df[(df["Volume"] > 0) & (df["Pct_Change"] != 0)].copy()
plot_df["Color"] = plot_df["Pct_Change"].apply(lambda x: "▲ Gainers" if x > 0 else "▼ Losers")
if not plot_df.empty:
    fig_bubble = px.scatter(
        plot_df,
        x="Pct_Change",
        y="Close",
        size=plot_df["Volume"].clip(upper=plot_df["Volume"].quantile(0.95)),
        color="Color",
        color_discrete_map={"▲ Gainers": "#1a7a3c", "▼ Losers": "#c0392b"},
        hover_name="Company",
        hover_data={"Pct_Change": ":.2f", "Close": ":.2f", "Volume": ":,.0f", "Color": False},
        labels={"Pct_Change": "% Change", "Close": "Close Price (₦)"},
        height=400,
    )
    fig_bubble.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig_bubble.update_layout(
        margin=dict(t=10, b=0, l=0, r=0),
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    st.plotly_chart(fig_bubble, use_container_width=True)

st.markdown("---")

# ── Buy Recommendations ───────────────────────────────────────────────────────
st.subheader("💡 Buy Recommendations")

snap_info = f"Based on {len(snaps)} snapshot(s)" if len(snaps) >= 2 else "Based on current session only (more snapshots improve accuracy)"
st.caption(snap_info)

if recs is not None and not recs.empty:
    NUM_COLS = min(len(recs), rec_n)
    rec_cols = st.columns(NUM_COLS)
    for i, (_, row) in enumerate(recs.iterrows()):
        if i >= NUM_COLS:
            break
        signal = str(row.get("Recommendation", "WATCH"))
        score  = row.get("Score", 0)
        pct    = row.get("Pct_Change", 0)
        close  = row.get("Close", 0)
        vol    = row.get("Volume", 0)

        color = "#1a7a3c" if "BUY" in signal else "#e67e22"
        momentum = row.get("momentum_%", pct)
        consistency = row.get("consistency", None)

        with rec_cols[i]:
            st.markdown(f"""
            <div style="background:#f0f9f4;border-radius:10px;padding:16px;border-top:4px solid {color};text-align:center">
                <div style="font-size:1.3rem;font-weight:700;color:#111">{row['Company']}</div>
                <div style="font-size:1.6rem;font-weight:800;color:{color}">₦{close:,.2f}</div>
                <div style="font-size:1rem;color:{'#1a7a3c' if pct>=0 else '#c0392b'}">{'+' if pct>=0 else ''}{pct:.2f}%</div>
                <hr style="margin:8px 0">
                <div style="font-size:0.85rem;color:#333">Score: <b>{score:.1f}</b></div>
                <div style="font-size:0.85rem;color:#333">Momentum: <b>{momentum:+.1f}%</b></div>
                {"<div style='font-size:0.85rem;color:#333'>Consistency: <b>" + f"{consistency:.0%}</b></div>" if isinstance(consistency, float) else ""}
                <div style="font-size:0.85rem;color:#333">Volume: <b>{vol:,.0f}</b></div>
                <div style="margin-top:10px">
                    <span style="background:{color};color:white;padding:4px 12px;border-radius:20px;font-size:0.8rem;font-weight:700">{signal}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")
    st.markdown("**Score guide:** STRONG BUY ≥30 &nbsp;|&nbsp; BUY ≥15 &nbsp;|&nbsp; WATCH ≥5 &nbsp;|&nbsp; HOLD <5")
    st.markdown("**Factors:** Price momentum (40%), Trend consistency (20%), Volume confirmation (10%), Recent momentum (30%); −15pts for 3 consecutive down-sessions")

st.markdown("---")

# ── Full price list ───────────────────────────────────────────────────────────
with st.expander("📋 Full Equities Price List", expanded=False):
    search = st.text_input("Search symbol", placeholder="e.g. ZENITHBANK")
    show_df = df.copy()
    if search:
        show_df = show_df[show_df["Company"].str.contains(search.upper(), na=False)]

    # Colour-code pct change
    def pct_color(val):
        if val > 0:  return "color: #1a7a3c; font-weight:600"
        if val < 0:  return "color: #c0392b; font-weight:600"
        return ""

    cols_to_show = ["Company", "Prev_Close", "Opening_Price", "High", "Low", "Close", "Change", "Pct_Change", "Volume", "Value"]
    cols_to_show = [c for c in cols_to_show if c in show_df.columns]
    styled = (
        show_df[cols_to_show]
        .rename(columns={
            "Prev_Close": "Prev ₦", "Opening_Price": "Open ₦",
            "High": "High ₦", "Low": "Low ₦", "Close": "Close ₦",
            "Pct_Change": "% Chg",
        })
        .style.applymap(pct_color, subset=["% Chg"])
        .format({
            "Prev ₦": "{:,.2f}", "Open ₦": "{:,.2f}",
            "High ₦": "{:,.2f}", "Low ₦":  "{:,.2f}",
            "Close ₦": "{:,.2f}", "Change": "{:+.2f}",
            "% Chg": "{:+.2f}%", "Volume": "{:,.0f}",
            "Value": "{:,.0f}",
        }, na_rep="-")
    )
    st.dataframe(styled, use_container_width=True, height=500)

# ── Auto-refresh countdown ────────────────────────────────────────────────────
if auto_refresh:
    if st.session_state.last_fetch:
        elapsed_s  = int((datetime.now() - st.session_state.last_fetch).total_seconds())
        remaining  = max(0, refresh_interval * 60 - elapsed_s)
        mins, secs = divmod(remaining, 60)
        st.sidebar.caption(f"⏱ Next refresh in {mins}m {secs}s")
        if remaining == 0:
            st.rerun()
    time.sleep(30)
    st.rerun()
