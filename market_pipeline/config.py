"""
config.py
---------
Central configuration for the Automated Financial Market Data Extraction Pipeline.

Edit the values below (or override with environment variables) before running
the pipeline in your own environment.
"""

import os

# ----------------------------------------------------------------------------
# MySQL connection settings
# ----------------------------------------------------------------------------
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER", "pipeline_user"),
    "password": os.getenv("DB_PASSWORD", "PipelinePass@123"),
    "database": os.getenv("DB_NAME", "market_data_db"),
}

# ----------------------------------------------------------------------------
# Tickers to track
# ----------------------------------------------------------------------------
TICKERS = [
    {"ticker": "AAPL", "company_name": "Apple Inc.",      "sector": "Technology",  "exchange": "NASDAQ"},
    {"ticker": "MSFT", "company_name": "Microsoft Corp.",  "sector": "Technology",  "exchange": "NASDAQ"},
    {"ticker": "GOOGL","company_name": "Alphabet Inc.",    "sector": "Technology",  "exchange": "NASDAQ"},
    {"ticker": "AMZN", "company_name": "Amazon.com Inc.",  "sector": "Consumer Cyclical", "exchange": "NASDAQ"},
    {"ticker": "TSLA", "company_name": "Tesla Inc.",       "sector": "Automotive",  "exchange": "NASDAQ"},
]

# ----------------------------------------------------------------------------
# Extraction settings
# ----------------------------------------------------------------------------
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", 90))     # how many days of history to pull
REQUEST_RETRIES = 3                                      # retry attempts per ticker
RETRY_BACKOFF_SECONDS = 2                                 # base backoff, doubles each retry

# Data source mode: "auto" tries the live Yahoo Finance API first and falls
# back to the built-in simulator only if the API is unreachable (e.g. no
# internet, rate-limited, or a sandboxed/offline environment). Set to
# "live" to force the real API, or "simulate" to force synthetic data.
DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "auto")

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")
