"""24 soatlik saqlash muddati: eski run'lar (fayl + DB) o'chiriladi, yangilari va faol run qoladi."""

import json

from sqlalchemy import select

from backend.app.cleanup.retention import mark_interrupted_runs, purge_expired_runs
from backend.app.core.time import now_ts
from backend.app.db import session as db
from backend.app.db.enums import JobStatus
from backend.app.db.models import RunModel, UserModel
from backend.app.pipeline import storage as st


async def _mk_run(created_at: int, status: JobStatus = JobStatus.COMPLETED, files: bool = True) -> int:
    async with db.session_scope() as s:
        u = (await s.execute(select(UserModel))).scalars().first()
        if u is None:
            u = UserModel(username="r", password_hash=b"x" * 32, salt=b"s" * 16, iterations=1, created_at=0)
            s.add(u)
            await s.flush()
        r = RunModel(user_id=u.id, status=status, aoi_geojson=json.dumps({}), area_km2=1.0, settings_json="{}",
                     created_at=created_at)
        s.add(r)
        await s.commit()
        rid = r.id
    (st.run_dir(rid) / "png").mkdir(parents=True)
    (st.run_dir(rid) / "png" / "x.png").write_bytes(b"x")
    if files:
        st.save_json(st.summary_path(rid), {})
    return rid


async def test_saved_areas_kept_failed_purged_after_24h():
    now = now_ts()
    saved_old = await _mk_run(now - 10 * 86400)  # yakunlangan maydon — o'chirilmaydi
    old = await _mk_run(now - 24 * 3600 - 60, JobStatus.FAILED)
    fresh = await _mk_run(now - 23 * 3600, JobStatus.FAILED)
    orphan = st.run_dir(424242)
    orphan.mkdir(parents=True)
    assert await purge_expired_runs(now=now) == 1
    async with db.session_scope() as s:
        assert await s.get(RunModel, old) is None
        assert await s.get(RunModel, fresh) is not None
        assert await s.get(RunModel, saved_old) is not None
    assert st.run_dir(saved_old).exists()
    assert not st.run_dir(old).exists() and st.run_dir(fresh).exists()
    assert not orphan.exists()  # DB yozuvisiz katalog ham tozalanadi


async def test_interrupted_runs_removed_on_startup():
    rid = await _mk_run(now_ts(), JobStatus.RUNNING)
    assert await mark_interrupted_runs() == 1
    assert not st.run_dir(rid).exists()


async def test_run_ids_never_reused_after_purge():
    from backend.app.cleanup.retention import purge_expired_runs as purge

    first = await _mk_run(now_ts() - 2 * 86400, JobStatus.FAILED)
    await purge(now=now_ts())
    second = await _mk_run(now_ts())
    assert second > first  # AUTOINCREMENT: o'chirilgan ID qayta berilmaydi


async def test_completed_run_without_files_removed_on_startup():
    from backend.app.cleanup.retention import remove_runs_without_files

    keep = await _mk_run(now_ts())
    gone = await _mk_run(now_ts(), files=False)
    assert await remove_runs_without_files() == 1
    async with db.session_scope() as s:
        assert await s.get(RunModel, gone) is None and await s.get(RunModel, keep) is not None
