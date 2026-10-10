package screener

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/injoyai/tdx"
	"web/duckdb"
)

// StrategyServiceURL Python 策略服务地址
const StrategyServiceURL = "http://127.0.0.1:18081"

var strategyClient = &http.Client{Timeout: 120 * time.Second}

// HandleSync 触发数据同步（POST /api/screener/sync）
func HandleSync(mgr *tdx.Manage, fallbackClient *tdx.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, `{"code":-1,"message":"只支持POST请求"}`, http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			Codes       []string `json:"codes"`
			Concurrency int      `json:"concurrency"`
			Lookback    int      `json:"lookback"`
			Incremental bool     `json:"incremental"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)

		cfg := SyncConfig{
			Codes:       req.Codes,
			Concurrency: req.Concurrency,
			Lookback:    req.Lookback,
			Incremental: req.Incremental,
		}

		// 异步执行（用独立 context，不随 HTTP 请求结束而取消）
		go func() {
			_ = SyncMarketData(context.Background(), mgr, fallbackClient, cfg)
		}()

		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"code":    0,
			"message": "同步任务已启动",
			"data":    GetSyncStatus(),
		})
	}
}

// HandleSyncStatus 查询同步状态（GET /api/screener/sync-status）
func HandleSyncStatus(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"code":    0,
		"message": "success",
		"data":    GetSyncStatus(),
	})
}

// HandleDBStats 查询 DuckDB 数据统计（GET /api/screener/db-stats）
func HandleDBStats(w http.ResponseWriter, r *http.Request) {
	if duckdb.DB == nil {
		http.Error(w, `{"code":-1,"message":"DuckDB未初始化"}`, http.StatusInternalServerError)
		return
	}

	totalRows, _ := duckdb.CountDayKlines(duckdb.DB)
	totalCodes, _ := duckdb.CountDistinctCodes(duckdb.DB)

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"code":    0,
		"message": "success",
		"data": map[string]interface{}{
			"total_rows":  totalRows,
			"total_codes": totalCodes,
		},
	})
}

// HandleExportKline 导出生成交 CSV（供 Python 策略服务读取，避免 DuckDB 文件锁冲突）
func HandleExportKline(w http.ResponseWriter, r *http.Request) {
	if duckdb.DB == nil {
		http.Error(w, `{"code":-1,"message":"DuckDB未初始化"}`, http.StatusInternalServerError)
		return
	}

	lookback := 140
	if lb := r.URL.Query().Get("lookback"); lb != "" {
		if n, err := strconv.Atoi(lb); err == nil && n > 0 {
			lookback = n
		}
	}

	code := r.URL.Query().Get("code")

	var rows *sql.Rows
	var err error
	if code != "" {
		rows, err = duckdb.DB.Query(`
			SELECT code, exchange, date, open, high, low, close, volume, amount
			FROM day_kline
			WHERE code = ?
			ORDER BY date ASC
		`, code)
	} else {
		rows, err = duckdb.DB.Query(`
			SELECT code, exchange, date, open, high, low, close, volume, amount
			FROM (
				SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) as rn
				FROM day_kline
			)
			WHERE rn <= ?
			ORDER BY code, date ASC
		`, lookback)
	}
	if err != nil {
		http.Error(w, `{"code":-1,"message":"查询失败"}`, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename=kline_export.csv")

	// 写 CSV 头
	fmt.Fprintln(w, "code,exchange,date,open,high,low,close,volume,amount")

	// 写数据
	var exchange string
	var date string
	var open, high, low, close, amount float64
	var volume int64
	for rows.Next() {
		if err := rows.Scan(&code, &exchange, &date, &open, &high, &low, &close, &volume, &amount); err != nil {
			continue
		}
		fmt.Fprintf(w, "%s,%s,%s,%.4f,%.4f,%.4f,%.4f,%d,%.2f\n",
			code, exchange, date, open, high, low, close, volume, amount)
	}
}

// HandleExportStockInfo 导出股票信息（代码+名称+是否ST），供 Python 策略服务使用
func HandleExportStockInfo(w http.ResponseWriter, r *http.Request) {
	if duckdb.DB == nil {
		http.Error(w, `{"code":-1,"message":"DuckDB未初始化"}`, http.StatusInternalServerError)
		return
	}

	rows, err := duckdb.DB.Query(`
		SELECT code, name, exchange, is_st, is_etf, decimal
		FROM stock_info
		ORDER BY code ASC
	`)
	if err != nil {
		http.Error(w, `{"code":-1,"message":"查询失败"}`, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename=stock_info.csv")
	fmt.Fprintln(w, "code,name,exchange,is_st,is_etf,decimal")

	var code, name, exchange string
	var isST, isETF bool
	var decimal int
	for rows.Next() {
		if err := rows.Scan(&code, &name, &exchange, &isST, &isETF, &decimal); err != nil {
			continue
		}
		// CSV 转义名称中的逗号
		nameEscaped := strings.ReplaceAll(name, ",", "，")
		fmt.Fprintf(w, "%s,%s,%s,%v,%v,%d\n", code, nameEscaped, exchange, isST, isETF, decimal)
	}
}

// HandleStrategyProxy 反向代理到 Python 策略服务
// 匹配 /api/screener/ 下除 sync/sync-status/db-stats 之外的所有路径
func HandleStrategyProxy(w http.ResponseWriter, r *http.Request) {
	// 构建目标 URL
	targetURL := StrategyServiceURL + r.URL.Path
	if r.URL.RawQuery != "" {
		targetURL += "?" + r.URL.RawQuery
	}

	// 创建代理请求
	proxyReq, err := http.NewRequestWithContext(r.Context(), r.Method, targetURL, r.Body)
	if err != nil {
		http.Error(w, `{"code":-1,"message":"代理请求创建失败"}`, http.StatusInternalServerError)
		return
	}

	// 复制请求头
	for key, values := range r.Header {
		for _, v := range values {
			proxyReq.Header.Add(key, v)
		}
	}
	// 设置 Host
	proxyReq.Host = "127.0.0.1:18081"

	// 执行请求
	resp, err := strategyClient.Do(proxyReq)
	if err != nil {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"code":    -1,
			"message": "策略服务不可用，请确认 Python 服务已启动 (127.0.0.1:18081)",
			"error":   err.Error(),
		})
		return
	}
	defer resp.Body.Close()

	// 复制响应头
	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.WriteHeader(resp.StatusCode)

	// 复制响应体
	io.Copy(w, resp.Body)
}

// HandleStrategyHealth 策略服务健康检查（代理 + 本地状态）
func HandleStrategyHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, StrategyServiceURL+"/api/screener/health", nil)
	resp, err := strategyClient.Do(req)

	status := "stopped"
	if err == nil {
		resp.Body.Close()
		if resp.StatusCode == http.StatusOK {
			status = "running"
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"code":    0,
		"message": "success",
		"data": map[string]interface{}{
			"strategy_service": status,
			"strategy_url":     StrategyServiceURL,
		},
	})
}

// 辅助：判断路径是否应由本地处理（不走代理）
func isLocalScreenerPath(path string) bool {
	localPaths := []string{
		"/api/screener/sync",
		"/api/screener/sync-status",
		"/api/screener/db-stats",
		"/api/screener/health",
	}
	for _, p := range localPaths {
		if strings.HasPrefix(path, p) {
			return true
		}
	}
	return false
}

// 确保 url 包被使用（防止编译器报错）
var _ = url.Parse
