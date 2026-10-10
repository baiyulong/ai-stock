package screener

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/injoyai/tdx"
	"github.com/injoyai/tdx/protocol"
	"web/duckdb"
)

// SyncConfig 数据同步配置
type SyncConfig struct {
	Codes       []string // 指定股票代码，为空则全量
	Concurrency int      // 并发数，默认 8
	Lookback    int      // 拉取最近 N 个交易日，默认 130
	Incremental bool     // 是否增量更新（只拉 DuckDB 中已有最新日期之后的数据）
}

// SyncStatus 同步进度
type SyncStatus struct {
	Status    string `json:"status"`     // running / success / failed
	Total     int    `json:"total"`      // 总股票数
	Done      int    `json:"done"`       // 已完成数
	Failed    int    `json:"failed"`     // 失败数
	StartedAt string `json:"started_at"` // 开始时间
	FinishedAt string `json:"finished_at,omitempty"`
	Error     string `json:"error,omitempty"`
}

var (
	currentSyncStatus *SyncStatus
	syncMu            sync.RWMutex
)

// GetSyncStatus 获取当前同步状态
func GetSyncStatus() *SyncStatus {
	syncMu.RLock()
	defer syncMu.RUnlock()
	if currentSyncStatus == nil {
		return &SyncStatus{Status: "idle"}
	}
	// 返回副本
	s := *currentSyncStatus
	return &s
}

// setSyncStatus 更新同步状态
func setSyncStatus(s *SyncStatus) {
	syncMu.Lock()
	defer syncMu.Unlock()
	currentSyncStatus = s
}

// SyncMarketData 执行市场数据同步（拉取日K入 DuckDB）
// mgr 为连接池（优先），fallbackClient 为单连接降级
func SyncMarketData(ctx context.Context, mgr *tdx.Manage, fallbackClient *tdx.Client, cfg SyncConfig) error {
	if cfg.Concurrency <= 0 {
		cfg.Concurrency = 8
	}
	if cfg.Lookback <= 0 {
		cfg.Lookback = 130
	}

	// 1. 获取股票列表
	codes := cfg.Codes
	if len(codes) == 0 {
		codes = getStockCodes()
	}
	if len(codes) == 0 {
		return fmt.Errorf("股票代码列表为空")
	}

	// 2. 写入股票基础信息
	if err := syncStockInfo(); err != nil {
		log.Printf("写入股票基础信息失败: %v", err)
	}

	// 3. 初始化状态
	status := &SyncStatus{
		Status:    "running",
		Total:     len(codes),
		Done:      0,
		Failed:    0,
		StartedAt: time.Now().Format("2006-01-02 15:04:05"),
	}
	setSyncStatus(status)

	var doneCount int64
	var failedCount int64
	var failedCodes []string
	var failedMu sync.Mutex

	// 4. 并发拉取
	sem := make(chan struct{}, cfg.Concurrency)
	var wg sync.WaitGroup

	for _, code := range codes {
		select {
		case <-ctx.Done():
			status.Status = "cancelled"
			status.FinishedAt = time.Now().Format("2006-01-02 15:04:05")
			setSyncStatus(status)
			return ctx.Err()
		default:
		}

		wg.Add(1)
		sem <- struct{}{}
		go func(code string) {
			defer wg.Done()
			defer func() { <-sem }()

			if err := syncOneStock(ctx, mgr, fallbackClient, code, cfg); err != nil {
				atomic.AddInt64(&failedCount, 1)
				failedMu.Lock()
				failedCodes = append(failedCodes, code)
				failedMu.Unlock()
				log.Printf("同步 %s 失败: %v", code, err)
			}
			atomic.AddInt64(&doneCount, 1)

			// 每 100 只更新一次状态
			if atomic.LoadInt64(&doneCount)%100 == 0 {
				syncMu.Lock()
				status.Done = int(atomic.LoadInt64(&doneCount))
				status.Failed = int(atomic.LoadInt64(&failedCount))
				syncMu.Unlock()
			}
		}(code)
	}

	wg.Wait()

	// 5. 更新最终状态
	syncMu.Lock()
	status.Done = int(atomic.LoadInt64(&doneCount))
	status.Failed = int(atomic.LoadInt64(&failedCount))
	status.FinishedAt = time.Now().Format("2006-01-02 15:04:05")
	if len(failedCodes) > 0 {
		status.Status = "partial"
		status.Error = fmt.Sprintf("失败 %d 只: %s", len(failedCodes), strings.Join(failedCodes[:min(10, len(failedCodes))], ","))
	} else {
		status.Status = "success"
	}
	syncMu.Unlock()
	setSyncStatus(status)

	log.Printf("数据同步完成: 成功 %d, 失败 %d, 总 %d", status.Done-status.Failed, status.Failed, status.Total)
	return nil
}

