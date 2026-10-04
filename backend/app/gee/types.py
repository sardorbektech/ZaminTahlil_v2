"""Ma'lumot manbasi (DataSource) interfeysi va umumiy turlar.

Quvur faqat shu interfeys orqali ishlaydi: haqiqiy ishda GEESource, testlarda soxta manba.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from backend.app.core.run_settings import RunSettings
from backend.app.db.enums import SensorKind
from backend.app.gee.gateway import CallContext
from backend.app.pipeline.grid import Grid


@dataclass(frozen=True)
class SceneInfo:
    """Bitta sun'iy yo'ldosh kadri (faqat metama'lumot)."""

    scene_id: str
    sensor: SensorKind
    platform: str
    dataset: str
    acq_time: int
    cloud_pct: float | None = None
    orbit_pass: str | None = None


@dataclass
class Observation:
    """Bir sensorning bir UTC kundagi kadrlari — bitta mozaika kuzatuvi."""

    sensor: SensorKind
    obs_time: int  # eng erta kadr vaqti
    scenes: list[SceneInfo]

    @property
    def key(self) -> str:
        return f"{self.sensor.name.lower()}_{self.obs_time}"

    @property
    def scene_ids(self) -> list[str]:
        return [s.scene_id for s in self.scenes]

    @property
    def datasets(self) -> list[str]:
        return sorted({s.dataset for s in self.scenes})

    @property
    def last_time(self) -> int:
        return max(s.acq_time for s in self.scenes)


@dataclass
class StaticProduct:
    """Sana bo'yicha guruhlanmaydigan mahsulot (DEM yoki eng so'nggi SMAP)."""

    sensor: SensorKind
    dataset: str
    acq_time: int  # mahsulot vaqti (SMAP: kuzatuv vaqti; DEM: eng so'nggi plitka vaqti)
    item_ids: list[str] = field(default_factory=list)
    time_range: tuple[int, int] | None = None


@dataclass
class Discovery:
    """3-bosqich natijasi: kadrlar va statik mahsulotlar."""

    scenes: list[SceneInfo]
    dem: StaticProduct | None
    smap: StaticProduct | None


@dataclass
class WeatherBundle:
    """Ob-havo: soatlik qatorlar (ERA5, GFS analiz/prognoz), CHIRPS kunlik, SMAP qatori."""

    hourly: list[dict[str, Any]]
    chirps_daily: list[dict[str, Any]]
    smap_series: list[dict[str, Any]]
    gfs_run_ts: int | None = None
    era5_last_ts: int | None = None
    notes: list[str] = field(default_factory=list)


class DataSource(Protocol):
    """Quvur foydalanadigan ma'lumot manbasi interfeysi."""

    def is_configured(self) -> bool: ...

    async def discover(
        self, aoi: dict[str, Any], start_ts: int, end_ts: int, s: RunSettings, ctx: CallContext
    ) -> Discovery: ...

    async def download_observation(
        self, obs: Observation, grid: Grid, s: RunSettings, ctx: CallContext
    ) -> dict[str, np.ndarray]: ...

    async def download_static(
        self, product: StaticProduct, grid: Grid, s: RunSettings, ctx: CallContext
    ) -> dict[str, np.ndarray]: ...

    async def fetch_weather(
        self, aoi: dict[str, Any], area_km2: float, now: int, s: RunSettings, ctx: CallContext
    ) -> WeatherBundle: ...
