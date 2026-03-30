# Integrated Sim World (GPS Tracker + Sim World Lite)

即時 GPS 追蹤 + UAV 3D 模擬控制 + 照片上傳 + Sionna 無線通道模擬。

## 外網入口

- 前端（Public URL）：https://frontend.simworld.website

## 功能

### 使用者功能（前端）

| 功能 | 說明 |
|------|------|
| 即時 GPS 同步 | 手機透過 WebSocket 持續上報 GPS（lat/lon/alt/accuracy），電腦端即時顯示位置 |
| 多裝置追蹤 | 支援同時連接多台裝置，列表顯示裝置名稱、狀態，並可切換追蹤目標 |
| 3D UAV 可視化 | GPS 轉 ENU 座標後在 3D 場景中顯示 UAV 即時位置與高度 |
| UAV 軌跡管理 | 顯示飛行路徑、跨裝置同步清除軌跡、切場景後自動重置路徑 |
| 場景切換 | 支援 NTPU / NYCU 場景切換，對應不同地理原點與模型配置 |
| UAV 控制面板 | 提供手動控制、自動移動、動畫開關等操作，便於模擬飛行測試 |
| 裝置設定面板 | 可調整模擬裝置（TX/RX）座標與參數，提供無線模擬輸入資料 |
| 手機拍照上傳 | 手機端可直接拍照上傳，附帶當下座標資訊（lat/lon/alt） |
| 照片歷史檢視 | 電腦端即時顯示上傳照片、支援刪除、並同步廣播給其他連線端 |
| Sionna 視覺化面板 | 一鍵產生並預覽 SINR / CFR / Doppler / Channel IR / ISS / TSS / CFAR 地圖 |

### 系統能力（後端 API / 即時通訊）

| 類別 | 提供能力 |
|------|----------|
| WebSocket (`/ws/gps`) | 裝置註冊、GPS 廣播、改名同步、清路徑同步、斷線事件推播 |
| GPS REST (`/api/gps/devices`) | 回傳目前在線裝置與最新 GPS 快照 |
| 照片 REST | `/api/upload-photo` 上傳、`/api/photo-history` 歷史查詢、`/api/delete-photo/{filename}` 刪除 |
| 靜態資源服務 | `/uploads` 提供照片存取、`/simulations` 提供模擬輸出圖檔 |
| Sionna API | `/api/sionna/status`、`/api/sionna/sinr-map`、`/api/sionna/cfr-plot`、`/api/sionna/doppler`、`/api/sionna/channel-response` |
| 場景模擬 API | `/api/simulate` 依 scene + device 參數產生 ISS/TSS/CFAR 等地圖結果 |
| 部署連線 | Cloudflare Tunnel 將本機前後端安全映射至公網網域 |

---

## 環境需求

- OS: **Windows** / Linux / macOS
- Python **3.12+**
- Node.js **18+**（建議 v22）
- npm（通常會隨 Node.js 安裝）
- `cloudflared`（選用，只有要用公網才需要）
- LLVM（選用，若使用 Sionna 時建議安裝，Windows 預設讀取 `C:\Program Files\LLVM\bin\LLVM-C.dll`）

---

## 套件清單

### 後端 Python 套件（`backend/requirements.txt`）

- FastAPI / Uvicorn / 上傳檔案支援
	- `fastapi==0.115.0`
	- `uvicorn[standard]==0.30.6`
	- `python-multipart==0.0.12`
	- `aiofiles==24.1.0`
- Sionna 模擬相關
	- `sionna`
	- `sionna-rt`
	- `tensorflow`
	- `trimesh`
	- `pyrender>=0.1.45`
	- `numpy>=1.24.0`
	- `matplotlib`

### 前端 Node.js 套件（`frontend/package.json`）

- 主要相依
	- `react`, `react-dom`
	- `three`, `@react-three/fiber`, `@react-three/drei`, `three-stdlib`
- 開發相依
	- `vite`, `typescript`, `sass`
	- `@vitejs/plugin-react`
	- `@types/node`, `@types/react`, `@types/react-dom`, `@types/three`

---

## 快速安裝

### 1. Clone 專案

```bash
git clone https://github.com/711483135/integrated-sim-world.git
cd integrated-sim-world
```

### 2. 後端：建立虛擬環境並安裝套件（Windows）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd ..
```

> ⚠️ Sionna / TensorFlow 安裝時間可能較長。
> 如果你暫時不需要無線模擬功能，可先安裝核心後端套件：
> ```powershell
> .\.venv\Scripts\python -m pip install fastapi uvicorn[standard] python-multipart aiofiles
> ```

### 3. 前端：安裝 npm 套件

```powershell
cd frontend
npm install
cd ..
```

### 4. 設定環境變數

```powershell
cd frontend
Copy-Item .env.example .env -Force
cd ..
```

本地開發預設值可直接使用，不需要修改。
若要用 Cloudflare Tunnel 公網連線，可再依你的網域調整 `frontend/.env`。

### 5. 啟動（Windows PowerShell）

#### 本機模式（不開 tunnel）

```powershell
.\start.ps1 -NoTunnel
```

#### 公網模式（啟用 tunnel）

```powershell
.\start.ps1
```

服務預設位址：
- **前端介面**：http://localhost:5173
- **後端 API**：http://localhost:8888
- **公網前端**：https://frontend.simworld.website（啟用 tunnel 時）

按 `Ctrl + C` 可停止所有服務。

啟動後可查看 log：

- `.logs/backend.log`
- `.logs/frontend.log`
- `.logs/tunnel.log` / `.logs/tunnel.log.err`

---

## Linux / macOS 啟動（bash）

```bash
bash start.sh --no-tunnel
# 或
bash start.sh
```

---

## Cloudflare Tunnel 設定（選用）

只有需要手機從外網連線時才需要設定。

### 1. 安裝 cloudflared（Windows）
請前往 [Cloudflare 官網](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 下載 Windows 版 `cloudflared.exe` 並加入環境變數。

### 2. 設定 Token
在根目錄或環境中設定您的 Token 以啟動內網穿透。

### 3. 設定前端指向公網後端

編輯 `frontend/.env`：

```env
VITE_WS_URL=wss://backend.yourdomain.com/ws/gps
VITE_API_URL=https://backend.yourdomain.com
```

### 4. 驗證 tunnel 是否成功

啟動後可檢查 `.logs/tunnel.log.err`，若看到類似 `Registered tunnel connection` 代表連線成功。
