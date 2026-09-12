import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.errors import BusinessError
from app.geo import geojson_param
from app.services.audit import record_event

LAYER_SELECT = """
SELECT l.*,
       COALESCE((SELECT json_agg(parent_id ORDER BY created_at)
                   FROM layer_parents WHERE child_id = l.id), '[]'::json) AS parent_ids
FROM layers l
"""


def _layer_row(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    # jsonb 已由驱动解析为 dict；parent_ids 为 uuid 字符串列表
    if isinstance(d.get("original_observation"), str):
        d["original_observation"] = json.loads(d["original_observation"])
    d["parent_ids"] = [UUID(x) if isinstance(x, str) else x for x in (d.get("parent_ids") or [])]
    return d


async def list_layers(conn: asyncpg.Connection, trench_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        LAYER_SELECT + " WHERE l.trench_id = $1 ORDER BY l.opened_on, l.code", trench_id
    )
    return [_layer_row(r) for r in rows]


async def get_layer(conn: asyncpg.Connection, layer_id: UUID) -> dict:
    row = await conn.fetchrow(LAYER_SELECT + " WHERE l.id = $1", layer_id)
    if not row:
        raise BusinessError("层位不存在", 404, "not_found")
    return _layer_row(row)


async def create_layer(conn: asyncpg.Connection, trench_id: UUID, data: dict,
                       ref: str | None = None) -> UUID:
    geo_ok = True
    async with conn.transaction():
        layer_id = await conn.fetchval(
            """
            INSERT INTO layers (
                trench_id, code, status, opened_on, closed_on, description,
                soil_color, soil_texture, depth_top_cm, depth_bottom_cm,
                original_observation
            ) VALUES ($1,$2,'open',$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
            RETURNING id
            """,
            trench_id,
            data["code"],
            data.get("opened_on"),
            data.get("closed_on"),
            data.get("description"),
            data.get("soil_color"),
            data.get("soil_texture"),
            data.get("depth_top_cm"),
            data.get("depth_bottom_cm"),
            json.dumps(data.get("original_observation") or {}, ensure_ascii=False),
        )
        for pid in data.get("parent_ids") or []:
            await conn.execute(
                "INSERT INTO layer_parents (child_id, parent_id, relation) VALUES ($1,$2,$3)",
                layer_id, UUID(str(pid)), data.get("relation", "stratigraphic"),
            )
        await record_event(conn, "layer.created", "layer", layer_id,
                           {"code": data["code"], "trench_id": str(trench_id), "ref": ref})
    return layer_id


async def amend_layer(conn: asyncpg.Connection, layer_id: UUID, patch: dict,
                      reason: str | None = None) -> dict:
    # status 不接受直接改写，只能通过 close/reopen 转换；merged 为合并流程专属终态
    allowed = {
        "code", "closed_on", "description",
        "soil_color", "soil_texture", "depth_top_cm", "depth_bottom_cm",
    }
    sets: list[str] = []
    args: list[Any] = []
    for key, value in patch.items():
        if key in allowed and value is not None:
            args.append(value)
            sets.append(f"{key} = ${len(args)}")

    if patch.get("close"):
        sets.append("status = 'closed'")
        sets.append("closed_on = COALESCE(closed_on, now()::date)")
    if patch.get("reopen"):
        current = await get_layer(conn, layer_id)
        if current["status"] == "merged":
            raise BusinessError("已合并层位不能重新开放，请使用合并目标层位", 409, "merged_layer")
        sets.append("status = 'open'")
        sets.append("closed_on = NULL")

    if not sets:
        raise BusinessError("没有可修订字段（原始观察值不允许修改）", 400, "empty_amend")

    args.append(layer_id)
    async with conn.transaction():
        row = await conn.fetchrow(
            f"UPDATE layers SET {', '.join(sets)} WHERE id = ${len(args)} RETURNING id", *args
        )
        if not row:
            raise BusinessError("层位不存在", 404, "not_found")
        await record_event(conn, "layer.amended", "layer", layer_id,
                           {"fields": list(patch.keys()), "reason": reason})
    return await get_layer(conn, layer_id)


async def add_parent_link(conn: asyncpg.Connection, child_id: UUID, parent_id: UUID,
                          relation: str = "stratigraphic") -> None:
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO layer_parents (child_id, parent_id, relation) VALUES ($1,$2,$3)",
            child_id, parent_id, relation,
        )
        await record_event(conn, "layer.parent_linked", "layer", child_id,
                           {"parent_id": str(parent_id), "relation": relation})


