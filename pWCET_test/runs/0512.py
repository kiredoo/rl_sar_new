import pandas as pd

# CSV 路徑
csv_path = '/home/itri/rl_sar_new/rl_sar/pWCET_test/runs/rlsim_sched.csv'

# 讀 CSV
df = pd.read_csv(csv_path)

# 只抓 wakeup 事件
wakeup = df[df['event_type']=='wakeup'].copy()

# 計算每個 thread start-to-start interval
wakeup['interval_ns'] = wakeup.groupby('pid')['timestamp_ns'].diff()
wakeup['interval_us'] = wakeup['interval_ns'] / 1000.0

# 設 loop_control deadline = 5000 us
deadline_us = 5000
wakeup['miss'] = wakeup['interval_us'] > deadline_us

# 整理每個 thread 統計
results = []
for tid in wakeup['pid'].unique():
    w = wakeup[wakeup['pid']==tid]
    if len(w) < 2:
        continue
    results.append({
        'pid': tid,
        'num_events': len(w),
        'interval_mean_us': w['interval_us'].mean(),
        'interval_p50_us': w['interval_us'].quantile(0.5),
        'interval_p95_us': w['interval_us'].quantile(0.95),
        'interval_p99_us': w['interval_us'].quantile(0.99),
        'interval_max_us': w['interval_us'].max(),
        'deadline_miss_count': w['miss'].sum()
    })

results_df = pd.DataFrame(results)

# 保存到 CSV，方便本地查看
results_df.to_csv('/mnt/data/rl_sim_bpftrace_interval_analysis.csv', index=False)

print("解析完成，結果已儲存到 rl_sim_bpftrace_interval_analysis.csv")
