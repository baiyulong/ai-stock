import sys
sys.path.insert(0, '.')
from db import load_day_klines
try:
    df = load_day_klines(lookback=140)
    print('Shape:', df.shape)
    print('Columns:', df.columns.tolist())
    print(df.head(2))
except Exception as e:
    import traceback
    traceback.print_exc()
