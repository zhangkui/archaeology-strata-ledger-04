-- 考古发掘层位证据链系统 - 初始 schema
-- PostgreSQL 16 + PostGIS 3.5

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 迁移记录
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 遗址
-- ---------------------------------------------------------------------------
CREATE TABLE sites (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    centroid    geometry(Point, 4326),
    boundary    geometry(Polygon, 4326),
    description text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sites_boundary_gix ON sites USING GIST (boundary);

-- ---------------------------------------------------------------------------
-- 探方
-- ---------------------------------------------------------------------------
CREATE TABLE trenches (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     uuid NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    code        text NOT NULL,
    geom        geometry(Polygon, 4326),
    elevation   numeric(10, 3),
    opened_on   date NOT NULL,
    closed_on   date,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site_id, code),
    CONSTRAINT trenches_date_range CHECK (closed_on IS NULL OR closed_on >= opened_on)
);
CREATE INDEX trenches_site_idx ON trenches (site_id);
CREATE INDEX trenches_geom_gix ON trenches USING GIST (geom);

-- ---------------------------------------------------------------------------
-- 层位（含不可变原始观察值）
-- status: open 可登记出土物 / closed 已结束 / merged 已被合并
-- ---------------------------------------------------------------------------
CREATE TABLE layers (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trench_id            uuid NOT NULL REFERENCES trenches(id) ON DELETE RESTRICT,
    code                 text NOT NULL,
    status               text NOT NULL DEFAULT 'open'
                           CHECK (status IN ('open', 'closed', 'merged')),
    opened_on            date NOT NULL,
    closed_on            date,
    description          text,
    soil_color           text,
    soil_texture         text,
    depth_top_cm         numeric(8, 2),
    depth_bottom_cm      numeric(8, 2),
    -- 原始观察值：仅 INSERT 时写入，触发器禁止后续修改
    original_observation jsonb NOT NULL,
    merged_into_id       uuid REFERENCES layers(id) ON DELETE RESTRICT,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (trench_id, code),
    CONSTRAINT layers_depth_range CHECK (
        depth_top_cm IS NULL OR depth_bottom_cm IS NULL OR depth_bottom_cm >= depth_top_cm
    ),
    CONSTRAINT layers_closed_check CHECK (
        closed_on IS NULL OR closed_on >= opened_on
    )
);
CREATE INDEX layers_trench_idx ON layers (trench_id);
CREATE INDEX layers_status_idx ON layers (status);

CREATE OR REPLACE FUNCTION fn_layers_touch() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_layers_touch
    BEFORE UPDATE ON layers
    FOR EACH ROW EXECUTE FUNCTION fn_layers_touch();

-- ---------------------------------------------------------------------------
-- 层位父子关系（DAG，考古地层学关系：child 晚于 / 打破 parent）
-- ---------------------------------------------------------------------------
CREATE TABLE layer_parents (
    child_id   uuid NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    parent_id  uuid NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    relation   text NOT NULL DEFAULT 'stratigraphic'
                 CHECK (relation IN ('stratigraphic', 'cuts', 'equals')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (child_id, parent_id),
    CONSTRAINT layer_parents_no_self CHECK (child_id <> parent_id)
);
CREATE INDEX layer_parents_parent_idx ON layer_parents (parent_id);

CREATE OR REPLACE FUNCTION fn_layer_parents_validate() RETURNS trigger AS $$
DECLARE
    v_child_trench  uuid;
    v_parent_trench uuid;
BEGIN
    SELECT trench_id INTO v_child_trench  FROM layers WHERE id = NEW.child_id;
    SELECT trench_id INTO v_parent_trench FROM layers WHERE id = NEW.parent_id;

    IF v_child_trench IS NULL OR v_parent_trench IS NULL THEN
        RAISE EXCEPTION 'layer not found' USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_child_trench <> v_parent_trench THEN
        RAISE EXCEPTION '层位关系必须在同一探方内 (child trench=%, parent trench=%)',
            v_child_trench, v_parent_trench
            USING ERRCODE = 'check_violation';
    END IF;

    -- 沿 parent 链向上递归，若能从新父层回到子层则成环
    IF EXISTS (
        WITH RECURSIVE walk AS (
            SELECT NEW.parent_id AS id
            UNION
            SELECT lp.parent_id
              FROM layer_parents lp
              JOIN walk w ON w.id = lp.child_id
        )
        SELECT 1 FROM walk WHERE id = NEW.child_id
    ) THEN
        RAISE EXCEPTION '检测到地层环：% 不能成为 % 的父层（将形成循环）',
            NEW.parent_id, NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_layer_parents_validate
    BEFORE INSERT OR UPDATE ON layer_parents
    FOR EACH ROW EXECUTE FUNCTION fn_layer_parents_validate();

-- ---------------------------------------------------------------------------
-- 层位修订（只追加，永不更新/删除）
-- ---------------------------------------------------------------------------
CREATE TABLE layer_revisions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id    uuid NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('create', 'amend')),
    field       text,
    old_value   jsonb,
    new_value   jsonb,
    actor       text NOT NULL DEFAULT COALESCE(current_setting('app.actor', true), 'anonymous'),
    reason      text,
    revised_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX layer_revisions_layer_idx ON layer_revisions (layer_id, revised_at);

