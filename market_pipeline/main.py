"""
main.py
-------
Entry point for the Automated Financial Market Data Extraction Pipeline.
"""

import sys
import time

from src.pipeline import run_pipeline
from src.logger_config import get_logger

logger = get_logger(__name__)


def main():
    start = time.time()
    try:
        summary = run_pipeline()
    except Exception as exc: 
        logger.exception("Pipeline crashed before completion: %s", exc)
        sys.exit(1)

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(" PIPELINE RUN SUMMARY")
    print("=" * 60)
    print(f" Run ID              : {summary['run_id']}")
    print(f" Status              : {summary['status']}")
    print(f" Data source used    : {summary['data_source_used']}")
    print(f" Tickers processed   : {summary['tickers_processed']}")
    print(f" Tickers failed      : {summary['tickers_failed']}")
    print(f" Rows extracted      : {summary['rows_extracted']}")
    print(f" Rows inserted (new) : {summary['rows_inserted']}")
    print(f" Rows updated        : {summary['rows_updated']}")
    print(f" Rows rejected (DQ)  : {summary['rows_rejected']}")
    print(f" Elapsed time        : {elapsed:.2f}s")
    print("=" * 60)

    sys.exit(0 if summary["status"] in ("SUCCESS", "PARTIAL") else 1)


if __name__ == "__main__":
    main()
