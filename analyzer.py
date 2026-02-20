"""
NGX Trend Analyzer & Stock Recommendation Engine
Analyzes historical snapshots and recommends stocks to buy.
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

HISTORY_DIR = Path("data/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# -- Persistence ---------------------------------------------------------------

def save_snapshot(df: pd.DataFrame) -> None:
    """Persist a snapshot to disk as JSON."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = HISTORY_DIR / f"snapshot_{timestamp}.json"
    df.to_json(filepath, orient="records", indent=2)
    logger.info(f"Snapshot saved: {filepath}")
    _prune_old_snapshots(keep_last=720)  # keep 30 days × 24 hrs


def _prune_old_snapshots(keep_last: int = 720) -> None:
    """Remove oldest snapshots beyond the retention limit."""
    snapshots = sorted(HISTORY_DIR.glob("snapshot_*.json"))
    while len(snapshots) > keep_last:
        snapshots.pop(0).unlink()


def load_snapshots(last_n: int = 24) -> list[pd.DataFrame]:
    """Load the most recent N snapshots from disk."""
    snapshots = sorted(HISTORY_DIR.glob("snapshot_*.json"))[-last_n:]
    frames = []
    for path in snapshots:
        try:
            df = pd.read_json(path, orient="records")
            frames.append(df)
        except Exception as e:
            logger.warning(f"Could not load {path}: {e}")
    return frames


# -- Core Analysis -------------------------------------------------------------

