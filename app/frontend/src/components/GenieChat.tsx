import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, ChevronDown, ChevronRight, RotateCcw, Send, Sparkles } from "lucide-react";
import { api, type GenieAnswer, type GenieSpace } from "../api";
import { Spinner } from "./ui";

type Turn = {
  question: string;
  answer: GenieAnswer | null;
  error: string | null;
};

// Status intermediários da Genie Conversation API → texto amigável no loading.
const STATUS_LABEL: Record<string, string> = {
  SUBMITTED: "Enviando pergunta…",
  FETCHING_METADATA: "Lendo metadados das tabelas…",
  FILTERING_CONTEXT: "Selecionando contexto relevante…",
  ASKING_AI: "Gerando a consulta SQL…",
  PENDING_WAREHOUSE: "Aguardando o SQL Warehouse…",
  EXECUTING_QUERY: "Executando a consulta…",
};

// Respostas do Genie levam ~10-60s; o backend espera ~25s por request e o resto é polling.
const MAX_WAIT_MS = 180_000;

export default function GenieChat() {
  const [space, setSpace] = useState<GenieSpace | null>(null);
  const [spaceError, setSpaceError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("SUBMITTED");
  const [elapsed, setElapsed] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.genieSpace().then(setSpace).catch((e) => setSpaceError(e.message));
  }, []);

  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, [busy]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  const updateLast = (patch: Partial<Turn>) =>
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, ...patch } : t)));

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setElapsed(0);
    setStatus("SUBMITTED");
    setTurns((ts) => [...ts, { question: q, answer: null, error: null }]);
    try {
      const deadline = Date.now() + MAX_WAIT_MS;
      let a = await api.genieAsk(q, conversationId);
      setConversationId(a.conversation_id);
      while (!a.done) {
        if (Date.now() > deadline) {
          throw new Error("O Genie demorou demais para responder. Tente novamente.");
        }
        setStatus(a.status);
        a = await api.geniePoll(a.conversation_id, a.message_id);
      }
      updateLast({ answer: a, error: a.error && !a.text && !a.sql ? a.error : null });
    } catch (e) {
      updateLast({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setTurns([]);
    setConversationId(null);
  };

  if (spaceError) {
    return (
      <div className="border border-line bg-white p-8">
        <h2 className="display text-lg font-bold">Pergunte ao Genie</h2>
        <p className="mt-2 max-w-[72ch] text-sm text-muted">
          O Genie space ainda não está disponível para o App. Ele é criado pelo job{" "}
          <span className="font-semibold text-ink">pf_genie_setup</span> depois que o pipeline gera as
          tabelas — rode-o e recarregue a página.
        </p>
        <p className="mt-3 text-xs text-bad">{spaceError}</p>
      </div>
    );
  }

  if (!space) {
    return (
      <div className="flex justify-center py-32">
        <Spinner label="Conectando ao Genie space…" />
      </div>
    );
  }

  const suggestions =
    turns.length > 0 ? turns[turns.length - 1].answer?.suggested_questions ?? [] : [];

  return (
    <div className="flex h-[calc(100vh-180px)] min-h-[640px] flex-col border border-line bg-white">
      <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
        <div>
          <h2 className="display flex items-center gap-2 text-lg font-bold">
            <Sparkles className="h-4 w-4 text-brand" /> Pergunte ao Genie
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            Perguntas em linguagem natural sobre os reviews, respondidas pelo Genie space{" "}
            <span className="font-semibold text-ink">{space.title}</span> via Genie Conversation API.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {turns.length > 0 && (
            <button
              onClick={reset}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted transition-colors hover:text-ink disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Nova conversa
            </button>
          )}
          <a
            href={space.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-brand px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-brand transition-colors hover:bg-brand hover:text-white"
          >
            Abrir space <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>

      <div className="flex-1 space-y-8 overflow-y-auto px-5 py-6">
        {turns.length === 0 && (
          <div>
            <p className="mb-3 text-sm font-bold uppercase tracking-[0.14em] text-muted">
              Experimente perguntar
            </p>
            <Chips questions={space.sample_questions} onPick={ask} disabled={busy} />
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-sm text-white">
                {t.question}
              </div>
            </div>
            {t.answer || t.error ? (
              <AnswerView answer={t.answer} error={t.error} />
            ) : (
              <div className="flex items-center gap-3">
                <Spinner label={STATUS_LABEL[status] ?? "Pensando…"} />
                <span className="text-xs tabular-nums text-muted">{elapsed}s</span>
              </div>
            )}
          </div>
        ))}

        {!busy && suggestions.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-muted">
              Sugestões de follow-up
            </p>
            <Chips questions={suggestions} onPick={ask} disabled={busy} />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="flex items-center gap-3 border-t border-line px-5 py-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          placeholder={
            conversationId
              ? "Faça uma pergunta de follow-up nesta conversa…"
              : "Ex.: Quais jogos tiveram mais bug reports na semana passada?"
          }
          className="h-11 flex-1 rounded-lg border border-line bg-paper px-4 text-sm outline-none transition-colors focus:border-ink disabled:opacity-60"
          aria-label="Pergunta para o Genie"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="inline-flex h-11 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white transition-colors hover:bg-brandDark disabled:opacity-50"
        >
          <Send className="h-4 w-4" /> Perguntar
        </button>
      </form>
    </div>
  );
}

function Chips({
  questions,
  onPick,
  disabled,
}: {
  questions: string[];
  onPick: (q: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {questions.map((q) => (
        <button
          key={q}
          onClick={() => onPick(q)}
          disabled={disabled}
          className="rounded-full border border-line bg-paper px-3.5 py-1.5 text-left text-sm text-ink transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}

function AnswerView({ answer, error }: { answer: GenieAnswer | null; error: string | null }) {
  const [showSql, setShowSql] = useState(false);

  if (error || !answer) {
    return (
      <div className="max-w-[80%] border border-bad/30 bg-brandSoft p-3 text-sm text-bad" role="alert">
        {error}
      </div>
    );
  }

  return (
    <div className="max-w-full space-y-3">
      {answer.text && <div className="report-body text-sm text-ink">{answer.text}</div>}
      {answer.error && <div className="text-xs text-bad">{answer.error}</div>}

      {answer.sql && (
        <div className="border border-line">
          <button
            onClick={() => setShowSql((s) => !s)}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted hover:text-ink"
          >
            {showSql ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            SQL gerado pelo Genie
          </button>
          {showSql && (
            <pre className="overflow-x-auto border-t border-line bg-paper px-3 py-2 text-xs leading-relaxed text-ink">
              {answer.sql}
            </pre>
          )}
        </div>
      )}

      {answer.columns.length > 0 && <ResultTable answer={answer} />}
    </div>
  );
}

function ResultTable({ answer }: { answer: GenieAnswer }) {
  return (
    <div>
      <div className="max-h-[360px] overflow-auto border border-line">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-paper">
            <tr>
              {answer.columns.map((c) => (
                <th key={c} className="whitespace-nowrap border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {answer.rows.map((r, i) => (
              <tr key={i} className="border-b border-line last:border-0">
                {r.map((v, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                    {v ?? <span className="text-muted">null</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-muted">
        {answer.row_count ?? answer.rows.length} linha(s)
        {answer.truncated ? ` — exibindo as primeiras ${answer.rows.length}` : ""}
      </p>
    </div>
  );
}
