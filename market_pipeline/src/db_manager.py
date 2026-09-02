"""
db_manager.py
-------------
LOAD layer of the pipeline. Wraps every MySQL interaction: connecting,
upserting curated rows, appending raw rows, recording pipeline run metadata,
and logging data-quality issues.

Uses mysql-connector-python with parameterised queries throughout (never
string-formatted SQL) to prevent SQL injection.
"""

import mysql.connector
from mysql.connector import Error as MySQLError

import config
from src.logger_config import get_logger

logger = get_logger(__name__)


class DBManager:
    def __init__(self):
        self.conn = None

    # -- connection lifecycle -------------------------------------------------
    def connect(self):
        try:
            self.conn = mysql.connector.connect(**config.DB_CONFIG)
            logger.info("Connected to MySQL database '%s' at %s:%s",
                        config.DB_CONFIG["database"],
                        config.DB_CONFIG["host"], config.DB_CONFIG["port"])
        except MySQLError as exc:
            logger.error("Could not connect to MySQL: %s", exc)
            raise

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            logger.info("MySQL connection closed.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -- reference data ---------------------------------------------------------
    def upsert_company(self, ticker: str, company_name: str, sector: str, exchange: str):
        sql = """
            INSERT INTO companies (ticker, company_name, sector, exchange)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                company_name = VALUES(company_name),
                sector = VALUES(sector),
                exchange = VALUES(exchange)
        """
        cur = self.conn.cursor()
        cur.execute(sql, (ticker, company_name, sector, exchange))
        self.conn.commit()
        cur.close()

    # -- raw / staging layer ------------------------------------------------
    def insert_raw(self, df, source: str) -> int:
        if df.empty:
            return 0
        sql = """
            INSERT INTO stock_prices_raw
                (ticker, trade_date, open_price, high_price, low_price,
                 close_price, adj_close_price, volume, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        rows = [
            (r.ticker, r.trade_date, r.open_price, r.high_price, r.low_price,
             r.close_price, r.adj_close_price, int(r.volume) if r.volume == r.volume else None, source)
            for r in df.itertuples(index=False)
        ]
        cur = self.conn.cursor()
        cur.executemany(sql, rows)
        self.conn.commit()
        n = cur.rowcount
        cur.close()
        return n

    # -- curated layer (idempotent upsert) -----------------------------------
    def upsert_prices(self, df) -> tuple[int, int]:
        """
        Inserts new (ticker, trade_date) rows or updates them if they already
        exist (re-running the pipeline for the same date range is therefore
        safe and produces no duplicates).
        Returns (rows_inserted, rows_updated) based on MySQL's affected-rows
        semantics for ON DUPLICATE KEY UPDATE (1 = insert, 2 = update).
        """
        if df.empty:
            return 0, 0

        sql = """
            INSERT INTO stock_prices
                (ticker, trade_date, open_price, high_price, low_price,
                 close_price, adj_close_price, volume,
                 daily_return_pct, ma_5, ma_20, volatility_10)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_price = VALUES(close_price),
                adj_close_price = VALUES(adj_close_price),
                volume = VALUES(volume),
                daily_return_pct = VALUES(daily_return_pct),
                ma_5 = VALUES(ma_5),
                ma_20 = VALUES(ma_20),
                volatility_10 = VALUES(volatility_10)
        """

        def clean_num(v):
            if v is None:
                return None
            try:
                if v != v:  # NaN check
                    return None
            except TypeError:
                pass
            return v

        cur = self.conn.cursor()
        inserted, updated = 0, 0
        for r in df.itertuples(index=False):
            params = (
                r.ticker, r.trade_date, r.open_price, r.high_price, r.low_price,
                r.close_price, r.adj_close_price,
                int(r.volume) if r.volume == r.volume else None,
                clean_num(r.daily_return_pct), clean_num(r.ma_5),
                clean_num(r.ma_20), clean_num(r.volatility_10),
            )
            cur.execute(sql, params)
            # MySQL reports 1 for a plain insert, 2 for an update-via-duplicate
            if cur.rowcount == 1:
                inserted += 1
            elif cur.rowcount == 2:
                updated += 1
        self.conn.commit()
        cur.close()
        return inserted, updated

    # -- data quality -----------------------------------------------------------
    def log_issues(self, run_id: int, issues: list[dict]):
        if not issues:
            return
        sql = """
            INSERT INTO data_quality_issues
                (run_id, ticker, trade_date, issue_type, issue_detail)
            VALUES (%s, %s, %s, %s, %s)
        """
        rows = [(run_id, i["ticker"], i["trade_date"], i["issue_type"], i["issue_detail"])
                for i in issues]
        cur = self.conn.cursor()
        cur.executemany(sql, rows)
        self.conn.commit()
        cur.close()

    # -- run/audit log -----------------------------------------------------------
    def start_run(self, tickers_requested: int, data_source: str) -> int:
        sql = """
            INSERT INTO pipeline_run_log (tickers_requested, data_source, status)
            VALUES (%s, %s, 'RUNNING')
        """
        cur = self.conn.cursor()
        cur.execute(sql, (tickers_requested, data_source))
        self.conn.commit()
        run_id = cur.lastrowid
        cur.close()
        return run_id

    def finish_run(self, run_id: int, status: str, rows_extracted: int,
                    rows_inserted: int, rows_updated: int, rows_rejected: int,
                    error_message: str = None):
        sql = """
            UPDATE pipeline_run_log
            SET finished_at = CURRENT_TIMESTAMP,
                status = %s,
                rows_extracted = %s,
                rows_inserted = %s,
                rows_updated = %s,
                rows_rejected = %s,
                error_message = %s
            WHERE run_id = %s
        """
        cur = self.conn.cursor()
        cur.execute(sql, (status, rows_extracted, rows_inserted, rows_updated,
                           rows_rejected, error_message, run_id))
        self.conn.commit()
        cur.close()

    
    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
