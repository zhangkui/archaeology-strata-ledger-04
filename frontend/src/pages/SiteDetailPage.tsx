import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ErrorBox } from "../components/ui";

export default function SiteDetailPage() {
  const { siteId = "" } = useParams();
  const qc = useQueryClient();
  const { data: sites } = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const site = sites?.find((s) => s.id === siteId);
  const { data: trenches, isLoading } = useQuery({
    queryKey: ["trenches", siteId],
    queryFn: () => api.listTrenches(siteId),
    enabled: !!siteId,
  });

  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ code: "", opened_on: today, geom: "" });
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.createTrench(siteId, {
        code: form.code,
        opened_on: form.opened_on,
        geom: form.geom.trim() ? JSON.parse(form.geom) : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trenches", siteId] });
      setForm({ code: "", opened_on: today, geom: "" });
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div>
      <p className="muted"><Link to="/sites">← 遗址列表</Link></p>
      <h2>{site?.name ?? "遗址"} <span className="muted">({site?.code})</span></h2>
      <ErrorBox message={error} />
      <h3>探方</h3>
      {isLoading ? (
        <p className="muted">加载中…</p>
      ) : (
        <table>
          <thead>
            <tr><th>编号</th><th>开工日期</th><th>收工日期</th><th>边界</th><th></th></tr>
          </thead>
          <tbody>
            {trenches?.map((t) => (
              <tr key={t.id}>
                <td>{t.code}</td>
                <td>{t.opened_on}</td>
                <td>{t.closed_on ?? "—"}</td>
                <td>{t.geom ? "已绘" : "未绘"}</td>
                <td>
                  <Link to={`/sites/${siteId}/trenches/${t.id}`}>打开层位工作区 →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="card" style={{ marginTop: 20, maxWidth: 640 }}>
        <h3>新探方</h3>
        <div className="form-row">
          <div>
            <label>探方编号</label>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如 T0103" />
          </div>
          <div>
            <label>开工日期</label>
            <input type="date" value={form.opened_on} onChange={(e) => setForm({ ...form, opened_on: e.target.value })} />
          </div>
        </div>
        <label>探方边界（GeoJSON Polygon，坐标 [经度,纬度]；出土物坐标必须落在此范围内）</label>
        <textarea
          rows={3}
          value={form.geom}
          onChange={(e) => setForm({ ...form, geom: e.target.value })}
          placeholder='{"type":"Polygon","coordinates":[[[116.401,39.901],[116.402,39.901],[116.402,39.902],[116.401,39.901]]]}'
        />
        <div style={{ marginTop: 12 }}>
          <button disabled={!form.code || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "创建中…" : "创建探方"}
          </button>
        </div>
      </div>
    </div>
  );
}
