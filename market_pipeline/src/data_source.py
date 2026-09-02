"""
data_source.py
---------------
EXTRACT layer of the pipeline.

Provides a single function, fetch_price_history(), that returns a pandas
DataFrame of OHLCV data for a ticker, regardless of where the data actually
came from. Two backends are implemented:

  1. YahooFinanceSource   - pulls real, live data via the `yfinance` package.
                             This is what you will use on your own machine.
  2. SimulatedMarketSource - generates statistically realistic synthetic
                             OHLCV data (seeded random walk). This is used
                             automatically as a fallback when the live API
                             cannot be reached (no internet, firewalled
                             sandbox, rate limiting, etc.) so the rest of the
                             pipeline can still be built, tested and
                             demonstrated end-to-end.

DATA_SOURCE_MODE in config.py controls this:
    "live"     -> always use Yahoo Finance, raise on failure
    "simulate" -> always use the synthetic generator
    "auto"     -> try Yahoo Finance first, fall back to synthetic on failure
"""

import time
import datetime as dt
import hashlib

import numpy as np
import pandas as pd
import yfinance as yf

import config
from src.logger_config import get_logger

logger = get_logger(__name__)


class DataSourceError(Exception):
    """Raised when a data source cannot supply data after all retries."""


# ----------------------------------------------------------------------------
# 1. LIVE SOURCE — Yahoo Finance via yfinance
# ----------------------------------------------------------------------------
class YahooFinanceSource:
    name = "yfinance"

    def fetch(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        end = dt.date.today()
        start = end - dt.timedelta(days=lookback_days)

        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=False,
        )
        if df is None or df.empty:
            raise DataSourceError(f"No data returned by Yahoo Finance for {ticker}")

        # yfinance can return a MultiIndex column header for a single ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        df = df.reset_index().rename(columns={
            "Date": "trade_date",
            "Open": "open_price",
            "High": "high_price",
            "Low": "low_price",
            "Close": "close_price",
            "Adj Close": "adj_close_price",
            "Volume": "volume",
        })
        df["ticker"] = ticker
        return df[["ticker", "trade_date", "open_price", "high_price",
                   "low_price", "close_price", "adj_close_price", "volume"]]


# ----------------------------------------------------------------------------
# 2. FALLBACK SOURCE — deterministic synthetic OHLCV generator
# ----------------------------------------------------------------------------
class SimulatedMarketSource:
    """
    Generates realistic-looking daily OHLCV bars using a seeded geometric
    random walk, so results are reproducible per ticker/day but still look
    like genuine market data (positive price, sensible High >= Close/Open
    >= Low, volume that varies with volatility).

    This is clearly a *substitute* for a live feed and is only used when
    the real API is unreachable, exactly as an engineering team would build
    a fallback/mocked data source for offline development and CI testing.
    """

    name = "simulated"

    def fetch(self, ticker: str, lookback_days: int) -> pd.DataFrame:
        seed = int(hashlib.sha256(ticker.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)

        end = dt.date.today()
        dates = pd.bdate_range(end=end, periods=lookback_days)  # business days only

        base_price = 50 + (seed % 400)          # spread starting prices out
        daily_drift = rng.normal(0.0004, 0.02, len(dates))       # ~ daily returns
        close_prices = base_price * np.cumprod(1 + daily_drift)

        rows = []
        prev_close = close_prices[0] / (1 + daily_drift[0])
        for d, close, ret in zip(dates, close_prices, daily_drift):
            open_p = prev_close * (1 + rng.normal(0, 0.003))
            high_p = max(open_p, close) * (1 + abs(rng.normal(0, 0.006)))
            low_p = min(open_p, close) * (1 - abs(rng.normal(0, 0.006)))
            volume = int(abs(rng.normal(5_000_000, 1_500_000)) * (1 + abs(ret) * 10))
            rows.append({
                "ticker": ticker,
                "trade_date": d.date(),
                "open_price": round(open_p, 4),
                "high_price": round(high_p, 4),
                "low_price": round(low_p, 4),
                "close_price": round(close, 4),
                "adj_close_price": round(close, 4),
                "volume": volume,
            })
            prev_close = close

        return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Public entry point used by the pipeline
# ----------------------------------------------------------------------------
def fetch_price_history(ticker: str, lookback_days: int = None) -> tuple[pd.DataFrame, str]:
    """
    Returns (dataframe, source_name_used).
    Retries the live source with exponential backoff before falling back
    (when mode == "auto") to the simulator.
    """
    lookback_days = lookback_days or config.LOOKBACK_DAYS
    mode = config.DATA_SOURCE_MODE

    if mode == "simulate":
        return SimulatedMarketSource().fetch(ticker, lookback_days), "simulated"

    last_error = None
    if mode in ("live", "auto"):
        source = YahooFinanceSource()
        for attempt in range(1, config.REQUEST_RETRIES + 1):
            try:
                df = source.fetch(ticker, lookback_days)
                return df, source.name
            except Exception as exc:  
                last_error = exc
                wait = config.RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "[%s] live fetch attempt %d/%d failed (%s). Retrying in %ds...",
                    ticker, attempt, config.REQUEST_RETRIES, exc, wait,
                )
                time.sleep(wait)

        if mode == "live":
            raise DataSourceError(
                f"Live data source failed for {ticker} after "
                f"{config.REQUEST_RETRIES} attempts: {last_error}"
            )

        logger.warning(
            "[%s] Live Yahoo Finance API unreachable after %d attempts (%s). "
            "Falling back to simulated data source.",
            ticker, config.REQUEST_RETRIES, last_error,
        )

    return SimulatedMarketSource().fetch(ticker, lookback_days), "simulated"
