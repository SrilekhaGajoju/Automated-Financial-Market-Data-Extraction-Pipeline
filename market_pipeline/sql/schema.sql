-- ============================================================================
-- Automated Financial Market Data Extraction Pipeline
-- Database Schema (MySQL 8.0+)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS market_data_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE market_data_db;

-- ----------------------------------------------------------------------------
-- 1. COMPANIES : master/reference table for tracked tickers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id      INT AUTO_INCREMENT PRIMARY KEY,
    ticker          VARCHAR(15)  NOT NULL UNIQUE,
    company_name    VARCHAR(150) NOT NULL,
    sector          VARCHAR(100) DEFAULT 'Unknown',
    exchange        VARCHAR(50)  DEFAULT 'NASDAQ',
    is_active       TINYINT(1)   DEFAULT 1,
    added_on        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 2. STOCK_PRICES_RAW : staging/landing layer - exact copy of what the
--    extractor pulled, before any cleaning. Kept for audit & reprocessing.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices_raw (
    raw_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker          VARCHAR(15) NOT NULL,
    trade_date      DATE NOT NULL,
    open_price      DECIMAL(12,4),
    high_price      DECIMAL(12,4),
    low_price       DECIMAL(12,4),
    close_price     DECIMAL(12,4),
    adj_close_price DECIMAL(12,4),
    volume          BIGINT,
    source          VARCHAR(30) DEFAULT 'yfinance',
    extracted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_raw_ticker_date (ticker, trade_date)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 3. STOCK_PRICES : curated / analytics-ready layer.
--    One row per (ticker, trade_date) -- upserted, deduplicated, with
--    derived indicators computed during the transform stage.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices (
    price_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker          VARCHAR(15) NOT NULL,
    trade_date      DATE NOT NULL,
    open_price      DECIMAL(12,4) NOT NULL,
    high_price      DECIMAL(12,4) NOT NULL,
    low_price       DECIMAL(12,4) NOT NULL,
    close_price     DECIMAL(12,4) NOT NULL,
    adj_close_price DECIMAL(12,4),
    volume          BIGINT,
    daily_return_pct DECIMAL(8,4)  COMMENT 'percent change vs previous close',
    ma_5            DECIMAL(12,4) COMMENT '5-day simple moving average',
    ma_20           DECIMAL(12,4) COMMENT '20-day simple moving average',
    volatility_10   DECIMAL(8,4)  COMMENT '10-day rolling std-dev of returns',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticker_date (ticker, trade_date),
    INDEX idx_price_ticker (ticker),
    INDEX idx_price_date (trade_date)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 4. PIPELINE_RUN_LOG : operational audit trail for every pipeline execution
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id          INT AUTO_INCREMENT PRIMARY KEY,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP NULL,
    status          ENUM('RUNNING','SUCCESS','PARTIAL','FAILED') DEFAULT 'RUNNING',
    tickers_requested INT DEFAULT 0,
    rows_extracted  INT DEFAULT 0,
    rows_inserted   INT DEFAULT 0,
    rows_updated    INT DEFAULT 0,
    rows_rejected   INT DEFAULT 0,
    data_source     VARCHAR(30),
    error_message   TEXT
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 5. DATA_QUALITY_ISSUES : rows that failed validation, kept for review
--    instead of being silently dropped
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT,
    ticker          VARCHAR(15),
    trade_date      DATE,
    issue_type      VARCHAR(100),
    issue_detail    VARCHAR(255),
    logged_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES pipeline_run_log(run_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- one row per ticker, showing its latest price, return, trend, and volatility
CREATE OR REPLACE VIEW vw_latest_snapshot AS
SELECT
    sp.ticker,
    c.company_name,
    sp.trade_date,
    sp.close_price,
    sp.daily_return_pct,
    sp.ma_20,
    ROUND(sp.close_price - sp.ma_20, 4) AS gap_vs_ma20,
    CASE WHEN sp.close_price > sp.ma_20 THEN 'Bullish' ELSE 'Bearish' END AS trend,
    sp.volatility_10
FROM stock_prices sp
JOIN companies c ON c.ticker = sp.ticker
WHERE sp.trade_date = (
    SELECT MAX(trade_date) FROM stock_prices s2 WHERE s2.ticker = sp.ticker
);
