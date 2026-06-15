import pandas as pd
import matplotlib.pyplot as plt

# 讀取三個檔案
gazebo_df = pd.read_csv('gazebo_state.csv')
real_cmd_df = pd.read_csv('real_command.csv')
real_state_df = pd.read_csv('real_state.csv')

# 找出最早的時間作為基準點 (t = 0 秒)
start_time = min(gazebo_df['Timestamp'].min(), real_cmd_df['Timestamp'].min(), real_state_df['Timestamp'].min())

# 將時間軸正規化 (經過的秒數)
gazebo_df['Time_s'] = gazebo_df['Timestamp'] - start_time
real_cmd_df['Time_s'] = real_cmd_df['Timestamp'] - start_time
real_state_df['Time_s'] = real_state_df['Timestamp'] - start_time

# 迴圈產出 12 張獨立圖片
for i in range(1, 13):
    axis_name = f'Axis_{i}'
    fig, ax = plt.subplots(figsize=(8, 4))
    
    # 畫出三條軌跡線
    if axis_name in real_cmd_df.columns:
        ax.plot(real_cmd_df['Time_s'], real_cmd_df[axis_name], label='Target (Command)', color='blue', linewidth=2)
    if axis_name in gazebo_df.columns:
        ax.plot(gazebo_df['Time_s'], gazebo_df[axis_name], label='Simulated (Gazebo)', color='red', alpha=0.7, linewidth=2)
    if axis_name in real_state_df.columns:
        ax.plot(real_state_df['Time_s'], real_state_df[axis_name], label='Real (Physical)', color='green', alpha=0.7, linewidth=2)
    
    # 設定圖表標籤
    ax.set_title(f'Joint Tracking (High Precision): {axis_name}')
    ax.set_ylabel('Position (q)')
    ax.set_xlabel('Time (s)')
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(loc='best')
    
    # 存檔並關閉，避免記憶體佔用
    plt.tight_layout()
    plt.savefig(f'{axis_name}_comparison.png')
    plt.close(fig)
    # plt.show()

print("12張高精度軌跡追隨圖已成功輸出！")