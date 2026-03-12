import logging
import os
import json
import time
import uuid

# Auto-set DRJIT_LIBLLVM_PATH before any drjit/mitsuba/sionna import
if os.name == "nt" and not os.environ.get("DRJIT_LIBLLVM_PATH"):
    for _dll in [
        r"C:\Program Files\LLVM\bin\LLVM-C.dll",
        r"C:\Program Files (x86)\LLVM\bin\LLVM-C.dll",
    ]:
        if os.path.isfile(_dll):
            os.environ["DRJIT_LIBLLVM_PATH"] = _dll
            break

from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 資料夾設定
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
PHOTOS_JSON = UPLOAD_DIR / "photos.json"

# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
app = FastAPI(title="GPS Tracker API", version="1.0.0")

# CORS — 允許所有來源（也可以只填你的 cloudflare 域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態檔案：讓前端可以直接讀取已上傳的照片
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# 靜態檔案：Sionna 模擬產生的圖片
SIMULATION_OUT_DIR = BASE_DIR / "static" / "images"
SIMULATION_OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/simulations", StaticFiles(directory=str(SIMULATION_OUT_DIR)), name="simulations")


# ──────────────────────────────────────────────
# GPS WebSocket 連線管理器
# ──────────────────────────────────────────────
class GPSConnectionManager:
    def __init__(self):
        # { deviceId: WebSocket }
        self.connections: Dict[str, WebSocket] = {}
        # { deviceId: { lat, lon, alt, accuracy, deviceName, ... } }
        self.gps_data: Dict[str, dict] = {}
        # { deviceId: deviceName }
        self.names: Dict[str, str] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()

    def register(self, device_id: str, ws: WebSocket, name: str = "Unknown"):
        self.connections[device_id] = ws
        self.names[device_id] = name
        logger.info(f"✅ 裝置已註冊: {device_id[:12]} ({name})  連線數: {len(self.connections)}")

    def disconnect(self, device_id: str):
        self.connections.pop(device_id, None)
        self.gps_data.pop(device_id, None)
        self.names.pop(device_id, None)
        logger.info(f"📡 裝置斷線: {device_id[:12]}  連線數: {len(self.connections)}")

    def update_gps(self, device_id: str, data: dict):
        self.gps_data[device_id] = data

    async def broadcast(self, message: str):
        """廣播給所有已連線裝置"""
        dead: list[str] = []
        for did, ws in self.connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(did)
        for did in dead:
            self.disconnect(did)

    async def broadcast_except(self, message: str, exclude_id: str):
        """廣播給除 exclude_id 以外的裝置"""
        dead: list[str] = []
        for did, ws in self.connections.items():
            if did == exclude_id:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(did)
        for did in dead:
            self.disconnect(did)


gps_manager = GPSConnectionManager()


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────
@app.get("/ping")
async def ping():
    return {"message": "pong", "connections": len(gps_manager.connections)}


# ──────────────────────────────────────────────
# WebSocket — GPS 同步
# ──────────────────────────────────────────────
@app.websocket("/ws/gps")
async def ws_gps(ws: WebSocket):
    await gps_manager.connect(ws)
    device_id: Optional[str] = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            # ── 裝置註冊 ─────────────────────────────
            if msg_type == "register-device":
                device_id = msg.get("deviceId") or f"auto-{uuid.uuid4().hex[:8]}"
                name = msg.get("deviceName", "Unknown Device")
                gps_manager.register(device_id, ws, name)
                await ws.send_text(json.dumps({
                    "type": "device-registered",
                    "deviceId": device_id,
                    "deviceName": name,
                    "timestamp": time.time()
                }))
                continue

            if not device_id:
                continue

            # ── 更新裝置名稱 ──────────────────────────
            if msg_type == "update-device-name":
                new_name = msg.get("deviceName", "")
                if new_name:
                    gps_manager.names[device_id] = new_name
                    await gps_manager.broadcast(json.dumps({
                        "type": "device-name-updated",
                        "deviceId": device_id,
                        "deviceName": new_name,
                        "timestamp": time.time()
                    }))
                continue

            # ── 清除軌跡指令 ──────────────────────────
            if msg_type == "clear-path":
                await gps_manager.broadcast_except(json.dumps({
                    "type": "clear-path",
                    "deviceId": device_id,
                    "deviceName": gps_manager.names.get(device_id, ""),
                    "timestamp": time.time()
                }), device_id)
                continue

            # ── GPS 資料 ──────────────────────────────
            if msg.get("lat") is not None and msg.get("lon") is not None:
                payload = {
                    "lat": msg["lat"],
                    "lon": msg["lon"],
                    "alt": msg.get("alt", 0),
                    "accuracy": msg.get("accuracy", 999),
                    "deviceId": msg.get("deviceId", device_id),
                    "deviceName": gps_manager.names.get(device_id, msg.get("deviceName", "")),
                    "deviceType": msg.get("deviceType", "unknown"),
                    "timestamp": msg.get("timestamp", time.time())
                }
                gps_manager.update_gps(device_id, payload)
                await gps_manager.broadcast(json.dumps(payload))
                continue

            # ── 其他訊息直接廣播 ──────────────────────
            msg.setdefault("deviceId", device_id)
            msg.setdefault("deviceName", gps_manager.names.get(device_id, ""))
            await gps_manager.broadcast(json.dumps(msg))

    except WebSocketDisconnect:
        if device_id:
            # 廣播斷線事件
            await gps_manager.broadcast(json.dumps({
                "type": "device-disconnected",
                "deviceId": device_id,
                "deviceName": gps_manager.names.get(device_id, ""),
                "timestamp": datetime.now().isoformat()
            }))
            gps_manager.disconnect(device_id)
    except Exception as e:
        logger.error(f"❌ WebSocket 錯誤: {e}")
        if device_id:
            gps_manager.disconnect(device_id)