// syncOneStock 同步单只股票的日K数据
func syncOneStock(ctx context.Context, mgr *tdx.Manage, fallbackClient *tdx.Client, code string, cfg SyncConfig) error {
	// 增量更新：查 DuckDB 中已有最新日期
	var lastDate time.Time
	if cfg.Incremental && duckdb.DB != nil {
		d, err := duckdb.GetLastDate(duckdb.DB, code)
		if err == nil && !d.IsZero() {
			lastDate = d
		}
	}

	// 从 TDX 拉取日K（优先用连接池，降级用单连接）
	var resp *protocol.KlineResp
	var err error
	pullFn := func(c *tdx.Client) error {
		count := 0
		resp, err = c.GetKlineDayUntil(code, func(k *protocol.Kline) bool {
			// 增量模式：遇到已存在日期之前的数据就停
			if cfg.Incremental && !lastDate.IsZero() && k.Time.Before(lastDate) {
				return true
			}
			count++
			return count > cfg.Lookback
		})
		return err
	}

	if mgr != nil {
		err = mgr.Do(pullFn)
	} else if fallbackClient != nil {
		err = pullFn(fallbackClient)
	} else {
		return fmt.Errorf("无可用的 TDX 连接")
	}
	if err != nil {
		return fmt.Errorf("拉取K线失败: %w", err)
	}
	if resp == nil || len(resp.List) == 0 {
		return fmt.Errorf("K线数据为空")
	}

	// 转换为 DuckDB 格式（价格÷1000 转元，成交额÷1000 转元）
	exchange := getExchange(code)
	rows := make([]duckdb.DayKline, 0, len(resp.List))
	for _, k := range resp.List {
		// 跳过无效数据
		if k.Close == 0 || k.Time.IsZero() {
			continue
		}
		rows = append(rows, duckdb.DayKline{
			Code:     code,
			Exchange: exchange,
			Date:     k.Time,
			Open:     float64(k.Open) / 1000,
			High:     float64(k.High) / 1000,
			Low:      float64(k.Low) / 1000,
			Close:    float64(k.Close) / 1000,
			Volume:   k.Volume,
			Amount:   float64(k.Amount) / 1000,
		})
	}

	if len(rows) == 0 {
		return fmt.Errorf("转换后无有效数据")
	}

	// 批量写入 DuckDB
	if err := duckdb.UpsertDayKlines(duckdb.DB, rows); err != nil {
		return fmt.Errorf("写入DuckDB失败: %w", err)
	}

	return nil
}

// syncStockInfo 同步股票基础信息到 DuckDB
func syncStockInfo() error {
	if tdx.DefaultCodes == nil {
		return fmt.Errorf("代码库未初始化")
	}

	stocks := make([]duckdb.StockInfo, 0, len(tdx.DefaultCodes.Map))
	for _, m := range tdx.DefaultCodes.Map {
		fullCode := m.FullCode()
		// 只保留沪深 A 股个股（排除 ETF、指数、北交所）
		if !protocol.IsStock(fullCode) {
			continue
		}
		if strings.HasPrefix(m.Exchange, "bj") {
			continue
		}
		stocks = append(stocks, duckdb.StockInfo{
			Code:     m.Code,
			Name:     m.Name,
			Exchange: strings.ToLower(m.Exchange),
			IsST:     duckdb.IsSTName(m.Name),
			IsETF:    false,
			Decimal:  int(m.Decimal),
		})
	}

	return duckdb.UpsertStockInfos(duckdb.DB, stocks)
}

// getStockCodes 获取全量 A 股代码（沪深，排除北交所）
func getStockCodes() []string {
	if tdx.DefaultCodes == nil {
		return nil
	}
	codes := make([]string, 0, len(tdx.DefaultCodes.Map))
	for _, m := range tdx.DefaultCodes.Map {
		fullCode := m.FullCode()
		if !protocol.IsStock(fullCode) {
			continue
		}
		if strings.HasPrefix(m.Exchange, "bj") {
			continue
		}
		codes = append(codes, m.Code)
	}
	return codes
}

// getExchange 根据代码判断交易所
func getExchange(code string) string {
	if strings.HasPrefix(code, "6") || strings.HasPrefix(code, "5") || strings.HasPrefix(code, "9") {
		return "sh"
	}
	return "sz"
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