CREATE OR REPLACE FUNCTION fn_layer_revisions_append_only() RETURNS trigger AS $$
BEGIN
    -- 仅允许「删除层位」这一显式管理操作在服务端设置 app.allow_evidence_purge=on 后清理
    IF COALESCE(current_setting('app.allow_evidence_purge', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'layer_revisions 为只追加证据记录，禁止 % 操作', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_layer_revisions_freeze
    BEFORE UPDATE OR DELETE ON layer_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_layer_revisions_append_only();

-- 层位 INSERT：固化原始观察快照；UPDATE：逐字段写入修订，且禁止篡改 original_observation
CREATE OR REPLACE FUNCTION fn_layer_revision_audit() RETURNS trigger AS $$
DECLARE
    v_actor text := COALESCE(NULLIF(current_setting('app.actor', true), ''), 'anonymous');
    v_field text;
    v_old   jsonb;
    v_new   jsonb;
    v_fields text[] := ARRAY[
        'code', 'status', 'opened_on', 'closed_on', 'description',
        'soil_color', 'soil_texture', 'depth_top_cm', 'depth_bottom_cm',
        'merged_into_id'
    ];
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO layer_revisions (layer_id, kind, field, old_value, new_value, actor)
        VALUES (NEW.id, 'create', NULL, NULL, to_jsonb(NEW), v_actor);
        RETURN NEW;
    END IF;

    IF OLD.original_observation IS DISTINCT FROM NEW.original_observation THEN
        RAISE EXCEPTION 'original_observation 是原始观察证据，不可修改'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    FOREACH v_field IN ARRAY v_fields LOOP
        EXECUTE format('SELECT to_jsonb($1.%I), to_jsonb($2.%I)', v_field, v_field)
            INTO v_old, v_new USING OLD, NEW;
        IF v_old IS DISTINCT FROM v_new THEN
            INSERT INTO layer_revisions (layer_id, kind, field, old_value, new_value, actor)
            VALUES (NEW.id, 'amend', v_field, v_old, v_new, v_actor);
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_layer_revision_audit
    AFTER INSERT OR UPDATE ON layers
    FOR EACH ROW EXECUTE FUNCTION fn_layer_revision_audit();

-- ---------------------------------------------------------------------------
-- 出土记录（只能归属 open 层位 + 坐标必须在探方范围内）
-- ---------------------------------------------------------------------------
CREATE TABLE finds (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id    uuid NOT NULL REFERENCES layers(id) ON DELETE RESTRICT,
    code        text NOT NULL UNIQUE,
    category    text NOT NULL,
    position    geometry(Point, 4326),
    z_elevation numeric(10, 3),
    found_on    date NOT NULL,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finds_layer_idx ON finds (layer_id);
CREATE INDEX finds_position_gix ON finds USING GIST (position);
CREATE INDEX finds_found_on_idx ON finds (found_on);

CREATE OR REPLACE FUNCTION fn_finds_validate() RETURNS trigger AS $$
DECLARE
    v_status text;
    v_trench uuid;
    v_geom   geometry(Polygon, 4326);
BEGIN
    SELECT l.status, l.trench_id, t.geom
      INTO v_status, v_trench, v_geom
      FROM layers l JOIN trenches t ON t.id = l.trench_id
     WHERE l.id = NEW.layer_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'layer % 不存在', NEW.layer_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_status <> 'open' THEN
        RAISE EXCEPTION '出土物只能登记到开放(open)层位，当前层位状态为 %', v_status
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.position IS NOT NULL AND v_geom IS NOT NULL
       AND NOT ST_Within(NEW.position, v_geom) THEN
        RAISE EXCEPTION '出土坐标不在探方边界内 (layer=%)', NEW.layer_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_finds_validate
    BEFORE INSERT OR UPDATE OF layer_id, position ON finds
    FOR EACH ROW EXECUTE FUNCTION fn_finds_validate();

-- ---------------------------------------------------------------------------
-- 照片（MinIO 对象引用，属证据材料）
-- ---------------------------------------------------------------------------
CREATE TABLE photos (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id     uuid REFERENCES layers(id) ON DELETE RESTRICT,
    find_id      uuid REFERENCES finds(id) ON DELETE RESTRICT,
    object_key   text NOT NULL,
    bucket       text NOT NULL,
    filename     text NOT NULL,
    content_type text,
    size_bytes   bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    taken_on     date,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT photos_target_check CHECK (layer_id IS NOT NULL OR find_id IS NOT NULL)
);
CREATE INDEX photos_layer_idx ON photos (layer_id);
CREATE INDEX photos_find_idx ON photos (find_id);

-- ---------------------------------------------------------------------------
-- 样本（碳样、土样等，属证据材料）
-- ---------------------------------------------------------------------------
CREATE TABLE samples (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id     uuid NOT NULL REFERENCES layers(id) ON DELETE RESTRICT,
    find_id      uuid REFERENCES finds(id) ON DELETE RESTRICT,
    code         text NOT NULL UNIQUE,
    material     text NOT NULL,
    position     geometry(Point, 4326),
    collected_on date NOT NULL,
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX samples_layer_idx ON samples (layer_id);
CREATE INDEX samples_find_idx ON samples (find_id);

-- ---------------------------------------------------------------------------
-- 层位合并迁移关系
-- ---------------------------------------------------------------------------
CREATE TABLE layer_merge_relations (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_layer_id   uuid NOT NULL REFERENCES layers(id) ON DELETE RESTRICT,
    target_layer_id   uuid NOT NULL REFERENCES layers(id) ON DELETE RESTRICT,
    migrated_finds    integer NOT NULL DEFAULT 0,
    migrated_photos   integer NOT NULL DEFAULT 0,
    migrated_samples  integer NOT NULL DEFAULT 0,
    reason            text,
    merged_by         text NOT NULL DEFAULT COALESCE(current_setting('app.actor', true), 'anonymous'),
    merged_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT layer_merge_distinct CHECK (source_layer_id <> target_layer_id)
);
CREATE INDEX layer_merge_source_idx ON layer_merge_relations (source_layer_id);
CREATE INDEX layer_merge_target_idx ON layer_merge_relations (target_layer_id);

-- ---------------------------------------------------------------------------
-- 审计事件（只追加）
-- ---------------------------------------------------------------------------
CREATE TABLE audit_events (
    id          bigserial PRIMARY KEY,
    event_type  text NOT NULL,
    entity_type text NOT NULL,
    entity_id   uuid,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor       text NOT NULL DEFAULT COALESCE(current_setting('app.actor', true), 'anonymous'),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_entity_idx ON audit_events (entity_type, entity_id);
CREATE INDEX audit_events_type_idx ON audit_events (event_type, created_at);

CREATE OR REPLACE FUNCTION fn_audit_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events 为只追加记录，禁止 % 操作', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_freeze
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION fn_audit_append_only();
