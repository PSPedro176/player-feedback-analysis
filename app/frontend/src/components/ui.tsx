import { Star } from "lucide-react";

const GRADE = {
  green: { label: "Saudável", text: "text-good", dot: "bg-good" },
  yellow: { label: "Atenção", text: "text-warn", dot: "bg-warn" },
  red: { label: "Crítico", text: "text-bad", dot: "bg-bad" },
} as const;

export function GradeBadge({ grade }: { grade: string }) {
  const g = GRADE[grade as keyof typeof GRADE] ?? GRADE.green;
  return (
    <span className="inline-flex items-center gap-2 border border-line bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-wider">
      <span className={`h-2 w-2 rounded-full ${g.dot}`} />
      <span className={g.text}>{g.label}</span>
    </span>
  );
}

export function GradeDot({ grade }: { grade: string }) {
  const g = GRADE[grade as keyof typeof GRADE] ?? GRADE.green;
  return <span className={`h-2 w-2 shrink-0 rounded-full ${g.dot}`} title={g.label} />;
}

export function Stars({ score }: { score: number }) {
  return (
    <span className="inline-flex items-center gap-1 font-semibold tabular-nums">
      <Star className="h-3.5 w-3.5 fill-ink text-ink" />
      {score.toFixed(2)}
    </span>
  );
}

export function GameIcon({
  icon,
  name,
  size = 44,
}: {
  icon?: string;
  name: string;
  size?: number;
}) {
  return (
    <div
      className="relative shrink-0 overflow-hidden border border-line bg-ink"
      style={{ width: size, height: size }}
    >
      {icon ? (
        <img
          src={icon}
          alt={name}
          className="h-full w-full object-cover"
          onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
        />
      ) : null}
      <div
        className="absolute inset-0 -z-10 flex items-center justify-center font-display font-black text-paper"
        style={{ fontSize: size * 0.4 }}
      >
        {name.charAt(0)}
      </div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-muted">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-ink" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}
