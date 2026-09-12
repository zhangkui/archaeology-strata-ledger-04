"""HTTP 端到端：真实 FastAPI 应用（ASGI）+ 异常处理器 + 迁移执行器。

Redis/MinIO 不参与断言：缓存自动降级，MinIO 建桶失败被吞掉。
"""
import os

# 必须在导入应用前指定测试库（conftest 会在每个用例重建 schema，
# 但应用启动迁移是幂等的，这里用独立的库避免与直连测试互相清库）
_TEST_DSN = "postgresql://postgres@127.0.0.1:55436/archaeo_api"
os.environ["DATABASE_URL"] = _TEST_DSN

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_api_db():
    """每个测试前清空 archaeo_api，避免唯一编号冲突。"""
    import asyncpg

    conn = await asyncpg.connect(_TEST_DSN)
    # 彻底重建 schema；启动迁移会幂等地重建扩展与全部对象
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    await conn.close()
    yield


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test",
                       headers={"X-Actor": "api-tester"})


async def test_health():
    async with app.router.lifespan_context(app):
        async with await _client() as c:
            r = await c.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"


async def test_full_workflow_api():
    async with app.router.lifespan_context(app):
        async with await _client() as c:
            # 遗址
            r = await c.post("/api/sites", json={"code": "YX01", "name": "殷墟外围点"})
            assert r.status_code == 201, r.text
            site_id = r.json()["id"]

            # 探方（含边界）
            polygon = {"type": "Polygon", "coordinates": [[
                [116.4010, 39.9010], [116.4020, 39.9010],
                [116.4020, 39.9020], [116.4010, 39.9020],
                [116.4010, 39.9010]]]}
            r = await c.post(f"/api/sites/{site_id}/trenches",
                             json={"code": "T01", "opened_on": "2026-09-01", "geom": polygon})
            assert r.status_code == 201, r.text
            trench_id = r.json()["id"]

            # 两个层位
            r = await c.post(f"/api/trenches/{trench_id}/layers",
                             json={"code": "L1", "opened_on": "2026-09-01",
                                   "original_observation": {"soil": "表土"}})
            assert r.status_code == 201, r.text
            l1 = r.json()["id"]
            r = await c.post(f"/api/trenches/{trench_id}/layers",
                             json={"code": "L2", "opened_on": "2026-09-02",
                                   "parent_ids": [l1]})
            assert r.status_code == 201, r.text
            l2 = r.json()["id"]

            # 成环：让 L1 挂到 L2 下 -> 409
            r = await c.post(f"/api/layers/{l1}/parents", json={"parent_id": l2})
            assert r.status_code == 409
            assert "环" in r.json()["message"]

            # 出土物登记到开放层位
            r = await c.post("/api/finds", json={
                "layer_id": l2, "code": "F-API-1", "category": "骨器",
                "found_on": "2026-09-03",
                "position": {"type": "Point", "coordinates": [116.4015, 39.9015]}})
            assert r.status_code == 201, r.text

            # 坐标越界 -> 409
            r = await c.post("/api/finds", json={
                "layer_id": l2, "code": "F-API-BAD", "category": "x",
                "found_on": "2026-09-03",
                "position": {"type": "Point", "coordinates": [121.0, 40.0]}})
            assert r.status_code == 409
            assert "探方边界" in r.json()["message"]

            # 关闭层位后再登记 -> 409
            r = await c.post(f"/api/layers/{l2}/close")
            assert r.status_code == 200
            r = await c.post("/api/finds", json={
                "layer_id": l2, "code": "F-API-CLOSED", "category": "x",
                "found_on": "2026-09-03"})
            assert r.status_code == 409

            # 删除有证据的层位 -> 409 且返回 blockers
            r = await c.delete(f"/api/layers/{l2}")
            assert r.status_code == 409
            assert "finds" in r.json()["details"]["blockers"]

            # 修订时间线
            r = await c.get(f"/api/layers/{l1}/revisions")
            assert r.status_code == 200
            assert any(x["kind"] == "create" for x in r.json())

            # 重新开放并合并 L2 -> L1
            await c.post(f"/api/layers/{l2}/reopen")
            r = await c.post("/api/layers/merge",
                             json={"source_layer_id": l2, "target_layer_id": l1,
                                   "reason": "同一堆积"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["migrated_finds"] == 1

            # 源层位已合并
            r = await c.get(f"/api/layers/{l2}")
            assert r.json()["status"] == "merged"

            # 回放（用晚于今天的时刻，确保覆盖刚建立的修订）
            r = await c.get(f"/api/trenches/{trench_id}/replay",
                            params={"as_of": "2027-01-01T00:00:00Z"})
            assert r.status_code == 200
            replay = r.json()
            assert len(replay["layers"]) == 2
            assert any(e["event_type"] == "layer.merged" for e in replay["audit_events"])

            # 空间 FeatureCollection
            r = await c.get(f"/api/trenches/{trench_id}/features")
            assert r.status_code == 200
            assert r.json()["type"] == "FeatureCollection"
            assert len(r.json()["features"]) >= 2  # 探方面 + 出土点


async def test_batch_api_rollback():
    async with app.router.lifespan_context(app):
        async with await _client() as c:
            r = await c.post("/api/sites", json={"code": "YXB", "name": "批量点"})
            site_id = r.json()["id"]
            r = await c.post(f"/api/sites/{site_id}/trenches",
                             json={"code": "TB", "opened_on": "2026-09-01"})
            trench_id = r.json()["id"]

            good = [
                {"op": "layer", "ref": "A", "data": {"code": "A", "opened_on": "2026-09-01"}},
                {"op": "find", "data": {
                    "layer_id": {"$ref": "A"}, "code": "OK1", "category": "x",
                    "found_on": "2026-09-02"}},
            ]
            r = await c.post(f"/api/trenches/{trench_id}/batch", json={"items": good})
            assert r.status_code == 200 and r.json()["committed"] is True

            bad = good[:1] + [
                {"op": "find", "data": {
                    "layer_id": "00000000-0000-0000-0000-000000000000",
                    "code": "BAD", "category": "x", "found_on": "2026-09-02"}},
            ]
            r = await c.post(f"/api/trenches/{trench_id}/batch", json={"items": bad})
            assert r.status_code == 409
            assert "回滚" in r.json()["message"]
