"""24 soatlik saqlash muddati: eski run'lar (fayl + DB) o'chiriladi, yangilari va faol run qoladi."""

import json

from backend.app.cleanup.retention import mark_interrupted_runs, purge_expired_runs
from backend.app.core.time import now_ts
from backend.app.db import session as db
from backend.app.db.enums import JobStatus
from backend.app.db.models import RunModel
from backend.app.pipeline import storage as st


async def _mk_run(created_at: int, status: JobStatus = JobStatus.COMPLETED) -> int:
    async with db.session_scope() as s:
        r = RunModel(status=status, aoi_geojson=json.dumps({}), area_km2=1.0, settings_json="{}", created_at=created_at)
        s.add(r)
        await s.commit()
        rid = r.id
    (st.run_dir(rid) / "png").mkdir(parents=True)
    (st.run_dir(rid) / "png" / "x.png").write_bytes(b"x")
    return rid


async def test_purge_older_than_24h():
    now = now_ts()
    old = await _mk_run(now - 24 * 3600 - 60)
    fresh = await _mk_run(now - 23 * 3600)
    orphan = st.run_dir(424242)
    orphan.mkdir(parents=True)
    assert await purge_expired_runs(now=now) == 1
    async with db.session_scope() as s:
        assert await s.get(RunModel, old) is None
        assert await s.get(RunModel, fresh) is not None
    assert not st.run_dir(old).exists() and st.run_dir(fresh).exists()
    assert not orphan.exists()  # DB yozuvisiz katalog ham tozalanadi


async def test_interrupted_runs_removed_on_startup():
    rid = await _mk_run(now_ts(), JobStatus.RUNNING)
    assert await mark_interrupted_runs() == 1
    assert not st.run_dir(rid).exists()


async def test_run_ids_never_reused_after_purge():
    from backend.app.cleanup.retention import purge_expired_runs as purge

    first = await _mk_run(now_ts() - 2 * 86400)
    await purge(now=now_ts())
    second = await _mk_run(now_ts())
    assert second > first  # AUTOINCREMENT: o'chirilgan ID qayta berilmaydi
