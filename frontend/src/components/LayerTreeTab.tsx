import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Layer, LayerTreeNode } from "../api";
import { Dialog, ErrorBox, StatusBadge } from "./ui";
import MergeDialog from "./MergeDialog";

function TreeNode({
  node,
  selectedId,
  onSelect,
}: {
  node: LayerTreeNode;
  selectedId: string | null;
  onSelect: (l: Layer) => void;
}) {
  return (
    <div className="tree-node">
      <div
        className={`tree-row ${selectedId === node.layer.id ? "selected" : ""}`}
        style={{ marginLeft: node.depth * 24 }}
        onClick={() => onSelect(node.layer)}
      >
        <span className="edge">{node.depth > 0 ? "└─" : "■"}</span>
        <strong>{node.layer.code}</strong>
        <StatusBadge status={node.layer.status} />
        {node.layer.merged_into_id && (
          <span className="muted">→ 已并入 {node.layer.merged_into_id.slice(0, 8)}</span>
        )}
        <span className="muted" style={{ marginLeft: "auto" }}>
          深 {node.layer.depth_top_cm ?? "?"}–{node.layer.depth_bottom_cm ?? "?"} cm
        </span>
      </div>
      {node.children.map((c) => (
        <TreeNode key={c.layer.id} node={c} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}

function NewLayerForm({ trenchId }: { trenchId: string }) {
  const qc = useQueryClient();
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    code: "",
    opened_on: today,
    soil_color: "",
    depth_top_cm: "",
    depth_bottom_cm: "",
    parent_codes: "",
    original: '{\n  "observed_by": "",\n  "stratum_interpretation": ""\n}',
  });
  const [error, setError] = useState<string | null>(null);
  const { data: layers } = useQuery({
    queryKey: ["layers", trenchId],
    queryFn: () => api.listLayers(trenchId),
  });

  const create = useMutation({
    mutationFn: () => {
      const parent_ids = form.parent_codes
        .split(/[,，\s]+/)
        .filter(Boolean)
        .map((code) => {
          const p = layers?.find((l) => l.code === code.trim());
          if (!p) throw new Error(`父层位编号不存在: ${code}`);
          return p.id;
        });
      return api.createLayer(trenchId, {
        code: form.code,
        opened_on: form.opened_on,
        soil_color: form.soil_color || null,
        depth_top_cm: form.depth_top_cm ? Number(form.depth_top_cm) : null,
        depth_bottom_cm: form.depth_bottom_cm ? Number(form.depth_bottom_cm) : null,
        parent_ids,
        original_observation: JSON.parse(form.original || "{}"),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["layers", trenchId] });
      qc.invalidateQueries({ queryKey: ["tree", trenchId] });
      setError(null);
      setForm({ ...form, code: "", parent_codes: "", depth_top_cm: "", depth_bottom_cm: "" });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="card">
      <h3>新层位</h3>
      <ErrorBox message={error} />
      <div className="form-row">
        <div>
          <label>层位编号 *</label>
          <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如 ③b / L07" />
        </div>
        <div>
          <label>发掘日期</label>
          <input type="date" value={form.opened_on} onChange={(e) => setForm({ ...form, opened_on: e.target.value })} />
        </div>
      </div>
      <div className="form-row">
        <div>
          <label>土色</label>
          <input value={form.soil_color} onChange={(e) => setForm({ ...form, soil_color: e.target.value })} />
        </div>
        <div>
          <label>顶深 cm</label>
          <input type="number" value={form.depth_top_cm} onChange={(e) => setForm({ ...form, depth_top_cm: e.target.value })} />
        </div>
        <div>
          <label>底深 cm</label>
          <input type="number" value={form.depth_bottom_cm} onChange={(e) => setForm({ ...form, depth_bottom_cm: e.target.value })} />
        </div>
      </div>
      <label>父层位编号（逗号分隔；成环将被数据库拒绝）</label>
      <input value={form.parent_codes} onChange={(e) => setForm({ ...form, parent_codes: e.target.value })} placeholder="L01, L02" />
      <label>原始观察记录（创建后不可修改）</label>
      <textarea rows={4} value={form.original} onChange={(e) => setForm({ ...form, original: e.target.value })} />
      <div style={{ marginTop: 10 }}>
        <button disabled={!form.code || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "提交中…" : "登记层位"}
        </button>
      </div>
    </div>
  );
}

function LayerDetail({ layer, trenchId }: { layer: Layer; trenchId: string }) {
  const qc = useQueryClient();
  const [showRevisions, setShowRevisions] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [amend, setAmend] = useState({ soil_color: layer.soil_color ?? "", description: layer.description ?? "" });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["layers", trenchId] });
    qc.invalidateQueries({ queryKey: ["tree", trenchId] });
  };

  const run = useMutation({
    mutationFn: async (fn: () => Promise<unknown>) => fn(),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="card">
      <h3>
        层位 {layer.code} <StatusBadge status={layer.status} />
      </h3>
      <ErrorBox message={error} />
      <p className="muted">
        发掘日期 {layer.opened_on}
        {layer.closed_on ? ` ～ ${layer.closed_on}` : ""} · ID {layer.id.slice(0, 8)}
      </p>

      <h4>原始观察值（只读证据）</h4>
      <pre>{JSON.stringify(layer.original_observation, null, 2)}</pre>

      <h4>修订（不覆盖原始观察，逐字段留痕）</h4>
      <label>土色</label>
      <input value={amend.soil_color} onChange={(e) => setAmend({ ...amend, soil_color: e.target.value })} />
      <label>描述</label>
      <textarea rows={2} value={amend.description} onChange={(e) => setAmend({ ...amend, description: e.target.value })} />
      <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={() => run.mutate(() => api.amendLayer(layer.id, {
          soil_color: amend.soil_color || null,
          description: amend.description || null,
        }))}>保存修订</button>
        {layer.status === "open" && (
          <button className="secondary" onClick={() => run.mutate(() => api.closeLayer(layer.id))}>关闭层位</button>
        )}
        {layer.status === "closed" && (
          <button className="secondary" onClick={() => run.mutate(() => api.reopenLayer(layer.id))}>重新开放</button>
        )}
        <button className="secondary" onClick={() => setShowRevisions(true)}>查看修订时间线</button>
        {layer.status !== "merged" && (
          <button className="secondary" onClick={() => setShowMerge(true)}>合并到其他层位…</button>
        )}
        <button
          className="danger"
          onClick={() => {
            if (confirm(`删除层位 ${layer.code}？存在子层位或证据引用时将被拒绝。`)) {
              run.mutate(() => api.deleteLayer(layer.id));
            }
          }}
        >
          删除
        </button>
      </div>

      {showRevisions && (
        <RevisionsDialog layerId={layer.id} onClose={() => setShowRevisions(false)} />
      )}
      {showMerge && (
        <MergeDialog
          source={layer}
          trenchId={trenchId}
          onClose={() => setShowMerge(false)}
          onDone={invalidate}
        />
      )}
    </div>
  );
}

function RevisionsDialog({ layerId, onClose }: { layerId: string; onClose: () => void }) {
  const { data: revisions, isLoading } = useQuery({
    queryKey: ["revisions", layerId],
    queryFn: () => api.revisions(layerId),
  });
  return (
    <Dialog title="修订时间线（只追加证据记录）" onClose={onClose}>
      {isLoading ? (
        <p className="muted">加载中…</p>
      ) : (
        revisions?.map((r) => (
          <div key={r.id} className="revision">
            <div>
              <strong>{r.kind === "create" ? "创建" : `修订字段 ${r.field}`}</strong>{" "}
              <span className="muted">{new Date(r.revised_at).toLocaleString()} · {r.actor}</span>
            </div>
            {r.kind === "amend" && (
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {JSON.stringify(r.old_value)} → {JSON.stringify(r.new_value)}
              </div>
            )}
          </div>
        ))
      )}
    </Dialog>
  );
}

export default function LayerTreeTab({ trenchId }: { trenchId: string }) {
  const { data: tree, isLoading, error } = useQuery({
    queryKey: ["tree", trenchId],
    queryFn: () => api.layerTree(trenchId),
  });
  const [selected, setSelected] = useState<Layer | null>(null);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, alignItems: "start" }}>
      <div>
        <ErrorBox message={error ? (error as Error).message : null} />
        <div className="card">
          <h3>地层层位关系</h3>
          {isLoading ? (
            <p className="muted">加载中…</p>
          ) : (
            tree?.map((n) => (
              <TreeNode key={n.layer.id} node={n} selectedId={selected?.id ?? null} onSelect={setSelected} />
            ))
          )}
          {tree && tree.length === 0 && <p className="muted">尚无层位，请在右侧登记。</p>}
        </div>
        <div style={{ height: 16 }} />
        <NewLayerForm trenchId={trenchId} />
      </div>
      <div>{selected ? <LayerDetail layer={selected} trenchId={trenchId} /> : (
        <div className="card muted">点击左侧层位查看详情、修订与合并操作。</div>
      )}</div>
    </div>
  );
}