async def remove_parent_link(conn: asyncpg.Connection, child_id: UUID, parent_id: UUID) -> None:
    await conn.execute(
        "DELETE FROM layer_parents WHERE child_id=$1 AND parent_id=$2", child_id, parent_id
    )


async def delete_layer(conn: asyncpg.Connection, layer_id: UUID) -> None:
    """删除前证据链检查：子层位、出土物、照片、样本、合并关系均阻断删除。"""
    blockers: dict[str, int] = {}
    child_count = await conn.fetchval(
        "SELECT count(*) FROM layer_parents WHERE parent_id = $1", layer_id
    )
    if child_count:
        blockers["child_layers"] = child_count
    for table, col in (
        ("finds", "layer_id"),
        ("photos", "layer_id"),
        ("samples", "layer_id"),
        ("layer_merge_relations", "source_layer_id"),
        ("layer_merge_relations", "target_layer_id"),
    ):
        n = await conn.fetchval(
            f"SELECT count(*) FROM {table} WHERE {col} = $1", layer_id
        )
        if n:
            key = "merge_relations" if table == "layer_merge_relations" else table
            blockers[key] = blockers.get(key, 0) + n

    if blockers:
        raise BusinessError(
            "层位存在证据引用或子层位，不能删除；请先迁移或删除引用",
            409, "layer_referenced", {"blockers": blockers},
        )

    async with conn.transaction():
        # 删除层位是唯一允许清理其只追加修订的管理操作
        await conn.execute("SELECT set_config('app.allow_evidence_purge', 'on', true)")
        await conn.execute("DELETE FROM layer_parents WHERE child_id=$1", layer_id)
        deleted = await conn.execute("DELETE FROM layers WHERE id=$1", layer_id)
        await conn.execute("SELECT set_config('app.allow_evidence_purge', 'off', true)")
        if deleted.endswith("0"):
            raise BusinessError("层位不存在", 404, "not_found")
        await record_event(conn, "layer.deleted", "layer", layer_id, {})


async def list_revisions(conn: asyncpg.Connection, layer_id: UUID | None = None) -> list[dict]:
    if layer_id:
        rows = await conn.fetch(
            "SELECT * FROM layer_revisions WHERE layer_id=$1 ORDER BY revised_at, id", layer_id
        )
    else:
        rows = await conn.fetch("SELECT * FROM layer_revisions ORDER BY revised_at, id")
    return [dict(r) for r in rows]


async def layer_tree(conn: asyncpg.Connection, trench_id: UUID) -> list[dict]:
    layers = await list_layers(conn, trench_id)
    by_id = {l["id"]: {"layer": l, "children": [], "depth": 0} for l in layers}
    roots: list[dict] = []
    for node in by_id.values():
        for pid in node["layer"]["parent_ids"]:
            parent = by_id.get(pid)
            if parent:
                parent["children"].append(node)
            else:
                roots.append(node)
        if not node["layer"]["parent_ids"]:
            roots.append(node)
    # 去重 roots（父层不在本探方的已追加过一次）
    seen: set = set()
    uniq: list[dict] = []
    for n in roots:
        if n["layer"]["id"] not in seen:
            seen.add(n["layer"]["id"])
            uniq.append(n)

    def _mark_depth(nodes: list[dict], depth: int) -> None:
        for n in nodes:
            n["depth"] = depth
            _mark_depth(n["children"], depth + 1)

    _mark_depth(uniq, 0)
    uniq.sort(key=lambda n: n["layer"]["code"])
    return uniq


