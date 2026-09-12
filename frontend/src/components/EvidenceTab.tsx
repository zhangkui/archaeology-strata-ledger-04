import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ErrorBox, StatusBadge } from "./ui";
import PhotosPanel from "./PhotosPanel";

export default function EvidenceTab({ trenchId }: { trenchId: string }) {
  const qc = useQueryClient();
  const { data: layers } = useQuery({
    queryKey: ["layers", trenchId],
    queryFn: () => api.listLayers(trenchId),
  });
  const { data: finds } = useQuery({
    queryKey: ["finds", trenchId],
    queryFn: () => api.listFinds(trenchId),
  });
  const { data: samples } = useQuery({
    queryKey: ["samples", trenchId],
    queryFn: () => api.listSamples(trenchId),
  });

  const openLayers = layers?.filter((l) => l.status === "open") ?? [];
  const layerCode = (id: string) => layers?.find((l) => l.id === id)?.code ?? id.slice(0, 8);

  const [kind, setKind] = useState<"find" | "sample">("find");
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    layer_id: "", code: "", category: "陶片", material: "炭样", found_on: today,
    collected_on: today, note: "", lon: "", lat: "",
  });
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["finds", trenchId] });
    qc.invalidateQueries({ queryKey: ["samples", trenchId] });
  };

  const submit = useMutation<unknown, Error, void>({
    mutationFn: () => {
      const position =
        form.lon && form.lat
          ? { type: "Point", coordinates: [Number(form.lon), Number(form.lat)] }
          : null;
      if (kind === "find") {
        return api.createFind({
          layer_id: form.layer_id,
          code: form.code,
          category: form.category,
          found_on: form.found_on,
          note: form.note || null,
          position,
        });
      }
      return api.createSample({
        layer_id: form.layer_id,
        code: form.code,
        material: form.material,
        collected_on: form.collected_on,
        note: form.note || null,
        position,
      });
    },
    onSuccess: () => {
      invalidate();
      setError(null);
      setForm({ ...form, code: "", note: "", lon: "", lat: "" });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div>
      <div className="card">
        <h3>登记出土物 / 样本</h3>
        <ErrorBox message={error} />
        {openLayers.length === 0 && (
          <div className="error">当前探方没有开放层位，出土物无法登记。请先在层位页开放一个层位。</div>
        )}
        <div className="form-row">
          <div>
            <label>类型</label>
            <select value={kind} onChange={(e) => setKind(e.target.value as "find" | "sample")}>
              <option value="find">出土物</option>
              <option value="sample">样本</option>
            </select>
          </div>
          <div>
            <label>归属开放层位 *</label>
            <select value={form.layer_id} onChange={(e) => setForm({ ...form, layer_id: e.target.value })}>
              <option value="">请选择…</option>
              {openLayers.map((l) => (
                <option key={l.id} value={l.id}>{l.code}</option>
              ))}
            </select>
          </div>
          <div>
            <label>编号 *</label>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </div>
        </div>
        <div className="form-row">
          {kind === "find" ? (
            <>
              <div>
                <label>类别</label>
                <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
              </div>
              <div>
                <label>出土日期</label>
                <input type="date" value={form.found_on} onChange={(e) => setForm({ ...form, found_on: e.target.value })} />
              </div>
            </>
          ) : (
            <>
              <div>
                <label>材质</label>
                <input value={form.material} onChange={(e) => setForm({ ...form, material: e.target.value })} />
              </div>
              <div>
                <label>采集日期</label>
                <input type="date" value={form.collected_on} onChange={(e) => setForm({ ...form, collected_on: e.target.value })} />
              </div>
            </>
          )}
          <div>
            <label>经度（可选）</label>
            <input type="number" step="0.000001" value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} />
          </div>
          <div>
            <label>纬度（可选，须落在探方内）</label>
            <input type="number" step="0.000001" value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} />
          </div>
        </div>
        <label>备注</label>
        <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        <div style={{ marginTop: 10 }}>
          <button disabled={!form.layer_id || !form.code || submit.isPending} onClick={() => submit.mutate()}>
            {submit.isPending ? "提交中…" : "登记"}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>出土物（{finds?.length ?? 0}）</h3>
        <table>
          <thead><tr><th>编号</th><th>层位</th><th>类别</th><th>日期</th><th>层位状态</th></tr></thead>
          <tbody>
            {finds?.map((f) => {
              const layer = layers?.find((l) => l.id === f.layer_id);
              return (
                <tr key={f.id}>
                  <td>{f.code}</td>
                  <td>{layerCode(f.layer_id)}</td>
                  <td>{f.category}</td>
                  <td>{f.found_on}</td>
                  <td>{layer && <StatusBadge status={layer.status} />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>样本（{samples?.length ?? 0}）</h3>
        <table>
          <thead><tr><th>编号</th><th>层位</th><th>材质</th><th>采集日期</th></tr></thead>
          <tbody>
            {samples?.map((s) => (
              <tr key={s.id}>
                <td>{s.code}</td>
                <td>{layerCode(s.layer_id)}</td>
                <td>{s.material}</td>
                <td>{s.collected_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <PhotosPanel trenchId={trenchId} />
    </div>
  );
}
