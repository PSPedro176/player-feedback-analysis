import { useState } from "react";
import { Plus, Trash2, Play, ExternalLink } from "lucide-react";
import { api, type Game, type GameInput } from "../api";
import { GameIcon, Spinner } from "./ui";

type Row = { name: string; package: string };
const emptyRow = (): Row => ({ name: "", package: "" });

export default function ManageGames({
  games,
  onChange,
}: {
  games: Game[];
  onChange: () => Promise<void>;
}) {
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [saving, setSaving] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [runUrl, setRunUrl] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, emptyRow()]);
  const dropRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  const save = async () => {
    const items: GameInput[] = rows
      .map((r) => ({ name: r.name.trim(), package: r.package.trim() }))
      .filter((r) => r.name && r.package);
    if (items.length === 0) return;
    setSaving(true);
    setError(null);
    setMsg(null);
    try {
      const res = await api.addGames(items);
      await onChange();
      setRows([emptyRow()]);
      setMsg(`${res.added} jogo(s) adicionado(s). Dispare a coleta para começar a monitorar.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (pkg: string) => {
    setError(null);
    try {
      await api.removeGame(pkg);
      await onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const collect = async () => {
    setCollecting(true);
    setError(null);
    setRunUrl(null);
    try {
      const res = await api.runCollect();
      setRunUrl(res.run_url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCollecting(false);
    }
  };

  return (
    <div className="space-y-12">
      {error && <div className="border border-bad/30 bg-bad/5 p-4 text-sm text-bad">{error}</div>}

      {/* ===== Adicionar jogos (em lote) ===== */}
      <section>
        <h2 className="display mb-1 text-sm font-bold uppercase tracking-[0.18em] text-muted">
          Adicionar jogos
        </h2>
        <p className="mb-5 max-w-2xl text-sm text-muted">
          Informe o nome e o <span className="font-semibold text-ink">ID da Play Store</span> (package
          name) de cada jogo. O ID aparece na URL da página do app na Play Store:{" "}
          <code className="bg-white px-1">
            play.google.com/store/apps/details?id=<b>com.exemplo.jogo</b>
          </code>
          . Você pode adicionar vários de uma vez.
        </p>

        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-3">
              <input
                value={r.name}
                onChange={(e) => setRow(i, { name: e.target.value })}
                placeholder="Nome do jogo"
                className="min-w-48 flex-1 border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              />
              <input
                value={r.package}
                onChange={(e) => setRow(i, { package: e.target.value })}
                placeholder="com.exemplo.jogo"
                className="min-w-64 flex-1 border border-line bg-white px-3 py-2 font-mono text-sm outline-none focus:border-ink"
              />
              <button
                onClick={() => dropRow(i)}
                disabled={rows.length === 1}
                className="p-2 text-muted transition-colors hover:text-bad disabled:opacity-30"
                title="Remover linha"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4">
          <button
            onClick={addRow}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted transition-colors hover:text-ink"
          >
            <Plus className="h-4 w-4" /> Adicionar outra linha
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-2 border border-ink bg-ink px-4 py-2 text-xs font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-carbon disabled:opacity-50"
          >
            {saving ? "Salvando…" : "Salvar jogos"}
          </button>
          {msg && <span className="text-sm text-good">{msg}</span>}
        </div>
      </section>

      {/* ===== Coleta ===== */}
      <section className="border-t border-line pt-8">
        <h2 className="display mb-1 text-sm font-bold uppercase tracking-[0.18em] text-muted">
          Coleta de dados
        </h2>
        <p className="mb-4 max-w-2xl text-sm text-muted">
          Dispara uma única execução do job de coleta cobrindo todos os jogos cadastrados. Jogos novos
          fazem backfill dos últimos meses e geram automaticamente o primeiro relatório semanal.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <button
            onClick={collect}
            disabled={collecting || games.length === 0}
            className="inline-flex items-center gap-2 border border-ink px-4 py-2 text-xs font-semibold uppercase tracking-wider transition-colors hover:bg-ink hover:text-paper disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" /> Disparar coleta agora
          </button>
          {collecting && <Spinner label="Sincronizando cadastro e disparando o job…" />}
          {runUrl && (
            <a
              href={runUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink underline"
            >
              Acompanhar execução do job <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </section>

      {/* ===== Jogos monitorados ===== */}
      <section className="border-t border-line pt-8">
        <h2 className="display mb-5 text-sm font-bold uppercase tracking-[0.18em] text-muted">
          Jogos monitorados ({games.length})
        </h2>
        {games.length === 0 ? (
          <p className="text-sm text-muted">Nenhum jogo cadastrado ainda.</p>
        ) : (
          <div className="divide-y divide-line border-y border-line">
            {games.map((g) => (
              <div key={g.package} className="flex items-center gap-4 py-3">
                <GameIcon icon={g.icon} name={g.name} size={40} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{g.name}</div>
                  <div className="truncate font-mono text-xs text-muted">{g.package}</div>
                </div>
                <button
                  onClick={() => remove(g.package)}
                  className="inline-flex items-center gap-1.5 p-2 text-muted transition-colors hover:text-bad"
                  title="Remover jogo"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
