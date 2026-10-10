import sys
sys.path.insert(0, '.')
import traceback
from screener import run_screener

try:
    result = run_screener()
    print("SUCCESS!")
    print(f"run_id: {result['run_id']}")
    print(f"scanned: {result['total_scanned']}")
    print(f"pool: {result['pool_count']}")
    print(f"tiers: {result.get('tier_counts', {})}")
except Exception as e:
    print("ERROR:")
    traceback.print_exc()
