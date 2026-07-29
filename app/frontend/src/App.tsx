import { useEffect, useState } from "react";
import { api, type AppConfig } from "./api";
import { Spinner } from "./components/ui";
import Overview from "./components/Overview";
import Embed from "./components/Embed";

type Tab = "overview" | "dashboard";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Visão geral" },
  { id: "dashboard", label: "AI/BI" },
];

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      {/* Header — minimalist, high contrast, no gradient */}
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-content items-center justify-between gap-6 px-6 py-4">
          <div className="flex items-baseline gap-3">
            <span className="brand-title text-2xl leading-none">Player Feedback</span>
            <span className="hidden text-sm font-semibold uppercase tracking-[0.18em] text-muted sm:inline">
              Analysis
            </span>
          </div>
          <nav className="flex items-center gap-6">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`relative py-1 text-sm font-semibold transition-colors ${
                  tab === t.id ? "text-ink" : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
                {tab === t.id && (
                  <span className="absolute -bottom-[17px] left-0 h-[2px] w-full bg-ink" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main
        className={`mx-auto w-full flex-1 px-6 py-10 ${
          tab === "dashboard" ? "max-w-[1800px]" : "max-w-content"
        }`}
      >
        {error && (
          <div className="border border-bad/30 bg-bad/5 p-4 text-sm text-bad">
            Erro ao inicializar: {error}
          </div>
        )}
        {!config ? (
          <div className="flex justify-center py-32">
            <Spinner label="Conectando ao workspace…" />
          </div>
        ) : (
          <div key={tab} className="animate-fade">
            {tab === "overview" && <Overview games={config.games} />}
            {tab === "dashboard" && (
              <Embed
                url={config.dashboard_embed_url}
                title="AI/BI Dashboard"
                note="Tendências, sentimento e leitura de comentários — com Genie integrado, servido por Databricks AI/BI"
              />
            )}
          </div>
        )}
      </main>

      {/* Footer — neutral, clean design */}
      <footer className="mt-auto bg-ink text-mutedDark">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-4 px-6 py-8">
          <span className="brand-title text-lg text-paper">Player Feedback</span>
          <span className="text-xs uppercase tracking-[0.18em]">
            Powered by Databricks · AI Functions · AI/BI · Genie
          </span>
        </div>
      </footer>
    </div>
  );
}
