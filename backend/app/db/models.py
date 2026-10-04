"""SQLAlchemy 2.x ma'lumotlar bazasi modellari (SQLite STRICT)."""

from sqlalchemy import (
    BLOB,
    INTEGER,
    REAL,
    TEXT,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Barcha modellar uchun asosiy sinf."""

    pass


class RunModel(Base):
    """Rekognossirovka jarayoni yozuvi."""

    __tablename__ = "runs"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    fingerprint: Mapped[bytes] = mapped_column(BLOB, nullable=False, index=True)
    status: Mapped[int] = mapped_column(INTEGER, nullable=False, default=0)
    aoi_geojson: Mapped[str] = mapped_column(TEXT, nullable=False)
    area_km2: Mapped[float] = mapped_column(REAL, nullable=False)
    created_at: Mapped[int] = mapped_column(INTEGER, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(INTEGER, nullable=True)

    scenes: Mapped[list["SceneModel"]] = relationship(
        "SceneModel", back_populates="run", cascade="all, delete-orphan"
    )
    layers: Mapped[list["LayerModel"]] = relationship(
        "LayerModel", back_populates="run", cascade="all, delete-orphan"
    )
    class_areas: Mapped[list["ClassAreaModel"]] = relationship(
        "ClassAreaModel", back_populates="run", cascade="all, delete-orphan"
    )
    weather_records: Mapped[list["WeatherModel"]] = relationship(
        "WeatherModel", back_populates="run", cascade="all, delete-orphan"
    )


class SceneModel(Base):
    """Qabul qilingan sun'iy yo'ldosh kadrlari (scene) metama'lumotlari."""

    __tablename__ = "scenes"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[str] = mapped_column(TEXT, nullable=False)
    sensor: Mapped[int] = mapped_column(INTEGER, nullable=False)
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    cloud_pct: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)

    run: Mapped["RunModel"] = relationship("RunModel", back_populates="scenes")


class LayerModel(Base):
    """Hisoblangan raster qatlamlari."""

    __tablename__ = "layers"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[int] = mapped_column(INTEGER, nullable=False)
    sensor: Mapped[int] = mapped_column(INTEGER, nullable=False)
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    file_path: Mapped[str] = mapped_column(TEXT, nullable=False)
    min_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    max_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    valid_pct: Mapped[float] = mapped_column(REAL, nullable=False, default=100.0)
    quality_flag: Mapped[int] = mapped_column(INTEGER, nullable=False, default=0)

    run: Mapped["RunModel"] = relationship("RunModel", back_populates="layers")
    stats: Mapped["LayerStatsModel | None"] = relationship(
        "LayerStatsModel", back_populates="layer", cascade="all, delete-orphan", uselist=False
    )


class LayerStatsModel(Base):
    """Qatlam piksellari statistikasi."""

    __tablename__ = "layer_stats"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    layer_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("layers.id", ondelete="CASCADE"), nullable=False, unique=True)
    mean_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    std_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    median_val: Mapped[float | None] = mapped_column(REAL, nullable=True)
    p10: Mapped[float | None] = mapped_column(REAL, nullable=True)
    p90: Mapped[float | None] = mapped_column(REAL, nullable=True)

    layer: Mapped["LayerModel"] = relationship("LayerModel", back_populates="stats")


class ClassAreaModel(Base):
    """Yer qoplami sinflari bo'yicha maydon taqsimoti."""

    __tablename__ = "class_areas"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    acq_time: Mapped[int] = mapped_column(INTEGER, nullable=False)
    class_code: Mapped[int] = mapped_column(INTEGER, nullable=False)
    area_m2: Mapped[float] = mapped_column(REAL, nullable=False)
    pct: Mapped[float] = mapped_column(REAL, nullable=False)

    run: Mapped["RunModel"] = relationship("RunModel", back_populates="class_areas")


class WeatherModel(Base):
    """Ob-havo ko'rsatkichlari (soatlik va agregatlangan)."""

    __tablename__ = "weather"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[int] = mapped_column(INTEGER, nullable=False)
    ts: Mapped[int] = mapped_column(INTEGER, nullable=False)
    temp_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    dewpoint_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    precip_mm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_deg: Mapped[float | None] = mapped_column(REAL, nullable=True)
    soil_moisture: Mapped[float | None] = mapped_column(REAL, nullable=True)
    is_forecast: Mapped[int] = mapped_column(INTEGER, nullable=False, default=0)

    run: Mapped["RunModel"] = relationship("RunModel", back_populates="weather_records")


class ReportModel(Base):
    """AI tomonidan tuzilgan hisobot (fingerprint bo'yicha noyob)."""

    __tablename__ = "reports"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(INTEGER, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[bytes] = mapped_column(BLOB, nullable=False, unique=True, index=True)
    content_md: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[int] = mapped_column(INTEGER, nullable=False)


class SettingsModel(Base):
    """Tizim sozlamalari (yagona qator)."""

    __tablename__ = "settings"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, default=1)
    lookback_days: Mapped[int] = mapped_column(INTEGER, nullable=False, default=10)
    weather_past_days: Mapped[int] = mapped_column(INTEGER, nullable=False, default=5)
    weather_forecast_days: Mapped[int] = mapped_column(INTEGER, nullable=False, default=5)
    max_scene_cloud_pct: Mapped[float] = mapped_column(REAL, nullable=False, default=40.0)
    cloud_score_threshold: Mapped[float] = mapped_column(REAL, nullable=False, default=0.60)
    s1_orbit_pass: Mapped[str] = mapped_column(TEXT, nullable=False, default="BOTH")
    analysis_resolution_m: Mapped[float] = mapped_column(REAL, nullable=False, default=10.0)
    max_aoi_km2: Mapped[float] = mapped_column(REAL, nullable=False, default=100.0)
    gee_request_timeout_s: Mapped[int] = mapped_column(INTEGER, nullable=False, default=60)
    gee_max_retries: Mapped[int] = mapped_column(INTEGER, nullable=False, default=3)
    gee_max_concurrency: Mapped[int] = mapped_column(INTEGER, nullable=False, default=6)
    ai_provider: Mapped[str] = mapped_column(TEXT, nullable=False, default="openrouter")
    ai_model: Mapped[str] = mapped_column(TEXT, nullable=False, default="openrouter/free")
    ai_history_size: Mapped[int] = mapped_column(INTEGER, nullable=False, default=10)
