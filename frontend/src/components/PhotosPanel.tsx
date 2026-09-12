import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ErrorBox } from "./ui";

/** 照片证据：上传到 MinIO 并在库内登记引用，按层位查看。 */
export default function PhotosPanel({ trenchId }: { trenchId: string }) {
  const qc = useQueryClient();
  const { data: layers } = useQuery({
    queryKey: ["layers", trenchId],
    queryFn: () => api.listLayers(trenchId),
  });
  const [layerId, setLayerId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: photos } = useQuery({
    queryKey: ["photos", layerId],
    queryFn: () => api.listPhotos(layerId || undefined),
    enabled: !!layerId,
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadPhoto(layerId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["photos", layerId] });
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>照片证据（MinIO 对象存储）</h3>
      <ErrorBox message={error} />
      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "8px 0" }}>
        <select value={layerId} onChange={(e) => setLayerId(e.target.value)} style={{ width: 220 }}>
          <option value="">选择层位…</option>
          {layers?.map((l) => (
            <option key={l.id} value={l.id}>{l.code}</option>
          ))}
        </select>
        <input
          type="file"
          accept="image/*"
          disabled={!layerId}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload.mutate(f);
            e.target.value = "";
          }}
        />
      </div>
      {layerId && (
        <table>
          <thead><tr><th>文件</th><th>大小</th><th>拍摄日期</th><th></th></tr></thead>
          <tbody>
            {photos?.map((p) => (
              <tr key={p.id}>
                <td>{p.filename}</td>
                <td>{p.size_bytes ? `${(p.size_bytes / 1024).toFixed(0)} KB` : "—"}</td>
                <td>{p.taken_on ?? "—"}</td>
                <td>{p.url && <a href={p.url} target="_blank" rel="noreferrer">查看</a>}</td>
              </tr>
            ))}
            {photos?.length === 0 && (
              <tr><td colSpan={4} className="muted">该层位暂无照片</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
