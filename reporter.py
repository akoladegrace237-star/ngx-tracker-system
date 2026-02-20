"""
NGX Report Formatter
Renders analysis results as readable console output and saves to file.
"""

import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import logging

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("data/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DIVIDER = "=" * 75
THIN_DIV = "-" * 75


def _format_currency(val: float) -> str:
    if val >= 1_000_000_000:
        return f"₦{val / 1_000_000_000:.2f}B"
    elif val >= 1_000_000:
        return f"₦{val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"₦{val / 1_000:.1f}K"
    return f"₦{val:.2f}"


def _format_volume(vol: float) -> str:
    if vol >= 1_000_000:
        return f"{vol / 1_000_000:.2f}M"
    elif vol >= 1_000:
        return f"{vol / 1_000:.1f}K"
    return str(int(vol))


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def _gainers_losers_table(df: pd.DataFrame) -> str:
    lines = []
    lines.append(f"{'#':<4} {'SYMBOL':<15} {'PREV':>8} {'CLOSE':>8} {'CHG':>8} {'PCT':>8} {'VOLUME':>12} {'VALUE':>12}")
    lines.append(THIN_DIV)
    for i, row in df.iterrows():
        pct = row.get("Pct_Change", 0)
        arrow = _arrow(pct)
        lines.append(
            f"{i + 1:<4} {str(row['Company']):<15} "
            f"{row.get('Prev_Close', 0):>8.2f} "
            f"{row.get('Close', 0):>8.2f} "
            f"{arrow}{abs(row.get('Change', 0)):>7.2f} "
            f"{arrow}{abs(pct):>7.2f}% "
            f"{_format_volume(row.get('Volume', 0)):>12} "
            f"{_format_currency(row.get('Value', 0)):>12}"
        )
    return "\n".join(lines)


def _recommendations_table(df: pd.DataFrame) -> str:
    lines = []
    lines.append(f"{'#':<4} {'SYMBOL':<15} {'CLOSE':>8} {'PCT':>8} {'SCORE':>8} {'VOLUME':>12} {'SIGNAL':<18} REASONING")
    lines.append(THIN_DIV)
    for i, row in df.iterrows():
        pct = row.get("Pct_Change", 0)
        score = row.get("Score", 0)
        signal = row.get("Recommendation", "WATCH")
        momentum = row.get("momentum_%", row.get("Pct_Change", 0))
        consistency = row.get("consistency", "-")
        vol_trend = row.get("volume_trend_%", "-")

        reasoning_parts = []
        if isinstance(momentum, float):
            reasoning_parts.append(f"Mom:{momentum:+.1f}%")
        if isinstance(consistency, float):
            reasoning_parts.append(f"Cons:{consistency:.0%}")
        if isinstance(vol_trend, float):
            reasoning_parts.append(f"Vol:{vol_trend:+.0f}%")

        reasoning = "  ".join(reasoning_parts) if reasoning_parts else "Single-session signal"

        lines.append(
            f"{i + 1:<4} {str(row.get('Company', '')):<15} "
            f"{row.get('Close', 0):>8.2f} "
            f"{pct:>+8.2f}% "
            f"{score:>8.1f} "
            f"{_format_volume(row.get('Volume', 0)):>12} "
            f"{signal:<18} {reasoning}"
        )
    return "\n".join(lines)


def build_report(
    current_df: pd.DataFrame,
    gainers: pd.DataFrame,
    losers: pd.DataFrame,
    recommendations: pd.DataFrame,
    num_snapshots: int,
) -> str:
    now = datetime.now().strftime("%A, %d %B %Y  %H:%M:%S")
    total_stocks = len(current_df)
    advancing = (current_df["Pct_Change"] > 0).sum()
    declining = (current_df["Pct_Change"] < 0).sum()
    unchanged = (current_df["Pct_Change"] == 0).sum()

    lines = [
        "",
        DIVIDER,
        f"  NGX EQUITIES TRACKER  —  {now}",
        DIVIDER,
        f"  Market Overview: {total_stocks} stocks  |  "
        f"▲ {advancing} advancing  |  ▼ {declining} declining  |  — {unchanged} unchanged",
        f"  Historical snapshots used: {num_snapshots}",
        DIVIDER,
        "",
        "  TOP 10 GAINERS",
        THIN_DIV,
        _gainers_losers_table(gainers),
        "",
        DIVIDER,
        "",
        "  TOP 10 LOSERS",
        THIN_DIV,
        _gainers_losers_table(losers),
        "",
        DIVIDER,
        "",
        "  BUY RECOMMENDATIONS  (based on multi-session trend analysis)",
        THIN_DIV,
        _recommendations_table(recommendations),
        "",
        DIVIDER,
        "  SIGNAL GUIDE:  STRONG BUY ≥30pts  |  BUY ≥15pts  |  WATCH ≥5pts  |  HOLD <5pts",
        "  Score factors: Price momentum (40%), Trend consistency (20%),",
        "  Volume confirmation (10%), Recent momentum (30%); -15pts for 3 down-sessions",
        DIVIDER,
        "",
    ]
    return "\n".join(lines)


def print_report(report: str) -> None:
    print(report)


def save_report(report: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = REPORTS_DIR / f"report_{timestamp}.txt"
    filepath.write_text(report, encoding="utf-8")
    logger.info(f"Report saved: {filepath}")
    return filepath
