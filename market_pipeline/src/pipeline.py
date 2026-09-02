"""
pipeline.py
-----------
Orchestrates the full Extract -> Transform -> Load flow for every
configured ticker, with per-ticker error isolation (one bad ticker
does not crash the whole run) and a full audit trail written to
pipeline_run_log / data_quality_issues.
"""

import pandas as pd

import config
from src.data_source import fetch_price_history, DataSourceError
from src.transformer import transform
from src.db_manager import DBManager
from src.logger_config import get_logger

logger = get_logger(__name__)


def run_pipeline() -> dict:
    tickers = config.TICKERS
    summary = {
        "tickers_processed": 0,
        "tickers_failed": 0,
        "rows_extracted": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_rejected": 0,
        "data_source_used": set(),
    }

    with DBManager() as db:
        run_id = db.start_run(tickers_requested=len(tickers), data_source=config.DATA_SOURCE_MODE)
        logger.info("=== Pipeline run #%d started for %d ticker(s) ===", run_id, len(tickers))

        overall_status = "SUCCESS"
        last_error = None

        for t in tickers:
            ticker = t["ticker"]
            try:
                logger.info("[%s] Registering company metadata...", ticker)
                db.upsert_company(ticker, t["company_name"], t["sector"], t["exchange"])

                logger.info("[%s] Extracting last %d days of price history...",
                            ticker, config.LOOKBACK_DAYS)
                raw_df, source_used = fetch_price_history(ticker)
                summary["data_source_used"].add(source_used)
                summary["rows_extracted"] += len(raw_df)
                logger.info("[%s] Extracted %d raw rows from source='%s'",
                            ticker, len(raw_df), source_used)

                db.insert_raw(raw_df, source_used)

                logger.info("[%s] Transforming (validate -> clean -> enrich)...", ticker)
                clean_df, issues = transform(raw_df)
                if issues:
                    db.log_issues(run_id, issues)
                    summary["rows_rejected"] += len(issues)

                logger.info("[%s] Loading %d curated rows into stock_prices...",
                            ticker, len(clean_df))
                inserted, updated = db.upsert_prices(clean_df)
                summary["rows_inserted"] += inserted
                summary["rows_updated"] += updated
                summary["tickers_processed"] += 1

                logger.info("[%s] Done. inserted=%d updated=%d rejected=%d",
                            ticker, inserted, updated, len(issues))

            except DataSourceError as exc:
                logger.error("[%s] Extraction failed permanently: %s", ticker, exc)
                summary["tickers_failed"] += 1
                overall_status = "PARTIAL"
                last_error = str(exc)
            except Exception as exc:  # isolate per-ticker failures
                logger.exception("[%s] Unexpected error, skipping ticker: %s", ticker, exc)
                summary["tickers_failed"] += 1
                overall_status = "PARTIAL"
                last_error = str(exc)

        if summary["tickers_processed"] == 0:
            overall_status = "FAILED"

        db.finish_run(
            run_id, overall_status,
            summary["rows_extracted"], summary["rows_inserted"],
            summary["rows_updated"], summary["rows_rejected"],
            last_error,
        )
        logger.info(
            "=== Pipeline run #%d finished: status=%s processed=%d failed=%d "
            "inserted=%d updated=%d rejected=%d ===",
            run_id, overall_status, summary["tickers_processed"], summary["tickers_failed"],
            summary["rows_inserted"], summary["rows_updated"], summary["rows_rejected"],
        )

    summary["run_id"] = run_id
    summary["status"] = overall_status
    summary["data_source_used"] = ", ".join(sorted(summary["data_source_used"]))
    return summary
