import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Layer } from "../api";
import { Dialog, ErrorBox } from "./ui";

export default function MergeDialog({
  source,
  trenchId,
  onClose,
  onDone,
}: {
  source: Layer;
  trenchId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { data: layers } = useQuery({
    queryKey: ["layers", trenchId],
    queryFn: () => api.listLayers(trenchId),
  });
  const [targetId, setTargetId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const targets = layers?.filter((l) => l.id !== source.id && l.status !== "merged") ?? [];

  const merge = useMutation({
    mutationFn: () =>
      api.merge({ source_layer_id: source.id, target_layer_id: targetId, reason: reason || null }),
    onSuccess: (r) => {
      setResult(
        `合并完成：迁移出土物 ${r.migrated_finds} 件、照片 ${r.migrated_photos} 张、样本 ${r.migrated_samples} 份；已生成迁移关系与审计事件。`
      );
      onDone();
      setTimeout(onClose, 2200);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Dialog title={`合并层位 ${source.code}`} onClose={onClose}>
      <p className="muted" style={{ marginTop: 0 }}>
        源层位的出土物、照片、样本将迁移到目标层位；地层父子关系一并改写；
        源层位变为「已合并」终态，全过程单事务并记录审计事件。
      </p>
      <ErrorBox message={error} />
      {result && <div className="success">{result}</div>}
      <label>合并到（目标必须为开放层位）</label>
      <select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
        <option value="">请选择…</option>
        {targets.map((l) => (
          <option key={l.id} value={l.id}>
            {l.code}（{l.status === "open" ? "开放" : "已关闭"}）
          </option>
        ))}
      </select>
      <label>合并理由</label>
      <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button disabled={!targetId || merge.isPending} onClick={() => merge.mutate()}>
          {merge.isPending ? "合并中…" : "确认合并"}
        </button>
        <button className="secondary" onClick={onClose}>取消</button>
      </div>
    </Dialog>
  );
}
