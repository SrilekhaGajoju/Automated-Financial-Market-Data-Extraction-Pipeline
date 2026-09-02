"""
transformer.py
---------------
TRANSFORM layer of the pipeline.

Takes the raw OHLCV DataFrame from the extractor and:
  1. Validates each row (data-quality checks), separating good rows from bad.
  2. Cleans types and removes duplicate (ticker, date) rows.
  3. Computes derived analytics columns:
       - daily_return_pct  (percentage change vs previous close)
       - ma_5, ma_20       (5-day / 20-day simple moving averages)
       - volatility_10     (10-day rolling standard deviation of returns)
"""

import pandas as pd

from src.logger_config import get_logger

logger = get_logger(__name__)

REQUIRED_COLUMNS = [
    "ticker", "trade_date", "open_price", "high_price",
    "low_price", "close_price", "volume",
]


def validate_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Splits df into (valid_rows, issues) based on basic sanity checks."""
    issues = []
    valid_mask = pd.Series(True, index=df.index)

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Missing required column from extractor output: {col}")

    for idx, row in df.iterrows():
        reasons = []
        if pd.isna(row["open_price"]) or pd.isna(row["close_price"]):
            reasons.append("null OHLC value")
        if row.get("close_price", 0) <= 0 or row.get("open_price", 0) <= 0:
            reasons.append("non-positive price")
        if row.get("high_price", 0) < row.get("low_price", 0):
            reasons.append("high < low")
        if row.get("volume", 0) is not None and row.get("volume", 0) < 0:
            reasons.append("negative volume")

        if reasons:
            valid_mask.at[idx] = False
            issues.append({
                "ticker": row["ticker"],
                "trade_date": row["trade_date"],
                "issue_type": "validation_failed",
                "issue_detail": "; ".join(reasons),
            })

    valid_df = df[valid_mask].copy()
    return valid_df, issues


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate and normalise dtypes."""
    df = df.drop_duplicates(subset=["ticker", "trade_date"]).copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    numeric_cols = ["open_price", "high_price", "low_price", "close_price",
                     "adj_close_price", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values(["ticker", "trade_date"]).reset_index(drop=True)
    return df


def enrich_with_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds daily_return_pct, ma_5, ma_20, volatility_10 per ticker group."""
    df = df.copy()
    out_frames = []

    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("trade_date").copy()
        group["daily_return_pct"] = group["close_price"].pct_change() * 100
        group["ma_5"] = group["close_price"].rolling(window=5, min_periods=1).mean()
        group["ma_20"] = group["close_price"].rolling(window=20, min_periods=1).mean()
        group["volatility_10"] = (
            group["daily_return_pct"].rolling(window=10, min_periods=2).std()
        )
        out_frames.append(group)

    result = pd.concat(out_frames, ignore_index=True)
    result = result.round({
        "daily_return_pct": 4, "ma_5": 4, "ma_20": 4, "volatility_10": 4,
    })
    return result


def transform(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Full transform pipeline: validate -> clean -> enrich."""
    valid_df, issues = validate_rows(raw_df)
    if issues:
        logger.warning("Data quality: %d row(s) failed validation and were excluded.",
                        len(issues))
    if valid_df.empty:
        return valid_df, issues

    cleaned_df = clean(valid_df)
    enriched_df = enrich_with_indicators(cleaned_df)
    return enriched_df, issues
