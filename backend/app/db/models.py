"""SQLAlchemy 2.x ma'lumotlar bazasi modellari (SQLite STRICT jadvallar).

Ixcham ustun turlari: ID — INTEGER PK, vaqt — INTEGER epoch, enum — kichik INTEGER,
bayroq — 0/1, qiymat — REAL, xesh — 32 baytli BLOB. Rasterlar diskda, bazada faqat yo'li.
"""

from sqlalchemy import BLOB, INTEGER, REAL, TEXT, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STRICT = {"sqlite_strict": True}


class Base(DeclarativeBase):
    """Barcha modellar uchun asosiy sinf."""


class RunModel(Base):
    """Rekognossirovka jarayoni yozuvi va uning barmoq izi."""

    __tablename__ = "runs"
    # AUTOINCREMENT: o'chirilgan run ID lari qayta ishlatilmaydi (API jurnali run_id bo'yicha bog'langan)
    __table_args__ = (Index("ix_runs_fingerprint", "fingerprint"), {**STRICT, "sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    fingerprint: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    status: Mapped[int] = mapped_column(INTEGER, nullable=False)
    aoi_geojson: Mapped[str] = mapped_column(TEXT, nullable=False)
    area_km2: Mapped[float] = mapped_column(REAL, nullable=False)
    grid_json: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    settings_json: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[int] = mapped_column(INTEGER, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    error_code: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    failover: Mapped[int] = mapped_column(INTEGER, nullable=False, default=0)

    scenes: Mapped[list["SceneModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    layers: Mapped[list["LayerModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    class_areas: Mapped[list["ClassAreaModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    weather_records: Mapped[list["WeatherModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    reports: Mapped[list["ReportModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class SceneModel(Base):
    """Topilgan sun'iy yo'ldosh kadrlari (scene) metama'lumotlari."""

    __tablename__ = "scenes"
    __table_args__ = (Index("ix_scenes_run", "run_id"), STRICT)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str] = mapped_column(TEXT, nullable=False)
    sensor: Mapped[int] = mapped_column(INTEGER, nullable=False)
    platform: Mapped[str] = mapped_column(TEXT, nullable=False)
    dataset: Mapped[str] = mapped_column(TEXT, nullable=False)
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    obs_time: Mapped[int] = mapped_column(INTEGER, nullable=False)  # mozaika kuzatuvi vaqti
    cloud_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    orbit_pass: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    used: Mapped[int] = mapped_column(INTEGER, nullable=False, default=1)

    run: Mapped["RunModel"] = relationship(back_populates="scenes")


class LayerModel(Base):
    """Hisoblangan raster qatlami (bitta sana, bitta mahsulot)."""

    __tablename__ = "layers"
    __table_args__ = (
        UniqueConstraint("run_id", "name", "acq_time", name="uq_layer"),
        Index("ix_layers_run", "run_id"),
        STRICT,
    )

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    kind: Mapped[int] = mapped_column(INTEGER, nullable=False)
    sensor: Mapped[int] = mapped_column(INTEGER, nullable=False)
    dataset: Mapped[str] = mapped_column(TEXT, nullable=False)
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    prev_time: Mapped[int | None] = mapped_column(INTEGER, nullable=True)  # o'zgarish qatlamlari
    scene_ids: Mapped[str] = mapped_column(TEXT, nullable=False)  # JSON ro'yxat
    file_path: Mapped[str] = mapped_column(TEXT, nullable=False)
    unit: Mapped[str] = mapped_column(TEXT, nullable=False, default="")
    min_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    max_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    valid_pct: Mapped[float] = mapped_column(REAL, nullable=False)
    cloud_masked_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    quality_flag: Mapped[int] = mapped_column(INTEGER, nullable=False)

    run: Mapped["RunModel"] = relationship(back_populates="layers")
    stats: Mapped["LayerStatsModel | None"] = relationship(
        back_populates="layer", cascade="all, delete-orphan", uselist=False, passive_deletes=True
    )


class LayerStatsModel(Base):
    """Qatlam piksellari statistikasi (faqat AOI ichidagi yaroqli piksellar bo'yicha)."""

    __tablename__ = "layer_stats"
    __table_args__ = (STRICT,)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    layer_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("layers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    count: Mapped[int] = mapped_column(INTEGER, nullable=False)
    mean_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    std_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    median_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    p10: Mapped[float | None] = mapped_column(REAL, nullable=True)
    p90: Mapped[float | None] = mapped_column(REAL, nullable=True)

    layer: Mapped["LayerModel"] = relationship(back_populates="stats")


class ClassAreaModel(Base):
    """Yer qoplami sinflari bo'yicha maydon taqsimoti (har bir sana uchun)."""

    __tablename__ = "class_areas"
    __table_args__ = (Index("ix_class_areas_run", "run_id"), STRICT)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    class_code: Mapped[int] = mapped_column(INTEGER, nullable=False)
    pixel_count: Mapped[int] = mapped_column(INTEGER, nullable=False)
    area_m2: Mapped[float] = mapped_column(REAL, nullable=False)
    pct: Mapped[float] = mapped_column(REAL, nullable=False)
    mean_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)

    run: Mapped["RunModel"] = relationship(back_populates="class_areas")


class WeatherModel(Base):
    """Ob-havo ko'rsatkichlari: AOI bo'yicha o'rtacha, minimal va maksimal (manba va vaqt bilan)."""

    __tablename__ = "weather"
    __table_args__ = (Index("ix_weather_run", "run_id"), STRICT)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[int] = mapped_column(INTEGER, nullable=False)
    ts: Mapped[int] = mapped_column(INTEGER, nullable=False)  # qiymat tegishli vaqt (UTC)
    period_s: Mapped[int] = mapped_column(INTEGER, nullable=False)  # yog'in oralig'i (soniya)
    issued_ts: Mapped[int | None] = mapped_column(INTEGER, nullable=True)  # GFS run vaqti
    is_forecast: Mapped[int] = mapped_column(INTEGER, nullable=False, default=0)
    temp_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    temp_min_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    temp_max_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    dewpoint_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    rh_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    precip_mm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    precip_min_mm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    precip_max_mm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_min_ms: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_max_ms: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_deg: Mapped[float | None] = mapped_column(REAL, nullable=True)
    cloud_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    soil_moisture: Mapped[float | None] = mapped_column(REAL, nullable=True)

    run: Mapped["RunModel"] = relationship(back_populates="weather_records")


class ReportModel(Base):
    """AI hisoboti: har bir barmoq izi uchun ko'pi bilan bitta (muvaffaqiyatsiz bo'lsa qayta urinish mumkin)."""

    __tablename__ = "reports"
    __table_args__ = (STRICT,)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[bytes] = mapped_column(BLOB, nullable=False, unique=True)
    status: Mapped[int] = mapped_column(INTEGER, nullable=False)
    provider: Mapped[str] = mapped_column(TEXT, nullable=False)
    model: Mapped[str] = mapped_column(TEXT, nullable=False)
    content_md: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    error: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    attempts: Mapped[int] = mapped_column(INTEGER, nullable=False, default=1)
    created_at: Mapped[int] = mapped_column(INTEGER, nullable=False)

    run: Mapped["RunModel"] = relationship(back_populates="reports")


class SettingsModel(Base):
    """Tizim sozlamalari (yagona qator, id = 1)."""

    __tablename__ = "settings"
    __table_args__ = (STRICT,)

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, default=1)
    lookback_days: Mapped[int] = mapped_column(INTEGER, nullable=False)
    weather_past_days: Mapped[int] = mapped_column(INTEGER, nullable=False)
    weather_forecast_days: Mapped[int] = mapped_column(INTEGER, nullable=False)
    max_scene_cloud_pct: Mapped[float] = mapped_column(REAL, nullable=False)
    cloud_score_threshold: Mapped[float] = mapped_column(REAL, nullable=False)
    s1_orbit_pass: Mapped[str] = mapped_column(TEXT, nullable=False)
    analysis_resolution_m: Mapped[float] = mapped_column(REAL, nullable=False)
    max_aoi_km2: Mapped[float] = mapped_column(REAL, nullable=False)
    gee_request_timeout_s: Mapped[int] = mapped_column(INTEGER, nullable=False)
    gee_max_retries: Mapped[int] = mapped_column(INTEGER, nullable=False)
    gee_max_concurrency: Mapped[int] = mapped_column(INTEGER, nullable=False)
    ai_provider: Mapped[str] = mapped_column(TEXT, nullable=False)
    ai_model: Mapped[str] = mapped_column(TEXT, nullable=False)
    ai_history_size: Mapped[int] = mapped_column(INTEGER, nullable=False)
