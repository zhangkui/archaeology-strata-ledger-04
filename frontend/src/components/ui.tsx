import { useState } from "react";

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="error">{message}</div>;
}

export function StatusBadge({ status }: { status: string }) {
  const label = status === "open" ? "开放" : status === "closed" ? "已关闭" : "已合并";
  return <span className={`badge ${status}`}>{label}</span>;
}

export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}

/** 简单受控 JSON 文本域 */
export function JsonField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      <label>{label}（GeoJSON / JSON）</label>
      <textarea
        rows={3}
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          const v = e.target.value;
          if (v.trim()) {
            try {
              JSON.parse(v);
              setErr(null);
            } catch {
              setErr("JSON 格式错误");
            }
          } else {
            setErr(null);
          }
          onChange(v);
        }}
      />
      {err && <div className="muted" style={{ color: "#a8332b" }}>{err}</div>}
    </>
  );
}
