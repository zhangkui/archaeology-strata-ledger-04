import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, Replay } from "../api";
import { ErrorBox, StatusBadge } from "./ui";

export default function ReplayTab({ trenchId }: { trenchId: string }) {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const [asOf, setAsOf] = useState(now.toISOString().slice(0, 16));
  const [data, setData] = useState<Replay | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: () => api.replay(trenchId, new Date(asOf).toISOString()),
    onSuccess: setData,
    onError: (e: Error) => {
      setError(e.message);
      setData(null);
    },
  });

  return (
    <div>
      <div className="card">
        <h3>按发掘日期回放数据版本</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          依据只追加的层位修订流（layer_revisions）重放到指定时刻：重建当时每个层位的字段状态，
          并列出当时已登记的出土物与审计事件。
        </p>
        <ErrorBox message={error} />
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ width: 240 }} />
          <button onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? "回放中…" : "回放"}
          </button>
        </div>
      </div>

      {data && (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>层位快照（{data.layers.length}）</h3>
            <table>
              <thead><tr><th>编号</th><th>状态</th><th>土色</th><th>深度 cm</th><th>修订次数</th></tr></thead>
              <tbody>
                {data.layers.map((l, i) => (
                  <tr key={String(l.id ?? i)}>
                    <td>{String(l.code ?? "?")}</td>
                    <td><StatusBadge status={String(l.status ?? "open")} /></td>
                    <td>{String(l.soil_color ?? "—")}</td>
                    <td>{String(l.depth_top_cm ?? "?")}–{String(l.depth_bottom_cm ?? "?")}</td>
                    <td>{data.revisions.filter((r) => r.layer_id === l.id).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>当时出土物（{data.finds.length}）</h3>
            <table>
              <thead><tr><th>编号</th><th>类别</th><th>出土日期</th></tr></thead>
              <tbody>
                {data.finds.map((f) => (
                  <tr key={String(f.id)}>
                    <td>{String(f.code)}</td><td>{String(f.category)}</td><td>{String(f.found_on)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>修订与审计时间线（{data.revisions.length + data.audit_events.length}）</h3>
            {[
              ...data.revisions.map((r) => ({ at: r.revised_at, text: `[修订] 层位 ${String(r.layer_id).slice(0, 8)} ${r.kind === "create" ? "创建" : r.field}：${JSON.stringify(r.old_value)} → ${JSON.stringify(r.new_value)}（${r.actor}）` })),
              ...data.audit_events.map((e) => ({ at: e.created_at, text: `[审计] ${e.event_type}（${e.actor}）${Object.keys(e.payload).length ? " " + JSON.stringify(e.payload) : ""}` })),
            ]
              .sort((a, b) => a.at.localeCompare(b.at))
              .map((x, i) => <div key={i} className="revision">{new Date(x.at).toLocaleString()} · {x.text}</div>)}
          </div>
        </>
      )}
    </div>
  );
}
