import { useEffect, useState } from "react";
import { Plus, Trash2, ExternalLink } from "lucide-react";
import { api, type ConfiguredGame } from "../api";
import { GameIcon, Spinner } from "./ui";

type Notice = { kind: "ok" | "err"; text: string } | null;

export default function Manage() {
  const [games, setGames] = useState<ConfiguredGame[] | null>(null);
  const [pkg, setPkg] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  function load() {
    api.gamesConfig().then(setGames).catch((e) => setNotice({ kind: "err", text: e.message }));
  }
  useEffect(load, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const value = pkg.trim();
    if (!value) return;
    setAdding(true);
    setNotice(null);
    try {
      const res = await api.addGame(value);
      setPkg("");
      const triggered = res.ingestion_run_id != null;
      setNotice({
        kind: "ok",
        text: triggered
          ? `"${res.game.name}" adicionado. Ingestão disparada — os dados aparecem em alguns minutos.`
          : `"${res.game.name}" adicionado. Entrará na próxima execução agendada da ingestão.`,
      });
      load();
    } catch (e) {
      setNotice({ kind: "err", text: (e as Error).message });
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(name: string) {
    setRemoving(name);
    setNotice(null);
    try {
      await api.removeGame(name);
      setNotice({ kind: "ok", text: `"${name}" removido do monitoramento.` });
      load();
    } catch (e) {
      setNotice({ kind: "err", text: (e as Error).message });
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <h2 className="brand-title text-2xl">Gerenciar jogos</h2>
        <p className="mt-2 text-sm text-muted">
          Adicione jogos da Google Play Store para monitorar. Use o{" "}
          <span className="font-semibold text-ink">package name</span> (ex:{" "}
          <code className="bg-line/50 px-1">com.kiloo.subwaysurf</code>) — ele aparece na
          URL da página do app na Play Store, em <code className="bg-line/50 px-1">?id=</code>.
        </p>
      </div>

      {/* Form de adicionar */}
      <form onSubmit={handleAdd} className="flex gap-3">
        <input
          value={pkg}
          onChange={(e) => setPkg(e.target.value)}
          placeholder="com.example.game"
          className="flex-1 border border-line bg-white px-4 py-2.5 text-sm outline-none focus:border-ink"
          disabled={adding}
        />
        <button
          type="submit"
          disabled={adding || !pkg.trim()}
          className="inline-flex items-center gap-2 bg-ink px-5 py-2.5 text-sm font-semibold text-paper transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {adding ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-paper/40 border-t-paper" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Adicionar
        </button>
      </form>

      {notice && (
        <div
          className={`mt-4 border p-3 text-sm ${
            notice.kind === "ok"
              ? "border-good/30 bg-good/5 text-good"
              : "border-bad/30 bg-bad/5 text-bad"
          }`}
        >
          {notice.text}
        </div>
      )}

      {/* Lista de jogos configurados via UI */}
      <div className="mt-10">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
          Adicionados pela UI
        </h3>
        {games === null ? (
          <div className="py-10">
            <Spinner label="Carregando…" />
          </div>
        ) : games.length === 0 ? (
          <p className="border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
            Nenhum jogo adicionado por aqui ainda. Os jogos definidos no{" "}
            <code className="bg-line/50 px-1">databricks.yml</code> continuam monitorados.
          </p>
        ) : (
          <ul className="divide-y divide-line border border-line">
            {games.map((g) => (
              <li key={g.name} className="flex items-center gap-4 px-4 py-3">
                <GameIcon icon={g.icon ?? undefined} name={g.name} size={40} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{g.name}</div>
                  <a
                    href={`https://play.google.com/store/apps/details?id=${g.package}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
                  >
                    {g.package}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <button
                  onClick={() => handleRemove(g.name)}
                  disabled={removing === g.name}
                  className="inline-flex items-center gap-1.5 border border-line px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:border-bad hover:text-bad disabled:opacity-40"
                >
                  {removing === g.name ? (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-bad" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
