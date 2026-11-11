PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candles (
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    ts          TEXT NOT NULL,     -- ISO8601 UTC
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    tick_volume INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    direction   TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss   REAL NOT NULL,
    take_profit REAL NOT NULL,
    score       REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER REFERENCES signals(id),
    strategy_id TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    direction   TEXT NOT NULL,
    volume      REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price  REAL,
    stop_loss   REAL NOT NULL,
    take_profit REAL NOT NULL,
    opened_at   TEXT NOT NULL,
    closed_at   TEXT,
    pnl         REAL,
    status      TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS experiments (
    id           TEXT PRIMARY KEY,
    phase        TEXT NOT NULL,
    config_json  TEXT NOT NULL,
    code_version TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL,
    source     TEXT NOT NULL,
    message    TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));