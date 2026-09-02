"""
analysis_report.py
-------------------
Demonstrates the *value* of having clean market data sitting in MySQL:
runs a few analytical SQL queries directly against the curated
stock_prices table and prints a readable report.

Run this AFTER main.py has populated the database at least once.


"""

from src.db_manager import DBManager


def section(title: str):
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


def main():
    with DBManager() as db:

        section("1. Latest closing price & daily return per ticker")
        rows = db.query("""
            SELECT sp.ticker, c.company_name, sp.trade_date,
                   sp.close_price, sp.daily_return_pct
            FROM stock_prices sp
            JOIN companies c ON c.ticker = sp.ticker
            JOIN (
                SELECT ticker, MAX(trade_date) AS max_date
                FROM stock_prices GROUP BY ticker
            ) latest ON latest.ticker = sp.ticker AND latest.max_date = sp.trade_date
            ORDER BY sp.daily_return_pct DESC
        """)
        for r in rows:
            print(f"  {r['ticker']:<6} {r['company_name']:<20} "
                  f"close={r['close_price']:>10} return={r['daily_return_pct']:>7}%")

        section("2. Top gainer & top loser (most recent trading day)")
        top = rows[0]
        bottom = rows[-1]
        print(f"  Top gainer : {top['ticker']} ({top['daily_return_pct']}%)")
        print(f"  Top loser  : {bottom['ticker']} ({bottom['daily_return_pct']}%)")

        section("3. 20-day trend signal (price vs its own 20-day moving average)")
        rows = db.query("""
            SELECT ticker, trade_date, close_price, ma_20,
                   ROUND(close_price - ma_20, 4) AS gap_vs_ma20
            FROM stock_prices sp
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_prices s2 WHERE s2.ticker = sp.ticker)
            ORDER BY gap_vs_ma20 DESC
        """)
        for r in rows:
            trend = "ABOVE MA20 (bullish)" if r["gap_vs_ma20"] and r["gap_vs_ma20"] > 0 else "BELOW MA20 (bearish)"
            print(f"  {r['ticker']:<6} close={r['close_price']:>10} ma_20={r['ma_20']:>10} -> {trend}")

        section("4. Most volatile ticker (10-day rolling volatility, latest reading)")
        rows = db.query("""
            SELECT ticker, trade_date, volatility_10
            FROM stock_prices sp
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_prices s2 WHERE s2.ticker = sp.ticker)
              AND volatility_10 IS NOT NULL
            ORDER BY volatility_10 DESC
            LIMIT 3
        """)
        for r in rows:
            print(f"  {r['ticker']:<6} volatility_10={r['volatility_10']}")

        section("5. Pipeline run history (operational audit trail)")
        rows = db.query("""
            SELECT run_id, started_at, status, data_source,
                   rows_extracted, rows_inserted, rows_updated, rows_rejected
            FROM pipeline_run_log ORDER BY run_id DESC LIMIT 5
        """)
        for r in rows:
            print(f"  Run #{r['run_id']:<3} {str(r['started_at']):<20} status={r['status']:<8} "
                  f"source={r['data_source']:<10} extracted={r['rows_extracted']:<5} "
                  f"inserted={r['rows_inserted']:<5} updated={r['rows_updated']:<5} "
                  f"rejected={r['rows_rejected']}")

        print("\n")


if __name__ == "__main__":
    main()
