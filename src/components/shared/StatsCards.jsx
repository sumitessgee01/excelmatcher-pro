const CARDS = [
  { key: "total", label: "Total", color: "text-blue-300" },
  { key: "matched", label: "Matched", color: "text-green-300" },
  { key: "mismatch", label: "Mismatch", color: "text-red-300" },
  { key: "qty_mismatch", label: "Qty Mismatch", color: "text-yellow-300" },
  { key: "only_in_f1", label: "Only F1", color: "text-sky-300" },
  { key: "only_in_f2", label: "Only F2", color: "text-slate-300" }
];

export default function StatsCards({ stats }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {CARDS.map((card) => (
        <div key={card.key} className="card p-3">
          <div className="text-xs text-muted">{card.label}</div>
          <div className={`mt-1 text-xl font-bold ${card.color}`}>{Number(stats?.[card.key] || 0)}</div>
        </div>
      ))}
    </div>
  );
}
