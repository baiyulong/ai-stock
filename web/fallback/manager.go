package fallback

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// Manager 备用数据源管理器
type Manager struct {
	sources   []DataSource
	mu        sync.RWMutex
	quoteCache map[string]*FallbackQuote
	cacheTTL  time.Duration
}

// NewManager 创建数据源管理器
func NewManager() *Manager {
	m := &Manager{
		sources: []DataSource{
			NewTencentSource(),
			NewSinaSource(),
			NewEastmoneySource(),
		},
		quoteCache: make(map[string]*FallbackQuote),
		cacheTTL:   10 * time.Second,
	}
	return m
}

// GetQuote 获取实时行情（按优先级尝试各数据源）
func (m *Manager) GetQuote(codes []string) ([]*Quote, error) {
	if len(codes) == 0 {
		return nil, fmt.Errorf("codes empty")
	}

	// 先查缓存
	result := make([]*Quote, 0, len(codes))
	needFetch := make([]string, 0, len(codes))

	m.mu.RLock()
	for _, code := range codes {
		if cached, ok := m.quoteCache[code]; ok {
			if time.Since(cached.Timestamp) < m.cacheTTL {
				result = append(result, cached.Quote)
				continue
			}
		}
		needFetch = append(needFetch, code)
	}
	m.mu.RUnlock()

	if len(needFetch) == 0 {
		return result, nil
	}

	// 按优先级尝试各数据源
	var lastErr error
	for _, source := range m.sources {
		if !source.Available() {
			continue
		}
		quotes, err := source.GetQuote(needFetch)
		if err != nil {
			lastErr = err
			log.Printf("[fallback] %s quote failed: %v, trying next source", source.Name(), err)
			continue
		}
		if len(quotes) > 0 {
			// 缓存结果
			m.mu.Lock()
			for _, q := range quotes {
				m.quoteCache[q.Code] = &FallbackQuote{
					Quote:     q,
					Timestamp: time.Now(),
				}
			}
			m.mu.Unlock()

			result = append(result, quotes...)
			return result, nil
		}
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return nil, fmt.Errorf("all fallback sources unavailable")
}

// GetKline 获取日K线数据（按优先级尝试各数据源）
func (m *Manager) GetKline(code string, count int) ([]*Kline, error) {
	var lastErr error
	for _, source := range m.sources {
		if !source.Available() {
			continue
		}
		klines, err := source.GetKline(code, count)
		if err != nil {
			lastErr = err
			log.Printf("[fallback] %s kline failed: %v, trying next source", source.Name(), err)
			continue
		}
		if len(klines) > 0 {
			return klines, nil
		}
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return nil, fmt.Errorf("all fallback sources unavailable")
}

// GetSourceStatus 获取各数据源状态
func (m *Manager) GetSourceStatus() map[string]bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	status := make(map[string]bool)
	for _, source := range m.sources {
		status[source.Name()] = source.Available()
	}
	return status
}

// ClearCache 清除缓存
func (m *Manager) ClearCache() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.quoteCache = make(map[string]*FallbackQuote)
}

// 全局单例
var (
	globalManager *Manager
	once          sync.Once
)

// GetManager 获取全局管理器
func GetManager() *Manager {
	once.Do(func() {
		globalManager = NewManager()
	})
	return globalManager
}
