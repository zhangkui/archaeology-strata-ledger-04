from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

GeoJSON = dict[str, Any]

LayerStatus = Literal["open", "closed", "merged"]
RelationKind = Literal["stratigraphic", "cuts", "equals"]


# ---------------- 遗址 / 探方 ----------------
class SiteIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    centroid: GeoJSON | None = None
    boundary: GeoJSON | None = None


class SiteOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    centroid: GeoJSON | None
    boundary: GeoJSON | None
    created_at: datetime


class TrenchIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    elevation: float | None = None
    opened_on: date
    closed_on: date | None = None
    note: str | None = None
    geom: GeoJSON | None = None


class TrenchOut(BaseModel):
    id: UUID
    site_id: UUID
    code: str
    elevation: float | None
    opened_on: date
    closed_on: date | None
    note: str | None
    geom: GeoJSON | None
    created_at: datetime


# ---------------- 层位 ----------------
class LayerIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    opened_on: date
    closed_on: date | None = None
    description: str | None = None
    soil_color: str | None = None
    soil_texture: str | None = None
    depth_top_cm: float | None = Field(default=None, ge=0)
    depth_bottom_cm: float | None = Field(default=None, ge=0)
    parent_ids: list[UUID] = Field(default_factory=list)
    # 原始观察值：创建后不可修改
    original_observation: dict[str, Any] = Field(default_factory=dict)


class LayerUpdate(BaseModel):
    """修订：仅允许改这些字段；original_observation 永不出现于此。"""
    code: str | None = Field(default=None, min_length=1, max_length=64)
    closed_on: date | None = None
    description: str | None = None
    soil_color: str | None = None
    soil_texture: str | None = None
    depth_top_cm: float | None = Field(default=None, ge=0)
    depth_bottom_cm: float | None = Field(default=None, ge=0)
    reason: str | None = None
    # 关闭/重开走状态机；status 不允许直接赋值
    close: bool = False
    reopen: bool = False


class LayerOut(BaseModel):
    id: UUID
    trench_id: UUID
    code: str
    status: LayerStatus
    opened_on: date
    closed_on: date | None
    description: str | None
    soil_color: str | None
    soil_texture: str | None
    depth_top_cm: float | None
    depth_bottom_cm: float | None
    original_observation: dict[str, Any]
    merged_into_id: UUID | None
    parent_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class LayerNode(BaseModel):
    layer: LayerOut
    children: list["LayerNode"] = Field(default_factory=list)
    depth: int = 0


class ParentLinkIn(BaseModel):
    parent_id: UUID
    relation: RelationKind = "stratigraphic"


class RevisionOut(BaseModel):
    id: UUID
    layer_id: UUID
    kind: str
    field: str | None
    old_value: Any | None
    new_value: Any | None
    actor: str
    reason: str | None
    revised_at: datetime


# ---------------- 出土物 / 照片 / 样本 ----------------
class FindIn(BaseModel):
    layer_id: UUID
    code: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=100)
    found_on: date
    z_elevation: float | None = None
    note: str | None = None
    position: GeoJSON | None = None


class FindOut(FindIn):
    id: UUID
    created_at: datetime


class SampleIn(BaseModel):
    layer_id: UUID
    find_id: UUID | None = None
    code: str = Field(min_length=1, max_length=64)
    material: str = Field(min_length=1, max_length=100)
    collected_on: date
    note: str | None = None
    position: GeoJSON | None = None


class SampleOut(SampleIn):
    id: UUID
    created_at: datetime


class PhotoOut(BaseModel):
    id: UUID
    layer_id: UUID | None
    find_id: UUID | None
    object_key: str
    bucket: str
    filename: str
    content_type: str | None
    size_bytes: int | None
    taken_on: date | None
    url: str | None = None
    created_at: datetime


# ---------------- 批量导入 ----------------
class BatchItem(BaseModel):
    op: Literal["layer", "find", "sample", "parent_link"]
    ref: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class BatchIn(BaseModel):
    # trench_id 由路径提供；body 中可省略
    trench_id: UUID | None = None
    items: list[BatchItem] = Field(min_length=1)


class BatchResult(BaseModel):
    committed: bool
    count: int
    ids: dict[str, str]
    error: dict[str, Any] | None = None


# ---------------- 合并 ----------------
class MergeIn(BaseModel):
    source_layer_id: UUID
    target_layer_id: UUID
    reason: str | None = None


class MergeOut(BaseModel):
    merge_relation_id: UUID
    source_layer_id: UUID
    target_layer_id: UUID
    migrated_finds: int
    migrated_photos: int
    migrated_samples: int


# ---------------- 回放 ----------------
class ReplayOut(BaseModel):
    as_of: datetime
    layers: list[dict[str, Any]]
    finds: list[dict[str, Any]]
    revisions: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]


class AuditOut(BaseModel):
    id: int
    event_type: str
    entity_type: str
    entity_id: UUID | None
    payload: dict[str, Any]
    actor: str
    created_at: datetime
