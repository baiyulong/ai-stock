package duckdb

import (
	"database/sql"
	"fmt"
	"time"
)

// DayKline 日K线记录（价格单位：元；成交额单位：元）
type DayKline struct {
	Code     string
	Exchange string
	Date     time.Time
	Open     float64
	High     float64
	Low      float64
	Close    float64
	Volume   int64
	Amount   float64
}

// UpsertDayKlines 批量插入/更新日K线
// 使用 DuckDB 的 prepared statement 批量执行
func UpsertDayKlines(db *sql.DB, rows []DayKline) error {
	if len(rows) == 0 {
		return nil
	}

	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("开启事务失败: %w", err)
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`
		INSERT INTO day_kline (code, exchange, date, open, high, low, close, volume, amount, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT (code, date) DO UPDATE SET
			open = excluded.open,
			high = excluded.high,
			low = excluded.low,
			close = excluded.close,
			volume = excluded.volume,
			amount = excluded.amount,
			updated_at = excluded.updated_at
	`)
	if err != nil {
		return fmt.Errorf("预编译语句失败: %w", err)
	}
	defer stmt.Close()

	now := time.Now()
	for _, r := range rows {
		if _, err := stmt.Exec(
			r.Code, r.Exchange, r.Date,
			r.Open, r.High, r.Low, r.Close,
			r.Volume, r.Amount, now,
		); err != nil {
			return fmt.Errorf("插入失败 code=%s date=%s: %w", r.Code, r.Date.Format("2006-01-02"), err)
		}
	}

	return tx.Commit()
}

// GetLastDate 获取某只股票在 DuckDB 中的最新日期（用于增量同步）
func GetLastDate(db *sql.DB, code string) (time.Time, error) {
	var date sql.NullTime
	err := db.QueryRow(`SELECT MAX(date) FROM day_kline WHERE code = ?`, code).Scan(&date)
	if err != nil {
		return time.Time{}, err
	}
	if !date.Valid {
		return time.Time{}, nil // 无数据
	}
	return date.Time, nil
}

// GetDayKlines 查询某只股票的日K线（按日期升序）
func GetDayKlines(db *sql.DB, code string, limit int) ([]DayKline, error) {
	query := `SELECT code, exchange, date, open, high, low, close, volume, amount
		FROM day_kline WHERE code = ? ORDER BY date ASC`
	if limit > 0 {
		query += fmt.Sprintf(" LIMIT %d", limit)
	}

	rows, err := db.Query(query, code)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []DayKline
	for rows.Next() {
		var k DayKline
		if err := rows.Scan(&k.Code, &k.Exchange, &k.Date, &k.Open, &k.High, &k.Low, &k.Close, &k.Volume, &k.Amount); err != nil {
			return nil, err
		}
		result = append(result, k)
	}
	return result, rows.Err()
}

// CountDayKlines 统计总记录数
func CountDayKlines(db *sql.DB) (int64, error) {
	var count int64
	err := db.QueryRow(`SELECT COUNT(*) FROM day_kline`).Scan(&count)
	return count, err
}

// CountDistinctCodes 统计有K线数据的股票数
func CountDistinctCodes(db *sql.DB) (int64, error) {
	var count int64
	err := db.QueryRow(`SELECT COUNT(DISTINCT code) FROM day_kline`).Scan(&count)
	return count, err
}
