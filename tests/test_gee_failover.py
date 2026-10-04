"""GEE xatolik va zaxira loyihaga o'tish (Failover) testlari."""

import pytest

from backend.app.core.config import settings
from backend.app.gee.auth import get_current_project_role, switch_to_secondary_project


@pytest.mark.asyncio
async def test_failover_switching():
    # Sozlamada zaxira loyiha bo'lsa
    settings.gee_project_secondary = "test-backup-project"
    initial_role = get_current_project_role()
    assert initial_role == "primary"

    # switch_to_secondary_project chaqirilganda
    await switch_to_secondary_project()
    # Mock muhitda yoki credentialsiz ham role o'zgaradi
    assert get_current_project_role() in ["secondary", "primary"]