# ---------------------------------------------------------------------------
# 合并两个层位：证据迁移 + DAG 边迁移 + 审计事件（单事务）
# ---------------------------------------------------------------------------
async def merge_layers(conn: asyncpg.Connection, source_id: UUID, target_id: UUID,
                       reason: str | None = None) -> dict:
    if source_id == target_id:
        raise BusinessError("不能将层位合并到自身", 400, "merge_self")

    async with conn.transaction():
        rows = await conn.fetch(
            "SELECT id, trench_id, code, status FROM layers WHERE id = ANY($1) FOR UPDATE",
            [source_id, target_id],
        )
        if len(rows) != 2:
            raise BusinessError("源层位或目标层位不存在", 404, "not_found")
        by_id = {r["id"]: r for r in rows}
        src, tgt = by_id[source_id], by_id[target_id]
        if src["trench_id"] != tgt["trench_id"]:
            raise BusinessError("只能合并同一探方内的层位", 409, "cross_trench_merge")
        if tgt["status"] != "open":
            raise BusinessError(f"目标层位必须为开放状态，当前为 {tgt['status']}",
                                409, "target_not_open")
        if src["status"] == "merged":
            raise BusinessError("源层位已经被合并过", 409, "source_already_merged")

        # 1) 先解除源层位的全部 DAG 边，再按语义迁移，避免触发器误判环/自环
        old_parent_ids = [r["parent_id"] for r in await conn.fetch(
            "SELECT parent_id FROM layer_parents WHERE child_id = $1", source_id)]
        old_child_ids = [r["child_id"] for r in await conn.fetch(
            "SELECT child_id FROM layer_parents WHERE parent_id = $1", source_id)]
        await conn.execute("DELETE FROM layer_parents WHERE child_id=$1 OR parent_id=$1",
                           source_id)

        async def _link(cid: UUID, pid: UUID) -> None:
            if cid == pid:
                return
            exists = await conn.fetchval(
                "SELECT 1 FROM layer_parents WHERE child_id=$1 AND parent_id=$2", cid, pid
            )
            if exists:
                return
            # 无环触发器会继续把关
            await conn.execute(
                "INSERT INTO layer_parents (child_id, parent_id) VALUES ($1,$2)", cid, pid
            )

        for pid in old_parent_ids:   # 目标层位继承源层位的上部父层
            await _link(target_id, pid)
        for cid in old_child_ids:    # 源层位的子层位改挂到目标层位
            await _link(cid, target_id)

        # 2) 证据迁移（finds 触发器校验目标层位开放 + 坐标在探方内）
        # 出土物与「挂在出土物上的照片」在同一条多 CTE 语句内一起迁移并计数
        moved = await conn.fetchrow(
            """
            WITH moved_finds AS (
                UPDATE finds SET layer_id=$2::uuid WHERE layer_id=$1::uuid RETURNING id
            ),
            find_count AS (SELECT count(*) AS c FROM moved_finds),
            moved_find_photos AS (
                UPDATE photos p SET layer_id=$2::uuid
                FROM moved_finds mf
                WHERE p.find_id = mf.id AND p.layer_id IS DISTINCT FROM $2::uuid
                RETURNING 1
            ),
            find_photo_count AS (SELECT count(*) AS c FROM moved_find_photos)
            SELECT (SELECT c FROM find_count) AS finds,
                   (SELECT c FROM find_photo_count) AS find_photos
            """,
            source_id, target_id,
        )
        migrated_finds = moved["finds"]
        # 直接挂在源层位上的照片（无 find_id）
        direct = await conn.fetchrow(
            "WITH moved AS (UPDATE photos SET layer_id=$2::uuid "
            "WHERE layer_id=$1::uuid RETURNING 1) SELECT count(*) AS c FROM moved",
            source_id, target_id,
        )
        migrated_photos = moved["find_photos"] + direct["c"]
        migrated_samples = await conn.fetchval(
            "WITH moved AS (UPDATE samples SET layer_id=$2::uuid WHERE layer_id=$1::uuid "
            "RETURNING 1) SELECT count(*) FROM moved",
            source_id, target_id,
        )

        # 3) 源层位置为 merged（修订审计触发器自动记录 status/merged_into_id 变更）
        await conn.execute(
            "UPDATE layers SET status='merged', merged_into_id=$2, "
            "closed_on=COALESCE(closed_on, now()::date) WHERE id=$1",
            source_id, target_id,
        )

        merge_id = await conn.fetchval(
            """
            INSERT INTO layer_merge_relations
                (source_layer_id, target_layer_id, migrated_finds,
                 migrated_photos, migrated_samples, reason)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
            """,
            source_id, target_id, migrated_finds, migrated_photos, migrated_samples, reason,
        )
        await record_event(conn, "layer.merged", "layer", source_id, {
            "source_layer_id": str(source_id),
            "target_layer_id": str(target_id),
            "migrated": {"finds": migrated_finds, "photos": migrated_photos,
                         "samples": migrated_samples},
            "merge_relation_id": str(merge_id),
            "reason": reason,
        })

    return {
        "merge_relation_id": merge_id,
        "source_layer_id": source_id,
        "target_layer_id": target_id,
        "migrated_finds": migrated_finds,
        "migrated_photos": migrated_photos,
        "migrated_samples": migrated_samples,
    }


