# History

## 2026-05-29 — 初始化專案紀錄

### CLAUDE.md 建立

初次對話，透過 `/init` 指令分析整個 codebase 後建立 `CLAUDE.md`。

**架構理解重點：**
- 本專案為 `fan-ziqi/rl_sar` 的 ITRI 分支，主套件改名為 `rl_ITRI`（原為 `rl_sar`）
- 新增了 ITRI 自研機器人：idog、idogc、leo、idogcgo2
- Core library 位於 `src/rl_ITRI/library/core/`，設計為與 ROS 無關的純 C++ 模組
- ROS1/ROS2/CMake 三種建置模式透過 `build.sh` 統一管理，以 `package.ros{1,2}.xml` symlink 切換

**joint_mapping 設計決策（值得注意）：**
`config.yaml` 中的 `joint_mapping` 陣列用於將 policy 輸出的 joint 索引重新映射到實體機器人的 joint 順序。這是因為 IsaacGym/IsaacSim 訓練時的 joint 順序可能與實體 SDK 不同，若設定錯誤會導致機器人行為異常甚至損壞。

**兩層 YAML 設計：**
- `base.yaml`：跟隨實體機器人 joint 順序，`joint_names` 必須與 URDF 一致
- `config.yaml`：跟隨訓練環境，`observations` 順序必須與訓練時完全對應

---

## 2026-06-02 ~ 2026-06-08 — 深度相機 pipeline 建立與調校

### 目標

在 Gazebo 中部署 Go2 爬梯 RL policy（`robot_lab` 配置），需要深度相機觀測。

### 建立的完整 pipeline

```
Gazebo sensor → /depth_camera/depth/image_raw (32FC1, metres)
    ↓ depth_bridge.py
/forward_depth_image (Float32MultiArray, 5184 floats, ×0.333 scaled)
    ↓ rl_sim DepthCallback → obs.depth_data
    ↓ ComputeObservation() (rl_sdk.cpp)
5229-float tensor → model forward → 12 joint targets
```

### 關鍵決策與發現

**1. image_raw 格式：32FC1，單位為公尺**
- 每像素 4 bytes，小端 IEEE 754 float32
- `inf` 表示該像素超出 far clip 範圍（看到天空/空曠）
- bytes `[0, 0, 128, 127]` = `0x7F800000` = `+inf`
- Bridge 將 inf 轉為 0.0（對應訓練時的 `depth_clipping_behavior="zero"`）

**2. `<format>R8G8B8</format>` 為必要設定**
- 曾改為 `L8` 試圖修正 `[ERROR] Unsupported Gazebo ImageFormat` 警告
- 結果造成 Gazebo depth sensor 全部輸出 inf（深度渲染失效）
- 結論：`R8G8B8` 是 Gazebo Classic depth sensor 正確運作所需；警告訊息來自 ROS plugin 的 color image 轉換，不影響深度數據
- **保持 `R8G8B8`，忽略警告**

**3. RViz2 顯示 `32FC1` 只顯示第一行的問題**
- 原因：RViz2 的 Image display 不能正確處理 float32 深度影像
- 解法：改用 DepthCloud display，或接受 PointCloud2 正確顯示就代表數據正確
- Bridge 以 CvBridge 讀取數據不受此影響

**4. 相機方向：Gazebo 沿 reference link 的 +X 軸看**
- 不是 +Z（常見誤解）
- joint rpy 控制方向，`<pose>` 在 `<gazebo reference>` 內不可靠
- 兩連桿設計：`depth_camera_link` → `depth_camera_optical_link`，sensor attach 到 optical link

**5. 最終確認的 Isaac Sim 訓練相機規格（2026-06-08 更新）**

從訓練 config 取得真實規格（與之前 64×64 不同）：

| 項目 | 舊值 | 新值（正確）|
|---|---|---|
| 掛載點 | `Head_upper` | `trunk` at `(0.32, 0.0, 0.085)` |
| 解析度 | 64×64 | 96×54 |
| 水平視野 | 0.823 rad (47°) | 1.518 rad (87°) |
| 量測範圍 | 0.1–10 m | 0.3–3.0 m |
| Bridge 縮放 | ×0.1 | ×0.333 |
| num_observations | 4141 | 5229 |

**6. 模型架構分析（`2026_06_08.pt`）**

用 `analyze_model.py` 確認：
- 輸入：5229 floats（45 proprio + 5184 depth）
- CNN：Conv2d(1→16, 5×5) → Conv2d(16→32, 3×3) → Conv2d(32→32, 3×3) → flatten → 2304 features
- MLP：Linear(2349→512) → Linear(512→256) → Linear(256→128) → Linear(128→12)
- 輸出：12 joint positions

`analyze_model.py` 注意：第一個 Linear 層輸入 2349（非模型總輸入），自動偵測需用 5229 probe。

**7. Isaac Sim 訓練與 Gazebo 的已知差距**

- `delay_steps=2`：訓練時深度影像有 2 步延遲（~40ms），Gazebo 無此延遲
- 這可能影響 policy 對近距障礙物的反應，但難以精確實作

### 建立的診斷工具

- `src/rl_ITRI/scripts/test_depth.py`：同時監控 raw topic 與 bridge output，顯示像素統計與 OpenCV 視窗
- `src/rl_ITRI/scripts/analyze_model.py`：分析 TorchScript .pt 模型架構、參數形狀、輸入輸出尺寸

### 尚未完成

- 使用新相機規格（96×54）實際測試爬梯 rl policy
- 先前測試時 dog 停在階梯前，原因是 `depth_bridge.py` 未啟動（model 收到全零深度）
