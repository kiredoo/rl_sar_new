# Progress

## 主要目標

在 Gazebo 模擬中驗證 Go2 爬梯 RL policy（`robot_lab` 配置，帶深度相機），並部署至 ITRI 機器人。

---

## 現況

**更新日期：2026-06-08**

### 已完成
- 建立 `CLAUDE.md`、`notes/` 紀錄系統
- **深度相機 Gazebo pipeline 完整建立並驗證通過**
  - `gazebo.xacro`：掛載深度相機、sensor plugin 設定
  - `depth_bridge.py`：訂閱 `image_raw`，預處理後發布 `Float32MultiArray`
  - `rl_sim.cpp`：訂閱 `DepthCallback`，注入 `obs.depth_data`
  - `rl_sdk.cpp`：`ComputeObservation()` 支援 `"depth_image"` 項目
- **相機參數更新為與 Isaac Sim 訓練完全一致（2026-06-08）**
  - 掛載點：`Head_upper` → `trunk`，偏移 `(0.32, 0.0, 0.085)`
  - 解析度：64×64 → 96×54（5184 像素）
  - 視野：0.823 rad → 1.518 rad（87°）
  - 量測範圍：0.1–10 m → 0.3–3.0 m
  - Bridge 縮放：×0.1 → ×0.333
  - `config.yaml`：`num_observations` 4141 → 5229
- **新 policy：`2026_06_08.pt`**（已分析架構：CNN 3層 + MLP 4層，input=5229，output=12）
- 診斷工具：`test_depth.py`（驗證 pipeline 數據）、`analyze_model.py`（分析模型架構）

### 進行中
- 分支 `ros2_ting`：相機設定更新後**尚未重新測試爬梯**
- idogcgo2 FSM 整合（untracked）

---

## 活躍問題

| 問題 | 狀態 |
|------|------|
| 爬梯 policy 未成功爬梯 | 待測試（pipeline 已就緒，舊測試時 bridge 未啟動） |
| `delay_steps=2` 未實作 | 訓練用延遲 2 步深度，實機無此延遲（可能影響性能） |
| rl_sim Forward() 含每 cycle debug print | 仍在，會 flood terminal，需時移除 |
| idogcgo2 FSM | 進行中 |

---

## 下一步

1. 重新 build 並重啟模擬（`./run.sh -r go2 -w stairs`）
2. 啟動 `depth_bridge.py` 並用 `test_depth.py` 確認數據（應為 `shape=(54,64)`，count=5184）
3. 啟動 `rl_sim`，按 `2`（robot_lab）→ `0`（站立）→ `1`（RL）→ `w`（前進）
4. 觀察 dog 是否成功爬梯
5. 若不成功，考慮實作 `delay_steps=2` 或調整相機俯仰角
