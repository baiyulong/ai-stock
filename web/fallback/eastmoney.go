package fallback

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// EastmoneySource 东方财富数据源
type EastmoneySource struct {
	client    *http.Client
	available bool
}

// NewEastmoneySource 创建东方财富数据源
func NewEastmoneySource() *EastmoneySource {
	return &EastmoneySource{
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
		available: true,
	}
}

func (e *EastmoneySource) Name() string {
	return "eastmoney"
}

func (e *EastmoneySource) Available() bool {
	return e.available
}

// GetQuote 获取实时行情
// 东财行情API: https://push2.eastmoney.com/api/qt/stock/get?secid=1.600519&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f170
func (e *EastmoneySource) GetQuote(codes []string) ([]*Quote, error) {
	if len(codes) == 0 {
		return nil, fmt.Errorf("codes empty")
	}

	quotes := make([]*Quote, 0, len(codes))
	for _, code := range codes {
		quote, err := e.getSingleQuote(code)
		if err == nil && quote != nil {
			quotes = append(quotes, quote)
		}
	}

	if len(quotes) == 0 {
		e.available = false
		return nil, fmt.Errorf("eastmoney all quotes failed")
	}

	e.available = true
	return quotes, nil
}

// getSingleQuote 获取单只股票行情
func (e *EastmoneySource) getSingleQuote(code string) (*Quote, error) {
	secid := toEastmoneySecid(code)
	// f43=最新价, f44=最高, f45=最低, f46=今开, f47=成交量, f48=成交额, f57=代码, f58=名称, f60=昨收, f168=换手率, f170=涨跌幅
	fields := "f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f170,f169,f171"
	url := fmt.Sprintf("https://push2.eastmoney.com/api/qt/stock/get?secid=%s&fields=%s", secid, fields)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0")
	req.Header.Set("Referer", "https://quote.eastmoney.com/")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("eastmoney request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		Data map[string]interface{} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	if result.Data == nil {
		return nil, fmt.Errorf("eastmoney no data")
	}

	data := result.Data
	quote := &Quote{
		Code:      getStringField(data, "f57"),
		Name:      getStringField(data, "f58"),
		Price:     getFloatField(data, "f43") / 100, // 东财价格是分
		High:      getFloatField(data, "f44") / 100,
		Low:       getFloatField(data, "f45") / 100,
		Open:      getFloatField(data, "f46") / 100,
		Volume:    int64(getFloatField(data, "f47")),
		Amount:    getFloatField(data, "f48"),
		LastClose: getFloatField(data, "f60") / 100,
		Source:    "eastmoney",
	}

	return quote, nil
}

// GetKline 获取日K线数据（前复权）
// 东财K线API: https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600519&klt=101&fqt=1&lmt=320&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57
func (e *EastmoneySource) GetKline(code string, count int) ([]*Kline, error) {
	secid := toEastmoneySecid(code)
	url := fmt.Sprintf("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s&klt=101&fqt=1&lmt=%d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57", secid, count)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0")
	req.Header.Set("Referer", "https://quote.eastmoney.com/")

	resp, err := e.client.Do(req)
	if err != nil {
		e.available = false
		return nil, fmt.Errorf("eastmoney kline request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		Data struct {
			Klines []string `json:"klines"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	klines := make([]*Kline, 0, len(result.Data.Klines))
	for _, line := range result.Data.Klines {
		// 格式: 2024-01-01,10.0,10.5,11.0,9.5,100000,1000000.0
		fields := strings.Split(line, ",")
		if len(fields) < 6 {
			continue
		}
		kline := &Kline{
			Date:   fields[0],
			Open:   parseFloat(fields[1]),
			Close:  parseFloat(fields[2]),
			High:   parseFloat(fields[3]),
			Low:    parseFloat(fields[4]),
			Volume: parseInt64(fields[5]),
		}
		if len(fields) >= 7 {
			kline.Amount = parseFloat(fields[6])
		}
		klines = append(klines, kline)
	}

	e.available = true
	return klines, nil
}

// toEastmoneySecid 转换代码为东财secid格式
// 沪市: 1.600519, 深市: 0.000001
func toEastmoneySecid(code string) string {
	code = strings.ToLower(strings.TrimSpace(code))
	if strings.HasPrefix(code, "sh") {
		return "1." + strings.TrimPrefix(code, "sh")
	}
	if strings.HasPrefix(code, "sz") {
		return "0." + strings.TrimPrefix(code, "sz")
	}
	if strings.HasPrefix(code, "bj") {
		return "0." + strings.TrimPrefix(code, "bj")
	}
	// 6开头是沪市，0/3开头是深市
	if len(code) >= 1 {
		switch code[0] {
		case '6', '5', '9':
			return "1." + code
		case '0', '1', '2', '3':
			return "0." + code
		case '4', '8':
			return "0." + code
		}
	}
	return "1." + code
}

// getStringField 从map获取字符串字段
func getStringField(data map[string]interface{}, key string) string {
	if v, ok := data[key]; ok {
		switch val := v.(type) {
		case string:
			return val
		case float64:
			return fmt.Sprintf("%.0f", val)
		}
	}
	return ""
}

// getFloatField 从map获取浮点数字段
func getFloatField(data map[string]interface{}, key string) float64 {
	if v, ok := data[key]; ok {
		switch val := v.(type) {
		case float64:
			return val
		case string:
			return parseFloat(val)
		}
	}
	return 0
}