# ──────────────────────────────────────────────
# REST — 取得所有裝置 GPS
# ──────────────────────────────────────────────
@app.get("/api/gps/devices")
async def get_devices():
    result = {
        did: {**data, "deviceName": gps_manager.names.get(did, "")}
        for did, data in gps_manager.gps_data.items()
    }
    return {"devices": result, "count": len(result)}


# ──────────────────────────────────────────────
# 照片上傳
# ──────────────────────────────────────────────
def _load_photos() -> list:
    if PHOTOS_JSON.exists():
        try:
            return json.loads(PHOTOS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_photos(photos: list):
    PHOTOS_JSON.write_text(json.dumps(photos, ensure_ascii=False, indent=2), encoding="utf-8")


@app.post("/api/upload-photo")
async def upload_photo(
    photo: UploadFile = File(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    altitude: Optional[float] = Form(None),
    deviceId: Optional[str] = Form(None),
):
    try:
        content = await photo.read()
        if len(content) > 10 * 1024 * 1024:
            return JSONResponse({"success": False, "error": "檔案超過 10MB 限制"}, status_code=413)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{photo.filename}"
        (UPLOAD_DIR / filename).write_bytes(content)

        record = {
            "filename": filename,
            "url": f"/uploads/{filename}",
            "timestamp": ts,
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "deviceId": deviceId,
        }

        photos = _load_photos()
        photos.insert(0, record)
        _save_photos(photos)

        # 廣播給所有 WebSocket 連線
        await gps_manager.broadcast(json.dumps({
            "type": "photo-upload",
            **record
        }))

        logger.info(f"📸 照片已儲存: {filename}  deviceId={deviceId}")
        return JSONResponse({"success": True, **record})

    except Exception as e:
        logger.error(f"❌ 照片上傳失敗: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/photo-history")
async def photo_history():
    photos = _load_photos()
    return {"success": True, "photos": photos, "count": len(photos)}


@app.delete("/api/delete-photo/{filename}")
async def delete_photo(filename: str):
    try:
        path = UPLOAD_DIR / filename
        if path.exists():
            path.unlink()

        photos = [p for p in _load_photos() if p.get("filename") != filename]
        _save_photos(photos)

        await gps_manager.broadcast(json.dumps({
            "type": "photo_deleted",
            "filename": filename,
            "timestamp": datetime.now().isoformat()
        }))

        return {"success": True, "filename": filename}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ──────────────────────────────────────────────
# Sionna 無線模擬 API
# ──────────────────────────────────────────────

@app.get("/api/sionna/status")
async def sionna_status():
    """Check if Sionna is installed and usable."""
    import traceback
    llvm_path = os.environ.get("DRJIT_LIBLLVM_PATH", "NOT SET")
    try:
        import sionna  # noqa: F401
        from app.sionna_service import _load_sionna
        _load_sionna()
        return {"available": True, "version": getattr(sionna, "__version__", "unknown"), "llvm_path": llvm_path}
    except ImportError as e:
        return {"available": False, "version": None, "llvm_path": llvm_path, "error": str(e), "trace": traceback.format_exc()}


@app.get("/api/sionna/sinr-map")
async def sionna_sinr_map(
    sinr_vmin: float = Query(default=-20.0, description="SINR 色階下限 (dB)"),
    sinr_vmax: float = Query(default=40.0,  description="SINR 色階上限 (dB)"),
    cell_size: float = Query(default=2.0,   description="採樣格子大小 (m)"),
    samples_per_tx: int = Query(default=1000000, description="每個 TX 的採樣數"),
):
    """Generate SINR coverage map and return the PNG."""
    try:
        from app.sionna_service import generate_sinr_map, SINR_MAP_PATH
        await generate_sinr_map(
            sinr_vmin=sinr_vmin,
            sinr_vmax=sinr_vmax,
            cell_size=cell_size,
            samples_per_tx=samples_per_tx,
        )
        if not os.path.isfile(SINR_MAP_PATH):
            return JSONResponse({"error": "圖檔生成失敗，請查看後端 log"}, status_code=500)
        return FileResponse(SINR_MAP_PATH, media_type="image/png", filename="sinr_map.png")
    except ImportError as e:
        logger.error(f"Sionna ImportError (sinr-map): {e}")
        return JSONResponse({"error": "Sionna 未安裝，請先執行 pip install sionna"}, status_code=503)


@app.get("/api/sionna/cfr-plot")
async def sionna_cfr_plot():
    """Generate Channel Frequency Response plot and return the PNG."""
    try:
        from app.sionna_service import generate_cfr_plot, CFR_PLOT_PATH
        await generate_cfr_plot()
        if not os.path.isfile(CFR_PLOT_PATH):
            return JSONResponse({"error": "圖檔生成失敗，請查看後端 log"}, status_code=500)
        return FileResponse(CFR_PLOT_PATH, media_type="image/png", filename="cfr_plot.png")
    except ImportError:
        return JSONResponse({"error": "Sionna 未安裝，請先執行 pip install sionna"}, status_code=503)
    except Exception as e:
        logger.error(f"CFR plot error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/sionna/doppler")
async def sionna_doppler():
    """Generate Delay-Doppler plot and return the PNG."""
    try:
        from app.sionna_service import generate_doppler_plot, DOPPLER_PLOT_PATH
        await generate_doppler_plot()
        if not os.path.isfile(DOPPLER_PLOT_PATH):
            return JSONResponse({"error": "圖檔生成失敗，請查看後端 log"}, status_code=500)
        return FileResponse(DOPPLER_PLOT_PATH, media_type="image/png", filename="doppler_plot.png")
    except ImportError:
        return JSONResponse({"error": "Sionna 未安裝，請先執行 pip install sionna"}, status_code=503)
    except Exception as e:
        logger.error(f"Doppler plot error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/sionna/channel-response")
async def sionna_channel_response():
    """Generate Channel Impulse Response plot and return the PNG."""
    try:
        from app.sionna_service import generate_channel_response, CHANNEL_RESP_PATH
        await generate_channel_response()
        if not os.path.isfile(CHANNEL_RESP_PATH):
            return JSONResponse({"error": "圖檔生成失敗，請查看後端 log"}, status_code=500)
        return FileResponse(CHANNEL_RESP_PATH, media_type="image/png", filename="channel_response.png")
    except ImportError:
        return JSONResponse({"error": "Sionna 未安裝，請先執行 pip install sionna"}, status_code=503)
    except Exception as e:
        logger.error(f"Channel response error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
from pydantic import BaseModel, Field
from typing import List
import asyncio
from fastapi import HTTPException
from fastapi.responses import Response

class DeviceIn(BaseModel):
    name: str
    role: str
    x: float
    y: float
    z: float
    power_dbm: Optional[float] = Field(default=None)

class SimulateRequest(BaseModel):
    scene: str
    map_type: str
    cell_size: float = Field(default=4.0, gt=0)
    samples_per_tx: int = Field(default=1000000, ge=10000)
    devices: List[DeviceIn]

@app.post("/api/simulate")
async def simulate(req: SimulateRequest):
    # Determine the absolute path for the XML properly from this main.py file
    scene_name = req.scene.upper()
    scene_xml = BASE_DIR / "static" / "scenes" / scene_name / f"{scene_name}.xml"
    
    if not scene_xml.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Scene XML not found: {scene_xml}",
        )

    output_dir = str(BASE_DIR / "static" / "maps" / req.scene.lower())
    os.makedirs(output_dir, exist_ok=True)

    devices_dicts = [
        {
            "name": d.name,
            "role": d.role,
            "x": d.x,
            "y": d.y,
            "z": d.z,
            **({"power_dbm": d.power_dbm} if d.power_dbm is not None else {}),
        }
        for d in req.devices
    ]

    logger.info(
        "Simulation request: scene=%s, map_type=%s, devices=%d",
        req.scene, req.map_type, len(devices_dicts),
    )

    try:
        loop = asyncio.get_event_loop()

        image_bytes: bytes = await loop.run_in_executor(
            None,
            _run_generate_maps,
            str(scene_xml),
            devices_dicts,
            output_dir,
            req.scene,
            req.map_type,
            req.cell_size,
            req.samples_per_tx,
        )
    except Exception as exc:
        logger.exception("Simulation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{req.map_type}_map.png"'},
    )

def _run_generate_maps(
    scene_xml: str,
    devices: list,
    output_dir: str,
    scene_name: str,
    map_type: str,
    cell_size: float,
    samples_per_tx: int,
) -> bytes:
    from app.sionna_service_lite import generate_maps
    return generate_maps(
        scene_xml_path=scene_xml,
        devices=devices,
        output_dir=output_dir,
        scene_name=scene_name,
        map_type=map_type,
        cell_size=cell_size,
        samples_per_tx=samples_per_tx,
    )