def get_top_gainers(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top N stocks by percentage gain in the current session."""
    gainers = df[df["Pct_Change"] > 0].copy()
    gainers = gainers.sort_values("Pct_Change", ascending=False).head(n)
    return gainers[["Company", "Prev_Close", "Close", "Change", "Pct_Change", "Volume", "Value"]].reset_index(drop=True)


def get_top_losers(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top N stocks by percentage decline in the current session."""
    losers = df[df["Pct_Change"] < 0].copy()
    losers = losers.sort_values("Pct_Change", ascending=True).head(n)
    return losers[["Company", "Prev_Close", "Close", "Change", "Pct_Change", "Volume", "Value"]].reset_index(drop=True)


# -- Multi-period Trend Scoring -------------------------------------------------

def build_price_history(snapshots: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Combine multiple snapshots into a wide DataFrame indexed by Company
    with one 'Close' column per snapshot.
    """
    if not snapshots:
        return pd.DataFrame()

    frames = []
    for i, snap in enumerate(snapshots):
        if "Company" not in snap.columns or "Close" not in snap.columns:
            continue
        sub = snap[["Company", "Close", "Volume", "Pct_Change"]].copy()
        sub = sub.rename(columns={"Close": f"close_{i}", "Volume": f"vol_{i}", "Pct_Change": f"pct_{i}"})
        frames.append(sub.set_index("Company"))

    if not frames:
        return pd.DataFrame()

    history = pd.concat(frames, axis=1)
    return history


def score_stock(row: pd.Series, n_snapshots: int) -> dict:
    """
    Score a stock using several trend signals.
    Returns a dict with individual signal scores and total score.
    """
    close_cols = [c for c in row.index if c.startswith("close_")]
    vol_cols = [c for c in row.index if c.startswith("vol_")]
    pct_cols = [c for c in row.index if c.startswith("pct_")]

    closes = row[close_cols].dropna().values.astype(float)
    vols = row[vol_cols].dropna().values.astype(float)
    pcts = row[pct_cols].dropna().values.astype(float)

    score = 0.0
    signals = {}

    if len(closes) < 2:
        return {"score": 0.0, "signals": {}}

    # 1. Price momentum: net change over all available snapshots
    net_change = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] != 0 else 0
    signals["momentum_%"] = round(net_change, 2)
    score += net_change * 0.4

    # 2. Trend consistency: fraction of positive pct_change periods
    if len(pcts) > 0:
        positive_periods = (pcts > 0).sum()
        consistency = positive_periods / len(pcts)
        signals["consistency"] = round(consistency, 2)
        score += consistency * 20
    
    # 3. Volume trend: is volume rising alongside price?
    if len(vols) >= 2 and vols[0] != 0:
        vol_trend = (vols[-1] - vols[0]) / vols[0] * 100
        signals["volume_trend_%"] = round(vol_trend, 2)
        # Reward rising volume only when price is also rising
        if net_change > 0 and vol_trend > 0:
            score += 10
        elif net_change < 0 and vol_trend > 0:
            score -= 5
    
    # 4. Recent momentum (last 3 snapshots vs earlier)
    if len(closes) >= 4:
        recent_avg = np.mean(closes[-3:])
        earlier_avg = np.mean(closes[:-3])
        if earlier_avg != 0:
            recent_momentum = (recent_avg - earlier_avg) / earlier_avg * 100
            signals["recent_momentum_%"] = round(recent_momentum, 2)
            score += recent_momentum * 0.3

    # 5. Avoid declining streaks: penalise if last 3 pcts all negative
    if len(pcts) >= 3 and all(p < 0 for p in pcts[-3:]):
        score -= 15
        signals["consecutive_declines"] = 3

    signals["total_score"] = round(score, 2)
    return {"score": round(score, 2), "signals": signals}


def generate_recommendations(current_df: pd.DataFrame, snapshots: list[pd.DataFrame], top_n: int = 5) -> pd.DataFrame:
    """
    Analyse trend across all snapshots and rank stocks by buy-worthiness.
    Returns a DataFrame of recommended stocks with their scores and reasoning.
    """
    # If fewer than 2 snapshots, fall back to single-session analysis
    if len(snapshots) < 2:
        logger.info("Insufficient history; using single-session signals only.")
        return _single_session_recommendations(current_df, top_n)

    history = build_price_history(snapshots)
    if history.empty:
        return _single_session_recommendations(current_df, top_n)

    scored = []
    for company, row in history.iterrows():
        result = score_stock(row, len(snapshots))
        if result["score"] > 0:
            scored.append({
                "Company": company,
                "Score": result["score"],
                **result["signals"],
            })

    if not scored:
        return _single_session_recommendations(current_df, top_n)

    scored_df = pd.DataFrame(scored).sort_values("Score", ascending=False).head(top_n)

    # Merge in current prices
    price_cols = current_df[["Company", "Close", "Pct_Change", "Volume"]].copy()
    scored_df = scored_df.merge(price_cols, on="Company", how="left")

    scored_df["Recommendation"] = scored_df["Score"].apply(_score_to_label)
    return scored_df.reset_index(drop=True)


def _single_session_recommendations(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Fallback: recommend top gainers with high volume from a single snapshot."""
    candidates = df[(df["Pct_Change"] > 0) & (df["Volume"] > 0)].copy()
    candidates["Score"] = candidates["Pct_Change"] * np.log1p(candidates["Volume"])
    candidates = candidates.sort_values("Score", ascending=False).head(top_n)
    candidates["momentum_%"] = candidates["Pct_Change"]
    candidates["Recommendation"] = "WATCH / BUY (single-session)"
    return candidates[["Company", "Close", "Pct_Change", "Volume", "Score", "Recommendation"]].reset_index(drop=True)


def _score_to_label(score: float) -> str:
    if score >= 30:
        return "STRONG BUY"
    elif score >= 15:
        return "BUY"
    elif score >= 5:
        return "WATCH"
    else:
        return "HOLD"


def score_portfolio_stock(company: str, current_row: pd.Series, snapshots: list) -> dict:
    """
    Assess whether a portfolio stock should be sold, held, or kept.
    Returns dict with signal, reason, and supporting stats.
    Signals: SELL | CONSIDER SELLING | WATCH CLOSELY | HOLD | KEEP
    """
    if len(snapshots) < 2:
        pct = float(current_row.get("Pct_Change", 0))
        signal = "WATCH CLOSELY" if pct < -3 else "HOLD"
        return {"signal": signal, "reason": "Insufficient history — check back tomorrow",
                "net_change_pct": pct, "recent_avg_pct": pct,
                "consec_down": 1 if pct < 0 else 0, "sessions": 1,
                "week_change_pct": pct, "three_day_change_pct": pct}

    closes, pcts = [], []
    for snap in snapshots:
        mask = snap["Company"].str.upper().str.startswith(company.upper().split(" ")[0])
        match = snap[mask]
        if not match.empty:
            closes.append(float(match.iloc[0]["Close"]))
            pcts.append(float(match.iloc[0]["Pct_Change"]))

    if len(closes) < 2:
        return {"signal": "HOLD", "reason": "Not enough historical data yet",
                "net_change_pct": 0, "recent_avg_pct": 0,
                "consec_down": 0, "sessions": 0,
                "week_change_pct": 0, "three_day_change_pct": 0}

    sessions = len(closes)
    net_change = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] != 0 else 0.0

    recent_pcts = pcts[-3:] if len(pcts) >= 3 else pcts
    recent_avg = float(np.mean(recent_pcts))

    consec_down = 0
    for p in reversed(pcts):
        if p < 0:
            consec_down += 1
        else:
            break

    week_closes = closes[-min(168, len(closes)):]
    week_change = (week_closes[-1] - week_closes[0]) / week_closes[0] * 100 if week_closes[0] != 0 else 0.0

    three_day_closes = closes[-min(72, len(closes)):]
    three_day_change = (three_day_closes[-1] - three_day_closes[0]) / three_day_closes[0] * 100 if three_day_closes[0] != 0 else 0.0

    if net_change <= -10 and consec_down >= 5:
        signal = "SELL"
        reason = f"Down {abs(net_change):.1f}% over {sessions} sessions with {consec_down} consecutive declines"
    elif net_change <= -5 and recent_avg < -1:
        signal = "CONSIDER SELLING"
        reason = f"Down {abs(net_change):.1f}% overall; recent avg {recent_avg:.1f}%/session"
    elif consec_down >= 5:
        signal = "CONSIDER SELLING"
        reason = f"{consec_down} consecutive declining sessions — momentum is bearish"
    elif net_change < -2 and recent_avg < 0:
        signal = "WATCH CLOSELY"
        reason = f"Down {abs(net_change):.1f}% with negative recent trend"
    elif net_change > 5 and recent_avg > 0:
        signal = "KEEP"
        reason = f"Up {net_change:.1f}% over {sessions} sessions — strong trend"
    elif net_change > 0:
        signal = "HOLD"
        reason = f"Slight gain of {net_change:.1f}% — stable, continue monitoring"
    else:
        signal = "HOLD"
        reason = f"Mixed signals over {sessions} sessions — no clear direction"

    return {
        "signal": signal,
        "reason": reason,
        "net_change_pct": round(net_change, 2),
        "recent_avg_pct": round(recent_avg, 2),
        "consec_down": consec_down,
        "sessions": sessions,
        "week_change_pct": round(week_change, 2),
        "three_day_change_pct": round(three_day_change, 2),
    }


# -- Quick test -----------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from scraper import get_equities_data

    df = get_equities_data()
    if not df.empty:
        print("\nTOP 10 GAINERS:")
        print(get_top_gainers(df).to_string(index=False))
        print("\nTOP 10 LOSERS:")
        print(get_top_losers(df).to_string(index=False))
        save_snapshot(df)
        snaps = load_snapshots()
        print("\nRECOMMENDATIONS:")
        print(generate_recommendations(df, snaps).to_string(index=False))
