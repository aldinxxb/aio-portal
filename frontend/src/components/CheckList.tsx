import { useState } from "react";
import type { Item } from "../api";

type Props = {
  items: Item[];
  selected: string[];
  onToggle: (id: string) => void;
  filterable?: boolean;
};

export default function CheckList({ items, selected, onToggle, filterable = false }: Props) {
  const [filter, setFilter] = useState("");

  const shown = items.filter((item) =>
    (item.label ?? item.id).toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div>
      {filterable && (
        <input
          placeholder="Filter…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ marginBottom: 6, width: "100%", boxSizing: "border-box" }}
        />
      )}
      <div
        style={{
          maxHeight: 220,
          overflowY: "auto",
          border: "1px solid #ccc",
          borderRadius: 6,
          padding: 8,
        }}
      >
        {shown.map((item) => (
          <label key={item.id} style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={selected.includes(item.id)}
              onChange={() => onToggle(item.id)}
            />{" "}
            {item.label ?? item.id}
          </label>
        ))}
        {shown.length === 0 && <em>No match</em>}
      </div>
    </div>
  );
}