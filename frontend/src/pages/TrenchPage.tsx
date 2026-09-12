import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import LayerTreeTab from "../components/LayerTreeTab";
import EvidenceTab from "../components/EvidenceTab";
import BatchTab from "../components/BatchTab";
import MapTab from "../components/MapTab";
import ReplayTab from "../components/ReplayTab";

const TABS = [
  { key: "layers", label: "层位与修订" },
  { key: "evidence", label: "出土物 / 样本 / 照片" },
  { key: "batch", label: "批量导入（单事务）" },
  { key: "map", label: "空间视图" },
  { key: "replay", label: "按日期回放" },
] as const;

export default function TrenchPage() {
  const { siteId = "", trenchId = "" } = useParams();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("layers");
  const { data: trenches } = useQuery({
    queryKey: ["trenches", siteId],
    queryFn: () => api.listTrenches(siteId),
  });
  const trench = trenches?.find((t) => t.id === trenchId);

  return (
    <div>
      <p className="muted">
        <a href={`/sites/${siteId}`}>← 返回遗址</a>
      </p>
      <h2>
        探方 {trench?.code ?? "…"}{" "}
        <span className="muted">开工 {trench?.opened_on}</span>
      </h2>

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "layers" && <LayerTreeTab trenchId={trenchId} />}
      {tab === "evidence" && <EvidenceTab trenchId={trenchId} />}
      {tab === "batch" && <BatchTab trenchId={trenchId} />}
      {tab === "map" && <MapTab trenchId={trenchId} />}
      {tab === "replay" && <ReplayTab trenchId={trenchId} />}
    </div>
  );
}
