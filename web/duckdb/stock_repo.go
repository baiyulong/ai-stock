package duckdb

import (
	"database/sql"
	"fmt"
	"strings"
)

// StockInfo 股票基础信息
type StockInfo struct {
	Code     string
	Name     string
	Exchange string
	IsST     bool
	IsETF    bool
	Decimal  int
}

// UpsertStockInfos 批量写入股票基础信息（upsert，code 为主键）
func UpsertStockInfos(db *sql.DB, stocks []StockInfo) error {
	if len(stocks) == 0 {
		return nil
	}

	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("开启事务失败: %w", err)
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`
		INSERT INTO stock_info (code, name, exchange, is_st, is_etf, decimal)
		VALUES (?, ?, ?, ?, ?, ?)
		ON CONFLICT (code) DO UPDATE SET
			name = excluded.name,
			exchange = excluded.exchange,
			is_st = excluded.is_st,
			is_etf = excluded.is_etf,
			decimal = excluded.decimal
	`)
	if err != nil {
		return fmt.Errorf("预编译语句失败: %w", err)
	}
	defer stmt.Close()

	for _, s := range stocks {
		if _, err := stmt.Exec(s.Code, s.Name, s.Exchange, s.IsST, s.IsETF, s.Decimal); err != nil {
			return fmt.Errorf("插入失败 code=%s: %w", s.Code, err)
		}
	}

	return tx.Commit()
}

// GetAllStockCodes 获取所有个股代码（排除ETF、ST可选）
func GetAllStockCodes(db *sql.DB, excludeST bool) ([]string, error) {
	query := `SELECT code FROM stock_info WHERE is_etf = false`
	if excludeST {
		query += ` AND is_st = false`
	}
	query += ` ORDER BY code`

	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, rows.Err()
}

// GetSTCodes 获取所有ST股票代码
func GetSTCodes(db *sql.DB) ([]string, error) {
	rows, err := db.Query(`SELECT code FROM stock_info WHERE is_st = true`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, rows.Err()
}

// IsSTName 判断名称是否为ST股
func IsSTName(name string) bool {
	upper := strings.ToUpper(name)
	return strings.Contains(upper, "ST")
}
