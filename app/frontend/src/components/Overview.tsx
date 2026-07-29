import { useEffect, useMemo, useState } from "react";
import { Calendar, ArrowRight } from "lucide-react";
import {
  api,
  type Game,
  type Overview as OverviewData,
  type Review,
  type WeeklyReport,
} from "../api";
import { GameIcon, GradeBadge, GradeDot, Spinner, Stars } from "./ui";

// Sentimento em escala monocromática de cinza (cor reservada só p/ grades)
const SENTIMENT_ORDER = ["positive", "neutral", "mixed", "negative"] as const;
const SENTIMENT_FILL: Record<string, string> = {
  positive: "#0E0E10",
  neutral: "#6B6A67",
  mixed: "#A9A7A2",
  negative: "#D3D1CC",
};
const SENTIMENT_LABEL: Record<string, string> = {
  positive: "Positivo",
  neutral: "Neutro",
  mixed: "Misto",
  negative: "Negativo",
};

function SentimentBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((s, n) => s + n, 0) || 1;
  return (
    <div className="flex h-2 w-full overflow-hidden">
      {SENTIMENT_ORDER.map((s) =>
        counts[s] ? (
          <div
            key={s}
            style={{ width: `${(counts[s] / total) * 100}%`, background: SENTIMENT_FILL[s] }}
            title={`${SENTIMENT_LABEL[s]}: ${counts[s]}`}
          />
        ) : null
      )}
    </div>
  );
}

export default function Overview({ games }: { games: Game[] }) {
  const [data, setData] = useState<OverviewData | null>(null);
  const [reports, setReports] = useState<WeeklyReport[] | null>(null);
  const [selected, setSelected] = useState<string>(games[0]?.name ?? "");
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview().then(setData).catch((e) => setError(e.message));
    api.reports().then(setReports).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setReviews(null);
    api.reviews(selected).then(setReviews).catch(() => setReviews([]));
  }, [selected]);

  // sentimento por jogo → mapa {game: {sentiment: n}}
  const sentByGame = useMemo(() => {
    const m: Record<string, Record<string, number>> = {};
    data?.sentiment_by_game.forEach((r) => {
      (m[r.game] ??= {})[r.sentiment] = r.n;
    });
    return m;
  }, [data]);

  const gameStat = (name: string) => data?.per_game.find((g) => g.game === name);
  const current = reports?.find((r) => r.game === selected);
  const meta = games.find((g) => g.name === selected);

  if (error) return <div className="text-bad">Erro ao carregar: {error}</div>;
  if (!data || !reports) return <Spinner label="Carregando dados ao vivo…" />;

  return (
    <div className="space-y-12">
      {/* ===== Cabeçalho de KPIs ===== */}
      <section>
        <div className="flex flex-wrap items-end gap-x-16 gap-y-6">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">
              Reviews analisados
            </div>
            <div className="display mt-1 text-6xl font-black tabular-nums leading-none">
              {data.totals.total_reviews.toLocaleString("pt-BR")}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">
              Nota média
            </div>
            <div className="display mt-1 flex items-baseline gap-1 text-6xl font-black leading-none">
              {data.totals.avg_score.toFixed(2)}
              <span className="text-2xl text-muted">/5</span>
            </div>
          </div>
          <p className="max-w-sm text-sm leading-relaxed text-muted">
            Feedback dos jogadores da Play Store, classificado e resumido com AI Functions.
            Explore tendências acumuladas na aba{" "}
            <span className="font-semibold text-ink">AI/BI</span>.
          </p>
        </div>
      </section>

      {/* ===== Jogos: estrelas + sentimento por jogo ===== */}
      <section>
        <h2 className="display mb-5 text-sm font-bold uppercase tracking-[0.18em] text-muted">
          Por jogo
        </h2>
        <div className="grid grid-cols-1 gap-px bg-line md:grid-cols-2">
          {games.map((g) => {
            const stat = gameStat(g.name);
            const rep = reports.find((r) => r.game === g.name);
            const active = g.name === selected;
            return (
              <button
                key={g.name}
                onClick={() => setSelected(g.name)}
                className={`group flex flex-col gap-4 bg-paper p-6 text-left transition-colors hover:bg-white ${
                  active ? "bg-white" : ""
                }`}
              >
                <div className="flex items-center gap-4">
                  <GameIcon icon={g.icon} name={g.name} size={52} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="display truncate text-lg font-bold">{g.name}</span>
                      {rep && <GradeDot grade={rep.grade} />}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-sm text-muted">
                      {stat && <Stars score={stat.avg_score} />}
                      <span>·</span>
                      <span>{stat?.reviews.toLocaleString("pt-BR")} reviews</span>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted transition-transform group-hover:translate-x-1 group-hover:text-ink" />
                </div>
                <SentimentBar counts={sentByGame[g.name] ?? {}} />
              </button>
            );
          })}
        </div>
        {/* Legenda de sentimento */}
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted">
          {SENTIMENT_ORDER.map((s) => (
            <span key={s} className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5" style={{ background: SENTIMENT_FILL[s] }} />
              {SENTIMENT_LABEL[s]}
            </span>
          ))}
        </div>
      </section>

      {/* ===== Relatório do jogo selecionado ===== */}
      <section className="border-t border-line pt-10">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <GameIcon icon={meta?.icon} name={selected} size={48} />
            <div>
              <h2 className="display text-2xl font-black">{selected}</h2>
              {current && (
                <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                  <Calendar className="h-4 w-4" />
                  {new Date(current.window_start).toLocaleDateString("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    timeZone: "UTC",
                  })}{" "}
                  –{" "}
                  {new Date(current.window_end).toLocaleDateString("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                    timeZone: "UTC",
                  })}
                </div>
              )}
            </div>
          </div>
          {current && <GradeBadge grade={current.grade} />}
        </div>

        {!current ? (
          <p className="text-muted">Sem relatório disponível para {selected}.</p>
        ) : (
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1fr_320px]">
            {/* Relatório textual */}
            <article>
              <h3 className="display mb-4 text-sm font-bold uppercase tracking-[0.18em] text-muted">
                Relatório semanal · gerado por IA
              </h3>
              <div className="report-body text-[15px]">{current.report}</div>
            </article>

            {/* Reviews recentes */}
            <aside>
              <h3 className="display mb-4 text-sm font-bold uppercase tracking-[0.18em] text-muted">
                Reviews recentes
              </h3>
              {!reviews ? (
                <Spinner label="Carregando…" />
              ) : reviews.length === 0 ? (
                <p className="text-sm text-muted">Sem reviews recentes.</p>
              ) : (
                <div className="divide-y divide-line border-y border-line">
                  {reviews.map((r) => (
                    <div key={r.review_id} className="py-3">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-semibold">
                          {r.user_name || "Anônimo"}
                        </span>
                        <Stars score={r.score} />
                      </div>
                      <p className="text-sm leading-relaxed text-muted">{r.content}</p>
                      <time className="mt-1.5 block text-xs text-muted">
                        {new Date(r.at).toLocaleDateString("pt-BR", {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                        })}
                      </time>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          </div>
        )}
      </section>
    </div>
  );
}
