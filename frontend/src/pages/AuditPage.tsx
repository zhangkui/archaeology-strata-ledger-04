import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

export default function AuditPage() {
  const [filter, setFilter] = useState("");
  const { data: events, isLoading } = useQuery({
    queryKey: ["audit", filter],
    queryFn: () => api.audit(filter ? { event_type: filter } : {}),
  });

  return (
    <div>
      <h2>审计事件流</h2>
      <div className="card">
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <input
            placeholder="按事件类型过滤，如 layer.merged / batch.committed"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        {isLoading ? (
          <p className="muted">加载中…</p>
        ) : (
          <table>
            <thead>
              <tr><th>时间</th><th>事件</th><th>实体</th><th>内容</th><th>操作人</th></tr>
            </thead>
            <tbody>
              {events?.map((e) => (
                <tr key={e.id}>
                  <td>{new Date(e.created_at).toLocaleString()}</td>
                  <td><strong>{e.event_type}</strong></td>
                  <td className="muted">{e.entity_type}{e.entity_id ? `/${e.entity_id.slice(0, 8)}` : ""}</td>
                  <td style={{ fontSize: 12 }}><code>{JSON.stringify(e.payload)}</code></td>
                  <td>{e.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
