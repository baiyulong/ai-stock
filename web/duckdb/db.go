package duckdb

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	_ "github.com/marcboeker/go-duckdb"
)

var DB *sql.DB

// Init 初始化 DuckDB 连接并建表
func Init(dbPath string) (*sql.DB, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("创建数据目录失败: %w", err)
	}

	db, err := sql.Open("duckdb", dbPath)
	if err != nil {
		return nil, fmt.Errorf("打开 DuckDB 失败: %w", err)
	}

	// 连接池配置：DuckDB 单写多读，写连接设为1
	db.SetMaxOpenConns(4)

	if err := createTables(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("建表失败: %w", err)
	}

	DB = db
	return db, nil
}

// createTables 创建所有表（IF NOT EXISTS）
func createTables(db *sql.DB) error {
	stmts := []string{
		// 日K线表
		`CREATE TABLE IF NOT EXISTS day_kline (
			code       VARCHAR,
			exchange   VARCHAR,
			date       DATE,
			open       DOUBLE,
			high       DOUBLE,
			low        DOUBLE,
			close      DOUBLE,
			volume     BIGINT,
			amount     DOUBLE,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (code, date)
		)`,
		// 股票基础信息表
		`CREATE TABLE IF NOT EXISTS stock_info (
			code      VARCHAR PRIMARY KEY,
			name      VARCHAR,
			exchange  VARCHAR,
			is_st     BOOLEAN DEFAULT false,
			is_etf    BOOLEAN DEFAULT false,
			decimal   INTEGER DEFAULT 2
		)`,
		// 选股结果快照表
		`CREATE TABLE IF NOT EXISTS screen_result (
			run_id              VARCHAR,
			run_at              TIMESTAMP,
			code                VARCHAR,
			name                VARCHAR,
			low_60              DOUBLE,
			low_prev40          DOUBLE,
			low_raise_pct       DOUBLE,
			high_100            DOUBLE,
			low_100             DOUBLE,
			last_close          DOUBLE,
			rebound_pct         DOUBLE,
			room_pct            DOUBLE,
			avg_amount_10       DOUBLE,
			avg_amount_100      DOUBLE,
			tier                VARCHAR,
			ma60_slope          DOUBLE,
			breakout_vol_ratio  DOUBLE,
			support_ok          BOOLEAN,
			volume_breakout_ok  BOOLEAN,
			ma_turn_ok          BOOLEAN,
			invalidated         BOOLEAN DEFAULT false,
			PRIMARY KEY (run_id, code)
		)`,
		// 数据同步进度表
		`CREATE TABLE IF NOT EXISTS sync_log (
			id          INTEGER PRIMARY KEY DEFAULT 1,
			status      VARCHAR,
			total       INTEGER,
			done        INTEGER,
			failed      INTEGER,
			started_at  TIMESTAMP,
			finished_at TIMESTAMP,
			error       VARCHAR
		)`,
	}

	for _, stmt := range stmts {
		if _, err := db.Exec(stmt); err != nil {
			return fmt.Errorf("执行建表语句失败: %w\nSQL: %s", err, stmt)
		}
	}

	return nil
}

// Close 关闭连接
func Close() {
	if DB != nil {
		DB.Close()
	}
}
