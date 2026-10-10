"""测试选股策略引擎"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screener import run_screener
from detail import analyze_stock

print("=== 运行选股策略 ===")
result = run_screener()
print(f"运行ID: {result['run_id']}")
print(f"扫描股票数: {result['total_scanned']}")
print(f"入池数: {result['pool_count']}")
print(f"分层统计: {result.get('tier_counts', {})}")
print()

if result["results"]:
    print("=== 入池股票（前10） ===")
    for i, r in enumerate(result["results"][:10]):
        print(f"{i+1}. {r['code']} {r['name']} | 分层: {r['tier']} | "
              f"低点抬升: {r['low_raise_pct']:.2f}% | "
              f"距低点回升: {r['rebound_pct']:.2f}% | "
              f"距高点空间: {r['room_pct']:.2f}%")
else:
    print("（5只测试股票中无入池标的，属正常现象）")

print()
print("=== 单票详细分析: 600519 贵州茅台 ===")
detail = analyze_stock("600519")
if "error" in detail:
    print(f"错误: {detail['error']}")
else:
    print(f"最新价: {detail['basic']['last_close']}")
    print(f"入池条件: {detail['pool_checks']}")
    print(f"分层指标: {detail['tier_indicators']}")
    print(f"三点验证: support={detail['confirmations']['support']['pass']}, "
          f"volume_breakout={detail['confirmations']['volume_breakout']['pass']}, "
          f"ma_turn={detail['confirmations']['ma_turn']['pass']}")
    print(f"证伪信号: invalidated={detail['invalidation']['invalidated']}")
    print(f"K线数据条数: {len(detail['klines'])}")
