"""Run katalogi tuzilmasi va .npz/.json fayllari bilan ishlash.

data/runs/{run_id}/
    raw/{key}.npz       — yuklangan xom bandlar (fizik birliklarda, NaN — yo'q)
    derived/{key}.npz   — hisoblangan qatlamlar (har bir kuzatuv uchun)
    png/{name}_{ts}.png — shaffof PNG qatlamlar
    composite/          — so'rov bo'yicha yaratilgan kompozitlar (kesh)
    summary.json        — barcha raqamli natijalar (API va AI uchun)
"""

import json
import shutil
import struct
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.core import config


def run_dir(run_id: int) -> Path:
    return config.RUNS_DIR / str(run_id)


def raw_path(run_id: int, key: str) -> Path:
    return run_dir(run_id) / "raw" / f"{key}.npz"


def derived_path(run_id: int, key: str) -> Path:
    return run_dir(run_id) / "derived" / f"{key}.npz"


def png_path(run_id: int, name: str, ts: int) -> Path:
    return run_dir(run_id) / "png" / f"{name}_{ts}.png"


def composite_dir(run_id: int) -> Path:
    return run_dir(run_id) / "composite"


def summary_path(run_id: int) -> Path:
    return run_dir(run_id) / "summary.json"


def save_arrays(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Massivlarni SIQILMAGAN .npz ga yozadi (float32).

    Siqilmagan format nuqta so'rovida faqat kerakli piksellarni o'qish imkonini beradi
    (read_pixel), butun massivni ochmasdan.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez(tmp, **{k: np.asarray(v, dtype=np.float32) for k, v in arrays.items()})
    tmp.replace(path)


def read_pixel(path: Path, row: int, col: int) -> dict[str, float | None]:
    """Siqilmagan .npz dagi har bir massivdan bitta piksel qiymatini o'qiydi (NaN → None)."""
    out: dict[str, float | None] = {}
    with zipfile.ZipFile(path) as zf, open(path, "rb") as fh:
        for info in zf.infolist():
            if not info.filename.endswith(".npy") or info.compress_type != zipfile.ZIP_STORED:
                continue
            fh.seek(info.header_offset)
            hdr = fh.read(30)
            name_len, extra_len = struct.unpack("<HH", hdr[26:30])
            fh.seek(info.header_offset + 30 + name_len + extra_len)
            version = np.lib.format.read_magic(fh)
            if version == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(fh)
            else:
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(fh)
            if len(shape) != 2 or fortran or not (0 <= row < shape[0] and 0 <= col < shape[1]):
                continue
            fh.seek(fh.tell() + (row * shape[1] + col) * dtype.itemsize)
            v = float(np.frombuffer(fh.read(dtype.itemsize), dtype=dtype)[0])
            out[info.filename[:-4]] = None if np.isnan(v) else v
    return out


def load_arrays(path: Path, names: list[str] | None = None) -> dict[str, np.ndarray]:
    """.npz dan massivlarni o'qiydi (fayl yopiladi)."""
    with np.load(path) as data:
        keys = data.files if names is None else [n for n in names if n in data.files]
        return {k: data[k] for k in keys}


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def delete_run_dir(run_id: int) -> None:
    """Run katalogini to'liq o'chiradi (mavjud bo'lmasa — hech narsa qilmaydi)."""
    shutil.rmtree(run_dir(run_id), ignore_errors=True)
