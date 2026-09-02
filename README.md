An end-to-end ETL pipeline that automatically extracts daily stock market data, validates and enriches it with trading indicators, and loads it into MySQL.

Tech Stack: Python | MySQL | pandas | yfinance.

OVERVIEW:

This project automates a task that's normally manual and error-prone: pulling daily stock prices, cleaning them, and keeping a reliable historical record. It pulls OHLCV (Open, High, Low, Close, Volume) data for a configurable list of tickers from the Yahoo Finance API, validates every row against basic sanity rules, calculates trading indicators (returns, moving averages, volatility), and stores everything in a relational MySQL schema designed to be safe to re-run daily without creating duplicate data.

ARCHITECTURE: 

main.py  →  pipeline.py  →  data_source.py  →  transformer.py  →  db_manager.py  →  MySQL
(entry)     (orchestrator)   (EXTRACT)          (TRANSFORM)         (LOAD)

Each stage is a separate, single-responsibility module — the API integration, cleaning logic, and database logic don't know anything about each other beyond a simple function call, so any one piece can change independently.

Want to get started?
1. Clone the repo
2. Install dependencies
3. Set up the database
4. Create a dedicated MySQL user
   
     CREATE USER 'user_name'@'localhost' IDENTIFIED BY 'YourSecurePasswordHere';

     GRANT ALL PRIVILEGES ON market_data_db.* TO 'user_name'@'localhost';
     
     FLUSH PRIVILEGES;"
  
6. Configure your credentials:
    Edit config.py, or set these as environment variables:

    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
8. Run the pipeline(main.py)
9. View the analytics

Design:
Staging vs. curated tables — raw API data is preserved untouched for audit/reprocessing, separate from the validated table used for analysis.
Repeatable safety over re-inserting — a UNIQUE key on (ticker, trade_date) combined with ON DUPLICATE KEY UPDATE guarantees the pipeline can be safely re-run on a schedule without ever producing duplicate rows.
Rejected data is stored, not dropped — every row that fails validation is logged with a specific reason, so data quality issues are visible and reviewable instead of silently disappearing.
Per-ticker error isolation — a failure fetching or processing one ticker doesn't stop the rest of the batch from completing.



