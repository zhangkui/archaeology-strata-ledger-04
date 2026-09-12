import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, BatchResult } from "../api";
import { ErrorBox } from "./ui";

const EXAMPLE = `[
  {
    "op": "layer",
    "ref": "L5",
    "data": {
      "code": "L05",
      "opened_on": "2026-09-01",
      "soil_color": "灰褐色",
      "depth_top_cm": 40,
      "depth_bottom_cm": 62,
      "parent_ids": [{"$ref": "L4"}],
      "original_observation": {"observed_by": "li", "note": "含炭粒"}
    }
  },
  {
    "op": "find",
    "ref": "F1",
    "data": {
      "layer_id": {"$ref": "L5"},
      "code": "F-2026-018",
      "category": "陶罐",
      "found_on": "2026-09-02",
      "position": {"type": "Point", "coordinates": [116.4015, 39.9015]}
    }
  },
  {
    "op": "sample",
    "data": {
      "layer_id": {"$ref": "L5"},
      "find_id": {"$ref": "F1"},
      "code": "C14-018",
      "material": "炭样",
      "collected_on": "2026-09-02"
    }
  }
]`;

export default function BatchTab({ trenchId }: { trenchId: string }) {
  const [text, setText] = useState(EXAMPLE);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchResult | null>(null);

  const submit = useMutation({
    mutationFn: () => {
      const items = JSON.parse(text);
      if (!Array.isArray(items)) throw new Error("顶层必须是数组");
      return api.batch(trenchId, items);
    },
    onSuccess: (r) => {
      setResult(r);
      setError(null);
    },
    onError: (e: Error) => {
      setError(e.message);
      setResult(null);
    },
  });

  return (
    <div>
      <div className="card">
        <h3>批量导入（原子事务）</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          整批 JSON 只在一个数据库事务内提交：任一项违反规则（地层成环、归属非开放层位、坐标越界、编号重复…）
          都会<strong>整体回滚</strong>，不留半成品。批内可用 <code>{"{\"$ref\":\"名字\"}"}</code> 引用同批先建实体。
        </p>
        <ErrorBox message={error} />
        {result?.committed && (
          <div className="success">
            ✅ 已提交 {result.count} 项：<code>{JSON.stringify(result.ids)}</code>
          </div>
        )}
        <textarea rows={20} style={{ fontFamily: "monospace", fontSize: 12 }} value={text}
          onChange={(e) => setText(e.target.value)} />
        <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
          <button disabled={submit.isPending} onClick={() => submit.mutate()}>
            {submit.isPending ? "提交中…" : "整批提交"}
          </button>
          <button className="secondary" onClick={() => setText(EXAMPLE)}>恢复示例</button>
        </div>
      </div>
    </div>
  );
}
