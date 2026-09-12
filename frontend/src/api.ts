export type LayerStatus = "open" | "closed" | "merged";

export interface Site {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  centroid?: GeoJSON.Point | null;
  boundary?: GeoJSON.Polygon | null;
}

export interface Trench {
  id: string;
  site_id: string;
  code: string;
  elevation?: number | null;
  opened_on: string;
  closed_on?: string | null;
  note?: string | null;
  geom?: GeoJSON.Polygon | null;
}

export interface Layer {
  id: string;
  trench_id: string;
  code: string;
  status: LayerStatus;
  opened_on: string;
  closed_on?: string | null;
  description?: string | null;
  soil_color?: string | null;
  soil_texture?: string | null;
  depth_top_cm?: number | null;
  depth_bottom_cm?: number | null;
  original_observation: Record<string, unknown>;
  merged_into_id?: string | null;
  parent_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface LayerTreeNode {
  layer: Layer;
  children: LayerTreeNode[];
  depth: number;
}

export interface Revision {
  id: string;
  layer_id: string;
  kind: "create" | "amend";
  field?: string | null;
  old_value: unknown;
  new_value: unknown;
  actor: string;
  reason?: string | null;
  revised_at: string;
}

export interface Find {
  id: string;
  layer_id: string;
  code: string;
  category: string;
  found_on: string;
  z_elevation?: number | null;
  note?: string | null;
  position?: GeoJSON.Point | null;
}

export interface Sample {
  id: string;
  layer_id: string;
  find_id?: string | null;
  code: string;
  material: string;
  collected_on: string;
  note?: string | null;
  position?: GeoJSON.Point | null;
}

export interface Photo {
  id: string;
  layer_id?: string | null;
  find_id?: string | null;
  filename: string;
  content_type?: string | null;
  size_bytes?: number | null;
  taken_on?: string | null;
  url?: string | null;
}

export interface AuditEvent {
  id: number;
  event_type: string;
  entity_type: string;
  entity_id?: string | null;
  payload: Record<string, unknown>;
  actor: string;
  created_at: string;
}

export interface MergeResult {
  merge_relation_id: string;
  source_layer_id: string;
  target_layer_id: string;
  migrated_finds: number;
  migrated_photos: number;
  migrated_samples: number;
}

export interface BatchResult {
  committed: boolean;
  count: number;
  ids: Record<string, string>;
  error?: { detail?: unknown } | null;
}

export interface Replay {
  as_of: string;
  layers: Array<Record<string, unknown>>;
  finds: Array<Record<string, unknown>>;
  revisions: Revision[];
  audit_events: AuditEvent[];
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const actor = localStorage.getItem("actor") || "director-li";
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Actor": actor,
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.message || body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listSites: () => request<Site[]>("/api/sites"),
  createSite: (data: Partial<Site>) =>
    request<Site>("/api/sites", { method: "POST", body: JSON.stringify(data) }),

  listTrenches: (siteId: string) =>
    request<Trench[]>(`/api/sites/${siteId}/trenches`),
  createTrench: (siteId: string, data: Partial<Trench>) =>
    request<Trench>(`/api/sites/${siteId}/trenches`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listLayers: (trenchId: string) =>
    request<Layer[]>(`/api/trenches/${trenchId}/layers`),
  layerTree: (trenchId: string) =>
    request<LayerTreeNode[]>(`/api/trenches/${trenchId}/layer-tree`),
  createLayer: (trenchId: string, data: unknown) =>
    request<Layer>(`/api/trenches/${trenchId}/layers`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  amendLayer: (layerId: string, data: unknown) =>
    request<Layer>(`/api/layers/${layerId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  closeLayer: (layerId: string) =>
    request<Layer>(`/api/layers/${layerId}/close`, { method: "POST" }),
  reopenLayer: (layerId: string) =>
    request<Layer>(`/api/layers/${layerId}/reopen`, { method: "POST" }),
  addParent: (layerId: string, parentId: string, relation = "stratigraphic") =>
    request<void>(`/api/layers/${layerId}/parents`, {
      method: "POST",
      body: JSON.stringify({ parent_id: parentId, relation }),
    }),
  deleteLayer: (layerId: string) =>
    request<void>(`/api/layers/${layerId}`, { method: "DELETE" }),
  revisions: (layerId: string) =>
    request<Revision[]>(`/api/layers/${layerId}/revisions`),
  merge: (data: unknown) =>
    request<MergeResult>("/api/layers/merge", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listFinds: (trenchId: string) =>
    request<Find[]>(`/api/trenches/${trenchId}/finds`),
  createFind: (data: unknown) =>
    request<Find>("/api/finds", { method: "POST", body: JSON.stringify(data) }),
  listSamples: (trenchId: string) =>
    request<Sample[]>(`/api/trenches/${trenchId}/samples`),
  createSample: (data: unknown) =>
    request<Sample>("/api/samples", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listPhotos: (layerId?: string) =>
    request<Photo[]>(`/api/photos${layerId ? `?layer_id=${layerId}` : ""}`),
  uploadPhoto: (layerId: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    form.set("layer_id", layerId);
    return fetch("/api/photos", {
      method: "POST",
      headers: { "X-Actor": localStorage.getItem("actor") || "director-li" },
      body: form,
    }).then(async (r) => {
      if (!r.ok) throw new Error(await r.text());
      return r.json() as Promise<Photo>;
    });
  },

  batch: (trenchId: string, items: unknown) =>
    request<BatchResult>(`/api/trenches/${trenchId}/batch`, {
      method: "POST",
      body: JSON.stringify({ trench_id: trenchId, items }),
    }),
  features: (trenchId: string) =>
    request<GeoJSON.FeatureCollection>(`/api/trenches/${trenchId}/features`),
  replay: (trenchId: string, asOf: string) =>
    request<Replay>(`/api/trenches/${trenchId}/replay?as_of=${encodeURIComponent(asOf)}`),
  audit: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request<AuditEvent[]>(`/api/audit${qs ? `?${qs}` : ""}`);
  },
};
