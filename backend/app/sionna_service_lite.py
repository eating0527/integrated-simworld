"""
sionna_service_lite.py
======================
Minimal Sionna RT-based map generation for sim-world-lite.
Extracted from sim-world's sionna_service.py, stripped of all DB / SQLAlchemy
dependencies — devices are passed directly as plain dicts.

Coordinate convention
---------------------
The frontend (Three.js) uses a Y-up right-handed system:
  x → east, y → height (up), z → south

Sionna RT (Mitsuba 3) uses a Z-up right-handed system:
  x → east, y → north, z → height (up)

Conversion: [x_three, y_three, z_three] → [x_three, -z_three, y_three]
i.e. sionna_x = x, sionna_y = -z, sionna_z = y (height)

The RadioMapSolver computes a 2D horizontal map at a given altitude (sionna_z).
"""

import logging
import os
import pathlib
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports — deferred so the module can still be imported for
# type-checking even when Sionna / TF are not installed.
# ---------------------------------------------------------------------------

def _import_sionna():
    from sionna.rt import (  # type: ignore
        load_scene,
        Transmitter as SionnaTransmitter,
        Receiver as SionnaReceiver,
        PlanarArray,
        RadioMapSolver,
    )
    return load_scene, SionnaTransmitter, SionnaReceiver, PlanarArray, RadioMapSolver


try:
    from skimage.feature import peak_local_max  # type: ignore
    _HAS_SKIMAGE = True
except ImportError:
    _HAS_SKIMAGE = False
    logger.warning("scikit-image not available; CFAR peak detection will use fallback.")


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def threejs_to_sionna(x: float, y: float, z: float):
    """Convert Three.js (x, y_height, z) → Sionna RT (x, y_north, z_height)."""
    return [x, -z, y]


# ---------------------------------------------------------------------------
# Core map generation
# ---------------------------------------------------------------------------

ANTENNA_CONFIG = {
    "num_rows": 1,
    "num_cols": 1,
    "vertical_spacing": 0.5,
    "horizontal_spacing": 0.5,
    "pattern": "iso",
    "polarization": "V",
}


