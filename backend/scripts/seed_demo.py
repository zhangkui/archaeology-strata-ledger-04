"""一键演示数据：遗址 → 探方(带边界) → 三层位 DAG → 出土物/样本/照片引用。

用法（API 已启动时）:
    python scripts/seed_demo.py
"""
import json
import os

import httpx

BASE = os.environ.get("API_BASE", "http://localhost:8000")

POLYGON = {"type": "Polygon", "coordinates": [[
    [116.4010, 39.9010], [116.4020, 39.9010],
    [116.4020, 39.9020], [116.4010, 39.9020],
    [116.4010, 39.9010]]]}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers={"X-Actor": "seed"}) as c:
        site = c.post("/api/sites", json={
            "code": "YX-2026-01", "name": "演西遗址",
            "description": "系统演示数据"}).json()
        trench = c.post(f"/api/sites/{site['id']}/trenches", json={
            "code": "T0103", "opened_on": "2026-08-20", "geom": POLYGON}).json()
        t = trench["id"]

        l1 = c.post(f"/api/trenches/{t}/layers", json={
            "code": "L1-表土层", "opened_on": "2026-08-20",
            "depth_top_cm": 0, "depth_bottom_cm": 25,
            "soil_color": "浅灰褐",
            "original_observation": {"observed_by": "li", "humidity": "dry"}}).json()
        l2 = c.post(f"/api/trenches/{t}/layers", json={
            "code": "L2-文化层", "opened_on": "2026-08-24",
            "depth_top_cm": 25, "depth_bottom_cm": 58,
            "soil_color": "深灰褐", "parent_ids": [l1["id"]],
            "original_observation": {"observed_by": "wang", "charcoal": True}}).json()
        l3 = c.post(f"/api/trenches/{t}/layers", json={
            "code": "L3-生土", "opened_on": "2026-08-28",
            "depth_top_cm": 58, "depth_bottom_cm": 80,
            "soil_color": "黄褐", "parent_ids": [l2["id"]],
            "original_observation": {"observed_by": "wang"}}).json()

        c.post("/api/finds", json={
            "layer_id": l2["id"], "code": "F-001", "category": "陶罐口沿",
            "found_on": "2026-08-25",
            "position": {"type": "Point", "coordinates": [116.4014, 39.9014]}})
        c.post("/api/samples", json={
            "layer_id": l2["id"], "code": "C14-001", "material": "炭样",
            "collected_on": "2026-08-25",
            "position": {"type": "Point", "coordinates": [116.4016, 39.9016]}})

        # 演示合并：把 L3 并入 L2
        r = c.post("/api/layers/merge", json={
            "source_layer_id": l3["id"], "target_layer_id": l2["id"],
            "reason": "发掘确认同为一个堆积单位"})
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
        print(f"\n演示数据已写入：{BASE}  探方 {t}")


if __name__ == "__main__":
    main()
