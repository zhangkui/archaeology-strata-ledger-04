import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Site } from "../api";
import { ErrorBox } from "../components/ui";

export default function SitesPage() {
  const qc = useQueryClient();
  const { data: sites, isLoading } = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const [form, setForm] = useState({ code: "", name: "", description: "", centroid: "" });
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => {
      const centroid = form.centroid.trim() ? JSON.parse(form.centroid) : null;
      return api.createSite({
        code: form.code,
        name: form.name,
        description: form.description || null,
        centroid,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sites"] });
      setForm({ code: "", name: "", description: "", centroid: "" });
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div>
      <h2>遗址</h2>
      <ErrorBox message={error} />
      {isLoading ? (
        <p className="muted">加载中…</p>
      ) : (
        <div className="grid">
          {sites?.map((s: Site) => (
            <Link key={s.id} to={`/sites/${s.id}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
              <h3>{s.name}</h3>
              <div className="muted">编号 {s.code}</div>
              {s.description && <p style={{ margin: "8px 0 0", fontSize: 13 }}>{s.description}</p>}
            </Link>
          ))}
          <div className="card">
            <h3>新建遗址</h3>
            <label>遗址编号</label>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如 YX-2026-01" />
            <label>名称</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <label>中心点（GeoJSON Point，可选）</label>
            <input
              value={form.centroid}
              onChange={(e) => setForm({ ...form, centroid: e.target.value })}
              placeholder='{"type":"Point","coordinates":[116.40,39.90]}'
            />
            <label>说明</label>
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <div style={{ marginTop: 12 }}>
              <button disabled={!form.code || !form.name || create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? "创建中…" : "创建遗址"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
