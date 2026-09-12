"""GeoJSON 几何与 EWKT/SQL 的转换辅助。

前端统一使用 GeoJSON 几何对象，例如 {"type":"Point","coordinates":[lon,lat]}；
库内以 PostGIS geometry(...,4326) 存储。
"""
from typing import Any

# asyncpg 文本编解码收到的 geometry 形如 "0101000020E610..."(hex WKB) 或 EWKT，
# 因此读写一律显式走 ST_GeomFromGeoJSON / ST_AsGeoJSON，不依赖驱动编码。

def geojson_param(value: Any) -> str | None:
    """把传入值规整成 ST_GeomFromGeoJSON 可用文本；非法时抛业务错误。"""
    import json

    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False)
    # 轻量结构校验，具体合法性交给 PostGIS
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("geometry 不是合法 GeoJSON")
    if obj.get("type") not in {"Point", "Polygon", "MultiPolygon"}:
        raise ValueError(f"不支持的几何类型: {obj.get('type')}")
    return text


def geom_select(column: str, alias: str) -> str:
    return f"ST_AsGeoJSON({column})::jsonb AS {alias}"
