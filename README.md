# 考古发掘层位证据链记录系统

管理**遗址 → 探方 → 层位 → 出土物 / 样本 / 照片**的考古发掘记录，重点保证地层关系正确、证据链不可篡改、批量操作事务化。

- **后端**：Python 3.12 · FastAPI 0.115 · asyncpg
- **数据**：PostgreSQL 16 + PostGIS 3.5（空间坐标由数据库触发器校验）
- **缓存/消息/对象**：Redis 7 · MinIO
- **前端**：React 19 · TypeScript · Vite 6 · react-leaflet
- **部署**：Docker Compose 一键启动

## 一键启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端（Nginx） | http://localhost:8080 |
| API 文档（Swagger） | http://localhost:8000/docs |
| MinIO 控制台 | http://localhost:9001 （minioadmin/minioadmin） |

演示数据（启动后另开终端）：

```bash
docker compose exec api python scripts/seed_demo.py
```

## 核心业务规则（均由数据库 + 服务层强制执行）

1. **层位无环父子关系（DAG）**
   `layer_parents` 上的 `BEFORE INSERT/UPDATE` 触发器用递归 CTE 沿父链回溯，
   一旦新边会形成环（直接环 / 间接环）即抛错回滚；同时禁止自环、禁止跨探方连边。
   允许菱形（一个层位多个父层）。

2. **出土物只能归属当前开放层位**
   `finds` 触发器校验所属层位 `status='open'`；挂到 closed / merged 层位、
   或把出土物 UPDATE 到非开放层位都会被拒绝。关闭层位走状态机（close/reopen），
   `merged` 为合并流程专属终态、不可重开。

3. **删除层位前的证据链检查**
   存在子层位、出土物、样本、照片或合并迁移关系时一律拒绝删除，并返回具体阻断项
   （`{"blockers": {"child_layers": n, "finds": n, ...}}`）。
   只有「干净」层位可删，删除是唯一允许清理其修订记录的管理操作（会话级开关）。

4. **修订不覆盖原始观察值**
   - 建层位时 `original_observation` 固化为不可变快照，触发器禁止后续 UPDATE；
   - 每次字段修订在 `layer_revisions` 只追加一行（旧值/新值/操作人/时间）；
   - `layer_revisions`、`audit_events` 均有「禁止 UPDATE/DELETE」触发器；
   - 操作人通过请求头 `X-Actor` → 会话变量 `app.actor` 自动落库。

5. **合并层位 = 迁移关系 + 审计事件（单事务）**
   - `SELECT … FOR UPDATE` 锁定两层，校验同探方、目标层开放、源层未合并；
   - 迁移全部出土物 / 样本 / 照片（含挂在出土物上的照片），计数精确；
   - 改写 DAG 边（目标继承源的父边，源的子层改挂目标），无环触发器继续把关；
   - 源层位置 `merged` 终态并写 `merged_into_id`；
   - 写入 `layer_merge_relations` 迁移关系与 `layer.merged` 审计事件。

6. **按发掘日期回放**
   `GET /api/trenches/{id}/replay?as_of=...` 用只追加修订流重放到指定时刻，
   重建当时各层位字段状态，并按 `found_on` 过滤出土物、按时间过滤审计事件。

7. **批量导入整批一个事务**
   `POST /api/trenches/{id}/batch` 提交任意数量的 layer/find/sample/parent_link，
   批内可用 `{"$ref":"名字"}` 引用同批先建实体；**任一项违规则整批回滚**，
   不留半成品（41 个测试中的重点用例）。

8. **空间坐标（PostGIS）**
   探方存 Polygon(4326)，出土点存 Point(4326)，触发器用 `ST_Within` 强制点必须
   落在探方边界内；提供 FeatureCollection 输出、空间相交检索与大地线距离计算。

## 本地开发

```bash
# 后端（需要可达的 PostGIS / Redis / MinIO，可用 compose 只起依赖）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev          # http://localhost:5173 ，/api 代理到 :8000
```

## 测试（真实 PostgreSQL 16 + PostGIS 3.5，非模拟）

无 root / 无 Docker 时可用用户态 micromamba 起测试库：

```bash
micromamba create -y -n archdb -c conda-forge 'postgresql=16' 'postgis=3.5'
cd backend
./scripts/start-test-db.sh
python -m pytest
```

`49` 个集成测试覆盖：DAG 直接/间接成环、菱形、跨探方；开放层位状态机；
`ST_Within` 越界拒绝；删除阻断（子层/出土物/样本/照片）；原始观察值不可改、
修订只追加、动态修订字段绑定；合并迁移计数、DAG 改写、审计；批量事务全成功/全回滚；
按日期回放；以及一条完整 HTTP API 工作流（ASGI in-process）。

## 目录结构

```
backend/
  app/
    main.py              FastAPI 入口 + 生命周期（自动迁移）
    db/migrations/       版本化 SQL（表/触发器/索引）
    services/            业务核心：layers(合并/回放/DAG) batch evidence spatial sites
    routers/             API 路由
  tests/                 pytest 集成测试
  scripts/start-test-db.sh  用户态测试库
frontend/src/
  pages/ components/     遗址/探方/层位树/证据/批量/地图/回放/审计
docker-compose.yml       db(postgis) redis minio api web
```