def generate_maps(
    *,
    scene_xml_path: str,
    devices: List[dict],
    output_dir: str,
    scene_name: str = "ntpu",
    map_type: str = "iss",          # "iss" | "tss" | "cfar"
    cell_size: float = 4.0,
    map_size: tuple = (512, 512),
    samples_per_tx: int = 10 ** 6,  # reduced for lite version
    altitude: float = 1.5,          # map altitude in metres (Sionna z)
    gaussian_sigma: float = 1.0,
    cfar_min_distance: int = 3,
    cfar_threshold_percentile: float = 99.5,
    frequency_hz: float = 1.5e9,
) -> str:
    """
    Run Sionna RadioMapSolver and generate the requested map type.

    Parameters
    ----------
    scene_xml_path : str
        Absolute path to the Sionna XML scene file.
    devices : list of dict
        Each dict: {name, role ('tx'|'rx'|'jammer'), x, y, z, power_dbm?}
        Coordinates are in Three.js convention.
    output_dir : str
        Directory in which to write the PNG (e.g. .../public/maps/ntpu/).
    map_type : str
        "iss"  → Interference Signal Strength heatmap
        "tss"  → Total Signal Strength heatmap
        "cfar" → ISS heatmap with CFAR peak markers overlaid
    Returns
    -------
    str  : absolute path of the written PNG file.
    """
    (
        load_scene,
        SionnaTransmitter,
        SionnaReceiver,
        PlanarArray,
        RadioMapSolver,
    ) = _import_sionna()

    os.makedirs(output_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # Separate devices by role
    # -----------------------------------------------------------------------
    tx_devices   = [d for d in devices if d["role"] == "tx"]
    rx_devices   = [d for d in devices if d["role"] == "rx"]
    jam_devices  = [d for d in devices if d["role"] == "jammer"]

    if not rx_devices:
        raise ValueError("At least one RX device is required.")

    rx = rx_devices[0]  # only one RX (UAV)

    # -----------------------------------------------------------------------
    # Load Sionna scene
    # -----------------------------------------------------------------------
    logger.info("Loading Sionna scene: %s", scene_xml_path)
    scene = load_scene(scene_xml_path)

    scene.tx_array = PlanarArray(**ANTENNA_CONFIG)
    scene.rx_array = PlanarArray(**ANTENNA_CONFIG)
    scene.frequency = frequency_hz

    # Clear any existing objects in the scene
    for name in list(scene.transmitters):
        scene.remove(name)
    for name in list(scene.receivers):
        scene.remove(name)

    # -----------------------------------------------------------------------
    # Add transmitters (TX + Jammer)
    # -----------------------------------------------------------------------
    all_tx_entries = []   # list of (SionnaTransmitter, role_str)
    idx_desired: List[int] = []
    idx_jammer: List[int] = []

    for i, d in enumerate(tx_devices):
        pos_sionna = threejs_to_sionna(d["x"], d["y"], d["z"])
        power = d.get("power_dbm", 20)
        tx = SionnaTransmitter(
            name=d["name"],
            position=pos_sionna,
            orientation=[0.0, 0.0, 0.0],
            power_dbm=float(power),
        )
        tx.role = "desired"
        scene.add(tx)
        all_tx_entries.append(tx)
        idx_desired.append(len(all_tx_entries) - 1)
        logger.info("Added TX '%s' at Sionna %s, %.1f dBm", d["name"], pos_sionna, power)

    for i, d in enumerate(jam_devices):
        pos_sionna = threejs_to_sionna(d["x"], d["y"], d["z"])
        power = d.get("power_dbm", 10)
        jammer = SionnaTransmitter(
            name=d["name"],
            position=pos_sionna,
            orientation=[0.0, 0.0, 0.0],
            power_dbm=float(power),
        )
        jammer.role = "jammer"
        scene.add(jammer)
        all_tx_entries.append(jammer)
        idx_jammer.append(len(all_tx_entries) - 1)
        logger.info("Added Jammer '%s' at Sionna %s, %.1f dBm", d["name"], pos_sionna, power)

    # -----------------------------------------------------------------------
    # Add receiver
    # -----------------------------------------------------------------------
    rx_pos_sionna = threejs_to_sionna(rx["x"], rx["y"], rx["z"])
    rx_obj = SionnaReceiver(name=rx["name"], position=rx_pos_sionna)
    scene.add(rx_obj)
    logger.info("Added RX '%s' at Sionna %s", rx["name"], rx_pos_sionna)

    # -----------------------------------------------------------------------
    # Run RadioMapSolver  (no center/size → auto-use scene bounding box)
    # -----------------------------------------------------------------------
    logger.info(
        "Running RadioMapSolver: cell_size=%s, samples=%s",
        cell_size, samples_per_tx,
    )
    rm_solver = RadioMapSolver()
    rm = rm_solver(
        scene,
        max_depth=5,
        samples_per_tx=samples_per_tx,
        cell_size=(cell_size, cell_size),
        refraction=False,
        specular_reflection=True,
        diffuse_reflection=True,
    )

    # -----------------------------------------------------------------------
    # Extract RSS per transmitter
    # -----------------------------------------------------------------------
    # rm.rss shape: (num_tx, H, W)  — power in Watts per cell
    WSS = rm.rss[:].numpy()   # (num_tx, H, W)

    TSS = np.sum(WSS, axis=0)  # Total Signal Strength

    DSS = (
        np.sum(WSS[idx_desired, :, :], axis=0)
        if idx_desired
        else np.zeros_like(TSS)
    )
    ISS = (
        np.sum(WSS[idx_jammer, :, :], axis=0)
        if idx_jammer
        else np.zeros_like(TSS)
    )

    # Convert to dBm
    def to_dbm(arr: np.ndarray) -> np.ndarray:
        return 10.0 * np.log10(np.maximum(arr, 1e-12) / 1e-3)

    iss_dbm = to_dbm(ISS)
    tss_dbm = to_dbm(TSS)

    # Cell centres for axis labels
    # Sionna 1.x: cell_centers shape is (num_cells_y, num_cells_x, 2)
    cc = rm.cell_centers.numpy()
    # Flatten to get unique sorted axis values
    x_coords = np.unique(cc[:, :, 0])
    y_coords = np.unique(cc[:, :, 1])

    # -----------------------------------------------------------------------
    # CFAR peak detection (on smoothed ISS)
    # -----------------------------------------------------------------------
    iss_smooth = gaussian_filter(iss_dbm, sigma=gaussian_sigma)
    peak_coords_list = []

    if map_type in ("cfar", "iss"):
        peak_coords_list = _detect_cfar_peaks(
            iss_smooth,
            min_distance=cfar_min_distance,
            threshold_percentile=cfar_threshold_percentile,
        )

    # -----------------------------------------------------------------------
    # Select data for requested map type
    # -----------------------------------------------------------------------
    if map_type == "iss":
        data = iss_smooth
        title = f"ISS Map — {scene_name.upper()}"
        cbar_label = "ISS (dBm)"
        cmap = "hot"
    elif map_type == "tss":
        data = gaussian_filter(tss_dbm, sigma=gaussian_sigma)
        title = f"TSS Map — {scene_name.upper()}"
        cbar_label = "TSS (dBm)"
        cmap = "viridis"
    else:  # cfar
        data = iss_smooth
        title = f"ISS+CFAR Map — {scene_name.upper()}"
        cbar_label = "ISS (dBm)"
        cmap = "hot"

    # -----------------------------------------------------------------------
    # Plot
    # -----------------------------------------------------------------------
    # Compute aspect ratio from actual data extent to avoid matplotlib
    # cropping to half the figure when map is not square
    x_range = abs(x_coords[-1] - x_coords[0]) or 1
    y_range = abs(y_coords[-1] - y_coords[0]) or 1
    fig_w = 9
    fig_h = max(6, fig_w * y_range / x_range)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(
        data,
        origin="lower",
        aspect="auto",
        cmap=cmap,
        extent=[x_coords[0], x_coords[-1], y_coords[0], y_coords[-1]],
    )
    plt.colorbar(im, ax=ax, label=cbar_label)
    ax.set_title(title, fontsize=13)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")

    # Mark TX, Jammer, RX positions on the map
    for d in tx_devices:
        ps = threejs_to_sionna(d["x"], d["y"], d["z"])
        ax.plot(ps[0], ps[1], "b^", markersize=10, label="TX")
    for d in jam_devices:
        ps = threejs_to_sionna(d["x"], d["y"], d["z"])
        ax.plot(ps[0], ps[1], "rs", markersize=10, label="Jammer")
    rx_ps = threejs_to_sionna(rx["x"], rx["y"], rx["z"])
    ax.plot(rx_ps[0], rx_ps[1], "g*", markersize=12, label="RX (UAV)")

    # Overlay CFAR peaks
    if map_type == "cfar" and peak_coords_list:
        for row, col in peak_coords_list:
            if 0 <= col < len(x_coords) and 0 <= row < len(y_coords):
                ax.plot(
                    x_coords[col],
                    y_coords[row],
                    "cx",
                    markersize=12,
                    markeredgewidth=2,
                    label="CFAR Peak",
                )

    # Deduplicate legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=8)

    # -----------------------------------------------------------------------
    # Save to memory buffer (avoid disk I/O race conditions)
    # -----------------------------------------------------------------------
    import io as _io
    buf = _io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    image_bytes = buf.read()
    buf.close()

    # Also write to disk for caching / debugging
    filename_map = {"iss": "iss_map.png", "tss": "tss_map.png", "cfar": "cfar_map.png"}
    out_path = os.path.join(output_dir, filename_map[map_type])
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    logger.info("Saved %s map to %s (%d bytes)", map_type.upper(), out_path, len(image_bytes))
    return image_bytes


# ---------------------------------------------------------------------------
# CFAR helpers
# ---------------------------------------------------------------------------

def _detect_cfar_peaks(
    iss_smooth: np.ndarray,
    min_distance: int = 3,
    threshold_percentile: float = 99.5,
) -> List[tuple]:
    """Return list of (row, col) peak coordinates detected by 2D-CFAR."""
    if _HAS_SKIMAGE:
        threshold_abs = np.percentile(iss_smooth, threshold_percentile)
        coords = peak_local_max(  # type: ignore[name-defined]
            iss_smooth,
            min_distance=min_distance,
            threshold_abs=float(threshold_abs),
        )
        return [(int(r), int(c)) for r, c in coords]
    else:
        # Fallback: sliding-window maximum
        local_max = maximum_filter(iss_smooth, size=max(3, min_distance * 2 + 1))
        threshold = np.percentile(iss_smooth, threshold_percentile)
        peak_mask = (iss_smooth == local_max) & (iss_smooth >= threshold)
        coords = np.argwhere(peak_mask)
        return [(int(r), int(c)) for r, c in coords]
