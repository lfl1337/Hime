"""
Hardware monitoring service.

Collects GPU stats via pynvml and CPU/RAM stats via psutil.
Falls back gracefully if no NVIDIA GPU is present.
Persists stats to the hardware_stats SQLite table.
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
from pydantic import BaseModel

from ..config import settings

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class HardwareStats(BaseModel):
    timestamp: datetime

    # GPU
    gpu_name: str
    gpu_vram_used_mb: int
    gpu_vram_total_mb: int
    gpu_vram_pct: float
    gpu_utilization_pct: int
    gpu_memory_pct: int
    gpu_temp_celsius: int
    gpu_power_draw_w: float
    gpu_power_limit_w: float
    gpu_clock_mhz: int
    gpu_max_clock_mhz: int

    # CPU
    cpu_utilization_pct: float
    cpu_freq_mhz: float
    cpu_core_count: int

    # RAM
    ram_used_gb: float
    ram_total_gb: float
    ram_pct: float

    # Disk I/O
    disk_read_mb_s: float
    disk_write_mb_s: float


# ---------------------------------------------------------------------------
# pynvml state
# ---------------------------------------------------------------------------

_nvml_ok: bool = False
_gpu_handle = None


def _init_nvml() -> None:
    global _nvml_ok, _gpu_handle
    try:
        import pynvml
        pynvml.nvmlInit()
        _gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        _nvml_ok = True
    except Exception:
        _nvml_ok = False
        _gpu_handle = None


_nvml_initialized = False


def _ensure_nvml() -> None:
    global _nvml_initialized
    if not _nvml_initialized:
        _init_nvml()
        _nvml_initialized = True


# ---------------------------------------------------------------------------
# DB path helper
# ---------------------------------------------------------------------------

def _db_path() -> str:
    """Extract the filesystem path from the db_url (sqlite+aiosqlite:///path)."""
    url = settings.db_url
    # "sqlite+aiosqlite:///./hime.db"  or  "sqlite+aiosqlite:///C:/..."
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        raw = url[len(prefix):]
        # Relative path starting with "./" → resolve from CWD
        if raw.startswith("./") or not Path(raw).is_absolute():
            return str(Path(raw))
        return raw
    return "hime.db"


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_hardware_stats() -> HardwareStats:
    """Collect current hardware stats. Never raises — falls back to zeros on error."""
    _ensure_nvml()

    now = datetime.now(tz=timezone.utc)

    # --- GPU via pynvml ---
    gpu_name = "N/A"
    gpu_vram_used_mb = 0
    gpu_vram_total_mb = 0
    gpu_vram_pct = 0.0
    gpu_utilization_pct = 0
    gpu_memory_pct = 0
    gpu_temp_celsius = 0
    gpu_power_draw_w = 0.0
    gpu_power_limit_w = 0.0
    gpu_clock_mhz = 0
    gpu_max_clock_mhz = 0

    if _nvml_ok and _gpu_handle is not None:
        try:
            import pynvml
            gpu_name = pynvml.nvmlDeviceGetName(_gpu_handle)
            if isinstance(gpu_name, bytes):
                gpu_name = gpu_name.decode("utf-8", errors="replace")

            mem = pynvml.nvmlDeviceGetMemoryInfo(_gpu_handle)
            gpu_vram_used_mb = mem.used // (1024 * 1024)
            gpu_vram_total_mb = mem.total // (1024 * 1024)
            gpu_vram_pct = round(mem.used / mem.total * 100.0, 1) if mem.total > 0 else 0.0

            util = pynvml.nvmlDeviceGetUtilizationRates(_gpu_handle)
            gpu_utilization_pct = util.gpu
            gpu_memory_pct = util.memory

            gpu_temp_celsius = pynvml.nvmlDeviceGetTemperature(
                _gpu_handle, pynvml.NVML_TEMPERATURE_GPU
            )

            try:
                gpu_power_draw_w = pynvml.nvmlDeviceGetPowerUsage(_gpu_handle) / 1000.0
                gpu_power_limit_w = pynvml.nvmlDeviceGetPowerManagementLimit(_gpu_handle) / 1000.0
            except pynvml.NVMLError:
                pass

            try:
                gpu_clock_mhz = pynvml.nvmlDeviceGetClockInfo(
                    _gpu_handle, pynvml.NVML_CLOCK_GRAPHICS
                )
                gpu_max_clock_mhz = pynvml.nvmlDeviceGetMaxClockInfo(
                    _gpu_handle, pynvml.NVML_CLOCK_GRAPHICS
                )
            except pynvml.NVMLError:
                pass

        except Exception:
            pass

    # --- CPU via psutil ---
    cpu_utilization_pct = psutil.cpu_percent(interval=None)
    freq = psutil.cpu_freq()
    cpu_freq_mhz = freq.current if freq else 0.0
    cpu_core_count = psutil.cpu_count(logical=True) or 1

    # --- RAM via psutil ---
    vm = psutil.virtual_memory()
    ram_used_gb = vm.used / (1024 ** 3)
    ram_total_gb = vm.total / (1024 ** 3)
    ram_pct = vm.percent

    # --- Disk I/O (two samples, 0.2 s apart) ---
    disk_read_mb_s = 0.0
    disk_write_mb_s = 0.0
    try:
        io1 = psutil.disk_io_counters()
        time.sleep(0.2)
        io2 = psutil.disk_io_counters()
        if io1 and io2:
            disk_read_mb_s = round((io2.read_bytes - io1.read_bytes) / 0.2 / (1024 * 1024), 2)
            disk_write_mb_s = round((io2.write_bytes - io1.write_bytes) / 0.2 / (1024 * 1024), 2)
    except Exception:
        pass

    return HardwareStats(
        timestamp=now,
        gpu_name=gpu_name,
        gpu_vram_used_mb=gpu_vram_used_mb,
        gpu_vram_total_mb=gpu_vram_total_mb,
        gpu_vram_pct=gpu_vram_pct,
        gpu_utilization_pct=gpu_utilization_pct,
        gpu_memory_pct=gpu_memory_pct,
        gpu_temp_celsius=gpu_temp_celsius,
        gpu_power_draw_w=round(gpu_power_draw_w, 1),
        gpu_power_limit_w=round(gpu_power_limit_w, 1),
        gpu_clock_mhz=gpu_clock_mhz,
        gpu_max_clock_mhz=gpu_max_clock_mhz,
        cpu_utilization_pct=round(cpu_utilization_pct, 1),
        cpu_freq_mhz=round(cpu_freq_mhz, 0),
        cpu_core_count=cpu_core_count,
        ram_used_gb=round(ram_used_gb, 2),
        ram_total_gb=round(ram_total_gb, 2),
        ram_pct=round(ram_pct, 1),
        disk_read_mb_s=disk_read_mb_s,
        disk_write_mb_s=disk_write_mb_s,
    )


# ---------------------------------------------------------------------------
# Memory detail
# ---------------------------------------------------------------------------

class MemoryDetail(BaseModel):
    process_rss_mb: float
    process_vms_mb: float
    system_total_gb: float
    system_available_gb: float
    system_used_pct: float
    pagefile_total_gb: float
    pagefile_used_gb: float
    pagefile_used_pct: float
    top_processes: list[dict]  # [{name, pid, rss_mb}]


def get_memory_detail() -> MemoryDetail:
    """Collect detailed memory breakdown: Python process, system, pagefile, top processes."""
    import os
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    me = psutil.Process(os.getpid())
    mi = me.memory_info()
    procs = []
    for p in psutil.process_iter(['name', 'pid', 'memory_info']):
        try:
            rss = p.info['memory_info'].rss / 1024 / 1024
            procs.append({'name': p.info['name'], 'pid': p.info['pid'], 'rss_mb': round(rss, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    top5 = sorted(procs, key=lambda x: x['rss_mb'], reverse=True)[:5]
    return MemoryDetail(
        process_rss_mb=round(mi.rss / 1024 / 1024, 1),
        process_vms_mb=round(mi.vms / 1024 / 1024, 1),
        system_total_gb=round(vm.total / 1024**3, 1),
        system_available_gb=round(vm.available / 1024**3, 1),
        system_used_pct=round(vm.percent, 1),
        pagefile_total_gb=round(sw.total / 1024**3, 1),
        pagefile_used_gb=round(sw.used / 1024**3, 1),
        pagefile_used_pct=round(sw.percent, 1),
        top_processes=top5,
    )


def save_hardware_stats(stats: HardwareStats) -> None:
    """Insert one hardware stats row into SQLite (sync, thread-safe)."""
    db = _db_path()
    try:
        con = sqlite3.connect(db, timeout=5)
        con.execute(
            """
            INSERT INTO hardware_stats (
                timestamp, gpu_name,
                gpu_vram_used_mb, gpu_vram_total_mb, gpu_vram_pct,
                gpu_utilization_pct, gpu_memory_pct,
                gpu_temp_celsius, gpu_power_draw_w, gpu_power_limit_w,
                gpu_clock_mhz, gpu_max_clock_mhz,
                cpu_utilization_pct, cpu_freq_mhz, cpu_core_count,
                ram_used_gb, ram_total_gb, ram_pct,
                disk_read_mb_s, disk_write_mb_s
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stats.timestamp.isoformat(),
                stats.gpu_name,
                stats.gpu_vram_used_mb, stats.gpu_vram_total_mb, stats.gpu_vram_pct,
                stats.gpu_utilization_pct, stats.gpu_memory_pct,
                stats.gpu_temp_celsius, stats.gpu_power_draw_w, stats.gpu_power_limit_w,
                stats.gpu_clock_mhz, stats.gpu_max_clock_mhz,
                stats.cpu_utilization_pct, stats.cpu_freq_mhz, stats.cpu_core_count,
                stats.ram_used_gb, stats.ram_total_gb, stats.ram_pct,
                stats.disk_read_mb_s, stats.disk_write_mb_s,
            ),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def cleanup_old_hardware_stats(hours: int = 1) -> None:
    """Delete hardware_stats rows older than N hours (sync, thread-safe)."""
    db = _db_path()
    try:
        con = sqlite3.connect(db, timeout=5)
        # Ensure timestamp index exists (idempotent, cheap after first run)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_hw_timestamp ON hardware_stats(timestamp)"
        )
        con.execute(
            "DELETE FROM hardware_stats WHERE timestamp < datetime('now', ? || ' hours')",
            (f"-{hours}",),
        )
        # Emergency cap: if table has grown unexpectedly, keep only newest 1000 rows
        row = con.execute("SELECT COUNT(*) FROM hardware_stats").fetchone()
        if row and row[0] > 10000:
            con.execute(
                "DELETE FROM hardware_stats WHERE id NOT IN "
                "(SELECT id FROM hardware_stats ORDER BY timestamp DESC LIMIT 1000)"
            )
        con.commit()
        con.close()
    except Exception:
        pass


def get_hardware_history(minutes: int = 10) -> list[HardwareStats]:
    """Return the last N minutes of hardware stats from SQLite."""
    db = _db_path()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)).isoformat()
    try:
        con = sqlite3.connect(db, timeout=5)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM ("
            "SELECT * FROM hardware_stats WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 120"
            ") ORDER BY timestamp ASC",
            (cutoff,),
        ).fetchall()
        con.close()
        result = []
        for row in rows:
            try:
                result.append(HardwareStats(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    gpu_name=row["gpu_name"] or "N/A",
                    gpu_vram_used_mb=row["gpu_vram_used_mb"] or 0,
                    gpu_vram_total_mb=row["gpu_vram_total_mb"] or 0,
                    gpu_vram_pct=row["gpu_vram_pct"] or 0.0,
                    gpu_utilization_pct=row["gpu_utilization_pct"] or 0,
                    gpu_memory_pct=row["gpu_memory_pct"] or 0,
                    gpu_temp_celsius=row["gpu_temp_celsius"] or 0,
                    gpu_power_draw_w=row["gpu_power_draw_w"] or 0.0,
                    gpu_power_limit_w=row["gpu_power_limit_w"] or 0.0,
                    gpu_clock_mhz=row["gpu_clock_mhz"] or 0,
                    gpu_max_clock_mhz=row["gpu_max_clock_mhz"] or 0,
                    cpu_utilization_pct=row["cpu_utilization_pct"] or 0.0,
                    cpu_freq_mhz=row["cpu_freq_mhz"] or 0.0,
                    cpu_core_count=row["cpu_core_count"] or 1,
                    ram_used_gb=row["ram_used_gb"] or 0.0,
                    ram_total_gb=row["ram_total_gb"] or 0.0,
                    ram_pct=row["ram_pct"] or 0.0,
                    disk_read_mb_s=row["disk_read_mb_s"] or 0.0,
                    disk_write_mb_s=row["disk_write_mb_s"] or 0.0,
                ))
            except Exception:
                continue
        return result
    except Exception:
        return []


def vacuum_hardware_db() -> None:
    """Run VACUUM on the hardware SQLite database to reclaim disk space after DELETEs."""
    db = _db_path()
    try:
        con = sqlite3.connect(db, timeout=30)
        con.execute("VACUUM")
        con.close()
    except Exception:
        pass
