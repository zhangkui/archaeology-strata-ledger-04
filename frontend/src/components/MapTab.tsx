import { useQuery } from "@tanstack/react-query";
import { MapContainer, TileLayer, GeoJSON as GeoJsonLayer, CircleMarker } from "react-leaflet";
import type { Feature, Geometry } from "geojson";
import { api } from "../api";

export default function MapTab({ trenchId }: { trenchId: string }) {
  const { data: fc, isLoading, error } = useQuery({
    queryKey: ["features", trenchId],
    queryFn: () => api.features(trenchId),
  });

  // 自动定位到数据范围
  const firstPoint = fc?.features.find((f) => f.geometry?.type === "Point");
  const center: [number, number] =
    firstPoint?.geometry?.type === "Point"
      ? [firstPoint.geometry.coordinates[1], firstPoint.geometry.coordinates[0]]
      : [39.901, 116.401];

  const polygons = (fc?.features ?? []).filter((f) => f.geometry?.type !== "Point");
  const points = (fc?.features ?? []).filter((f) => f.geometry?.type === "Point");

  return (
    <div className="card">
      <h3>空间视图（PostGIS 校验：出土点必须在探方内）</h3>
      {error && <div className="error">{(error as Error).message}</div>}
      {isLoading ? (
        <p className="muted">加载中…</p>
      ) : (
        <div className="map">
          <MapContainer center={center} zoom={18} scrollWheelZoom style={{ height: "100%" }}>
            <TileLayer
              attribution="&copy; OpenStreetMap"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {polygons.map((f, i) => (
              <GeoJsonLayer
                key={i}
                data={{ type: "Feature", geometry: f.geometry as Geometry, properties: f.properties } as Feature}
                style={{ color: "#8a5a28", weight: 2, fillOpacity: 0.08 }}
              />
            ))}
            {points.map((f, i) => {
              const g = f.geometry as GeoJSON.Point;
              const kind = (f.properties as { kind?: string }).kind;
              return (
                <CircleMarker
                  key={i}
                  center={[g.coordinates[1], g.coordinates[0]]}
                  radius={6}
                  pathOptions={{ color: kind === "sample" ? "#2e6e8a" : "#8c3b34", fillOpacity: 0.8 }}
                />
              );
            })}
          </MapContainer>
        </div>
      )}
      <p className="muted">
        红点＝出土物，蓝点＝样本，棕色面＝探方边界。坐标越界的出土物会被数据库触发器拒绝。
      </p>
    </div>
  );
}