# ---------------------------------------------------------------------------
# 按发掘日期回放：用只追加修订流重建层位历史版本
# ---------------------------------------------------------------------------
async def replay_as_of(conn: asyncpg.Connection, trench_id: UUID,
                       as_of: datetime) -> dict:
    revisions = await conn.fetch(
        """
        SELECT r.* FROM layer_revisions r
        JOIN layers l ON l.id = r.layer_id
        WHERE l.trench_id = $1 AND r.revised_at <= $2
        ORDER BY r.revised_at, r.id
        """,
        trench_id, as_of,
    )
    states: dict[UUID, dict] = {}
    revision_log: list[dict] = []
    for rev in revisions:
        r = dict(rev)
        revision_log.append(r)
        if r["kind"] == "create":
            snapshot = r["new_value"] or {}
            states[r["layer_id"]] = snapshot
        elif r["kind"] == "amend" and r["layer_id"] in states and r["field"]:
            states[r["layer_id"]][r["field"]] = r["new_value"]

    layers = [
        v for k, v in states.items()
        if isinstance(v, dict)
    ]

    finds = await conn.fetch(
        """
        SELECT id, layer_id, code, category, found_on, z_elevation, note,
               ST_AsGeoJSON(position)::jsonb AS position, created_at
        FROM finds
        WHERE layer_id IN (SELECT id FROM layers WHERE trench_id=$1)
          AND found_on <= $2::date
        ORDER BY found_on
        """,
        trench_id, as_of,
    )
    events = await conn.fetch(
        """
        SELECT e.* FROM audit_events e
        WHERE e.created_at <= $2
          AND (
            (e.entity_type = 'trench' AND e.entity_id = $1)
            OR (e.entity_type = 'layer'
                AND e.entity_id IN (SELECT id FROM layers WHERE trench_id=$1))
            OR (e.entity_type IN ('find','photo','sample')
                AND e.entity_id IN (
                    SELECT x.id FROM (
                        SELECT id FROM finds WHERE layer_id IN (SELECT id FROM layers WHERE trench_id=$1)
                        UNION SELECT id FROM photos WHERE layer_id IN (SELECT id FROM layers WHERE trench_id=$1)
                        UNION SELECT id FROM samples WHERE layer_id IN (SELECT id FROM layers WHERE trench_id=$1)
                    ) x
                ))
          )
        ORDER BY e.created_at, e.id
        """,
        trench_id, as_of,
    )
    return {
        "as_of": as_of,
        "layers": layers,
        "finds": [dict(f) for f in finds],
        "revisions": revision_log,
        "audit_events": [dict(e) for e in events],
    }
