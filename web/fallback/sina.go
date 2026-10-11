package fallback

import (
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// SinaSource 新浪财经数据源
type SinaSource struct {
	client    *http.Client
	available bool
}

// NewSinaSource 创建新浪数据源
func NewSinaSource() *SinaSource {
	return &SinaSource{
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
		available: true,
	}
}

func (s *SinaSource) Name() string {
	return "sina"
}

func (s *SinaSource) Available() bool {
	return s.available
}

// GetQuote 获取实时行情
// 新浪行情API: http://hq.sinajs.cn/list=sh600519,sz000001
func (s *SinaSource) GetQuote(codes []string) ([]*Quote, error) {
	if len(codes) == 0 {
		return nil, fmt.Errorf("codes empty")
	}

	sinaCodes := make([]string, 0, len(codes))
	for _, code := range codes {
		sinaCodes = append(sinaCodes, toSinaCode(code))
	}

	url := fmt.Sprintf("http://hq.sinajs.cn/list=%s", strings.Join(sinaCodes, ","))
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	// 新浪需要Referer头
	req.Header.Set("Referer", "https://finance.sina.com.cn")
	req.Header.Set("User-Agent", "Mozilla/5.0")

	resp, err := s.client.Do(req)
	if err != nil {
		s.available = false
		return nil, fmt.Errorf("sina request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("sina read body failed: %w", err)
	}

	text := string(body)
	quotes := make([]*Quote, 0, len(codes))
	lines := strings.Split(text, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || !strings.Contains(line, "=") {
			continue
		}
		// var hq_str_sh600519="贵州茅台,1688.00,1685.00,..."
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		data := strings.Trim(parts[1], "\";")
		if data == "" {
			continue
		}
		fields := strings.Split(data, ",")
		if len(fields) < 32 {
			continue
		}

		// 提取代码
		code := ""
		if strings.HasPrefix(parts[0], "var hq_str_") {
			code = strings.TrimPrefix(parts[0], "var hq_str_")
		}

		quote := &Quote{
			Name:      fields[0],
			Code:      code,
			Open:      parseFloat(fields[1]),
			LastClose: parseFloat(fields[2]),
			Price:     parseFloat(fields[3]),
			High:      parseFloat(fields[4]),
			Low:       parseFloat(fields[5]),
			Volume:    parseInt64(fields[8]),
			Amount:    parseFloat(fields[9]),
			Bid1:      parseFloat(fields[11]),
			Ask1:      parseFloat(fields[21]),
			Source:    "sina",
		}
		quotes = append(quotes, quote)
	}

	s.available = true
	return quotes, nil
}

// GetKline 获取日K线数据
// 新浪K线API: https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=320
func (s *SinaSource) GetKline(code string, count int) ([]*Kline, error) {
	sinaCode := toSinaCode(code)
	url := fmt.Sprintf("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=%s&scale=240&ma=no&datalen=%d", sinaCode, count)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Referer", "https://finance.sina.com.cn")
	req.Header.Set("User-Agent", "Mozilla/5.0")

	resp, err := s.client.Do(req)
	if err != nil {
		s.available = false
		return nil, fmt.Errorf("sina kline request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("sina kline read body failed: %w", err)
	}

	klines, err := parseSinaKline(body)
	if err != nil {
		return nil, err
	}

	s.available = true
	return klines, nil
}

// parseSinaKline 解析新浪K线JSON
func parseSinaKline(body []byte) ([]*Kline, error) {
	text := string(body)
	// 格式: [{day:"2024-01-01",open:"10.0",high:"11.0",low:"9.5",close:"10.5",volume:"100000"},...]
	klines := make([]*Kline, 0)
	// 简单解析每个对象
	objects := splitJSONObjects(text)
	for _, obj := range objects {
		kline := &Kline{}
		if v := extractJSONField(obj, "day"); v != "" {
			kline.Date = strings.Trim(v, "\"")
		}
		if v := extractJSONField(obj, "open"); v != "" {
			kline.Open = parseFloat(v)
		}
		if v := extractJSONField(obj, "high"); v != "" {
			kline.High = parseFloat(v)
		}
		if v := extractJSONField(obj, "low"); v != "" {
			kline.Low = parseFloat(v)
		}
		if v := extractJSONField(obj, "close"); v != "" {
			kline.Close = parseFloat(v)
		}
		if v := extractJSONField(obj, "volume"); v != "" {
			kline.Volume = parseInt64(v)
		}
		if kline.Date != "" {
			klines = append(klines, kline)
		}
	}
	return klines, nil
}

// splitJSONObjects 分割JSON数组中的对象
func splitJSONObjects(s string) []string {
	objects := make([]string, 0)
	depth := 0
	start := -1
	for i := 0; i < len(s); i++ {
		if s[i] == '{' {
			if depth == 0 {
				start = i
			}
			depth++
		} else if s[i] == '}' {
			depth--
			if depth == 0 && start >= 0 {
				objects = append(objects, s[start:i+1])
				start = -1
			}
		}
	}
	return objects
}

// extractJSONField 提取JSON字段值
func extractJSONField(obj, field string) string {
	key := fmt.Sprintf(`%s:"`, field)
	idx := strings.Index(obj, key)
	if idx < 0 {
		// 尝试带引号的key
		key = fmt.Sprintf(`"%s":"`, field)
		idx = strings.Index(obj, key)
	}
	if idx < 0 {
		return ""
	}
	start := idx + len(key)
	end := strings.Index(obj[start:], `"`)
	if end < 0 {
		return ""
	}
	return obj[start : start+end]
}

// toSinaCode 转换代码为新浪格式
func toSinaCode(code string) string {
	return toTencentCode(code) // 新浪和腾讯代码格式相同
}
