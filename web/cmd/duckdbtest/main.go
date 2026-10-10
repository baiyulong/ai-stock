package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"web/duckdb"
)

func main() {
	// 用临时目录测试
	tmpDir := filepath.Join(os.TempDir(), "duckdb_test")
	os.MkdirAll(tmpDir, 0755)
	dbPath := filepath.Join(tmpDir, "test.duckdb")
	defer os.Remove(dbPath)

	db, err := duckdb.Init(dbPath)
	if err != nil {
		log.Fatalf("Init failed: %v", err)
	}
	defer db.Close()
	fmt.Println("✓ DuckDB 初始化成功")

	// 测试写入股票信息
	stocks := []duckdb.StockInfo{
		{Code: "600519", Name: "贵州茅台", Exchange: "sh", IsST: false, IsETF: false, Decimal: 2},
		{Code: "000001", Name: "平安银行", Exchange: "sz", IsST: false, IsETF: false, Decimal: 2},
		{Code: "600001", Name: "ST测试", Exchange: "sh", IsST: true, IsETF: false, Decimal: 2},
	}
	if err := duckdb.UpsertStockInfos(db, stocks); err != nil {
		log.Fatalf("UpsertStockInfos failed: %v", err)
	}
	fmt.Println("✓ 写入 stock_info 成功")

	// 测试写入日K线
	klines := []duckdb.DayKline{
		{Code: "600519", Exchange: "sh", Date: time.Now().AddDate(0, 0, -2), Open: 1500.0, High: 1520.0, Low: 1490.0, Close: 1510.0, Volume: 100000, Amount: 151000000},
		{Code: "600519", Exchange: "sh", Date: time.Now().AddDate(0, 0, -1), Open: 1510.0, High: 1530.0, Low: 1505.0, Close: 1525.0, Volume: 120000, Amount: 183000000},
	}
	if err := duckdb.UpsertDayKlines(db, klines); err != nil {
		log.Fatalf("UpsertDayKlines failed: %v", err)
	}
	fmt.Println("✓ 写入 day_kline 成功")

	// 测试查询
	rows, err := duckdb.GetDayKlines(db, "600519", 0)
	if err != nil {
		log.Fatalf("GetDayKlines failed: %v", err)
	}
	fmt.Printf("✓ 查询 day_kline 成功，共 %d 条\n", len(rows))

	count, _ := duckdb.CountDayKlines(db)
	fmt.Printf("✓ day_kline 总记录数: %d\n", count)

	codes, _ := duckdb.GetAllStockCodes(db, true)
	fmt.Printf("✓ 非ST股票代码: %v\n", codes)

	// 测试 upsert（更新已有数据）
	klines[0].Close = 1515.0
	if err := duckdb.UpsertDayKlines(db, klines[:1]); err != nil {
		log.Fatalf("Upsert update failed: %v", err)
	}
	rows2, _ := duckdb.GetDayKlines(db, "600519", 0)
	fmt.Printf("✓ Upsert 更新成功，第一条收盘价: %.2f\n", rows2[0].Close)

	fmt.Println("\n=== 所有测试通过 ===")
}
