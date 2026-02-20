"""
NGX Tracking Agent
------------------
Runs on an hourly schedule, scrapes the NGX equities price list,
analyses gainers / losers and trend-based buy recommendations,
then prints a formatted report and saves it to disk.

Usage:
    python agent.py              # Run immediately then every hour
    python agent.py --once       # Run once and exit
    python agent.py --interval 30  # Run every 30 minutes
"""

import argparse
import logging
import sys
import time
from datetime import datetime

import schedule

from scraper import get_equities_data
from analyzer import (
    get_top_gainers,
    get_top_losers,
    generate_recommendations,
    save_snapshot,
    load_snapshots,
)
from reporter import build_report, print_report, save_report

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("ngx_agent")


# ── Core job ──────────────────────────────────────────────────────────────────

def run_analysis() -> None:
    """Fetch data, analyse, report."""
    logger.info("Starting NGX data fetch and analysis…")

    # 1. Fetch current data
    df = get_equities_data()
    if df.empty:
        logger.error("No data returned from NGX website. Skipping this cycle.")
        return

    # 2. Persist snapshot for trend analysis
    save_snapshot(df)

    # 3. Load historical snapshots (last 24 hrs)
    snapshots = load_snapshots(last_n=24)
    logger.info(f"Loaded {len(snapshots)} historical snapshot(s) for trend analysis.")

    # 4. Compute gainers / losers
    gainers = get_top_gainers(df, n=10)
    losers = get_top_losers(df, n=10)

    # 5. Generate recommendations
    recommendations = generate_recommendations(df, snapshots, top_n=5)

    # 6. Build, print, and save the report
    report = build_report(df, gainers, losers, recommendations, len(snapshots))
    print_report(report)
    path = save_report(report)
    logger.info(f"Report saved to {path}")
    logger.info("Analysis cycle complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="NGX Equities Tracking Agent")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no scheduling)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        metavar="MINUTES",
        help="How often to run in minutes (default: 60)",
    )
    args = parser.parse_args()

    print(
        "\n"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║          NGX Equities Tracking Agent — Starting Up          ║\n"
        "╚══════════════════════════════════════════════════════════════╝\n"
    )

    # Always run immediately on start
    run_analysis()

    if args.once:
        logger.info("--once flag set. Exiting after first run.")
        return

    # Schedule recurring runs
    interval = args.interval
    schedule.every(interval).minutes.do(run_analysis)
    logger.info(f"Scheduler active — next run in {interval} minute(s). Press Ctrl+C to stop.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # check every 30 seconds
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
        print("\nAgent stopped. Goodbye!")


if __name__ == "__main__":
    main()
