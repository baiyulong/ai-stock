package fallback

import "time"

// Quote 实时行情数据结构（与TDX返回兼容）
type Quote struct {
	Code    string  `json:"code"`
	Name    string  `json:"name"`
	Price   float64 `json:"price"`
	LastClose float64 `json:"last_close"`
	Open    float64 `json:"open"`
	High    float64 `json:"high"`
	Low     float64 `json:"low"`
	Volume  int64   `json:"volume"`
	Amount  float64 `json:"amount"`
	Bid1    float64 `json:"bid1"`
	Ask1    float64 `json:"ask1"`
	BidVol1 int64   `json:"bid_vol1"`
	AskVol1 int64   `json:"ask_vol1"`
	Inner   int64   `json:"inner"` // 内盘
	Outer   int64   `json:"outer"` // 外盘
	Source  string  `json:"source"` // 数据来源
}

// Kline K线数据
type Kline struct {
	Date   string  `json:"date"`
	Open   float64 `json:"open"`
	Close  float64 `json:"close"`
	High   float64 `json:"high"`
	Low    float64 `json:"low"`
	Volume int64   `json:"volume"`
	Amount float64 `json:"amount"`
}

// DataSource 数据源接口
type DataSource interface {
	// Name 数据源名称
	Name() string
	// GetQuote 获取实时行情
	GetQuote(codes []string) ([]*Quote, error)
	// GetKline 获取日K线数据
	GetKline(code string, count int) ([]*Kline, error)
	// Available 数据源是否可用
	Available() bool
}

// FallbackQuote 带时间戳的行情缓存
type FallbackQuote struct {
	Quote     *Quote
	Timestamp time.Time
}
