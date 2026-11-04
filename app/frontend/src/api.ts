export interface Game {
  name: string;
  package: string;
  icon: string;
  accent: string;
}

export interface AppConfig {
  host: string;
  dashboard_id: string;
  dashboard_embed_url: string;
  games: Game[];
}

export interface Overview {
  totals: {
    total_reviews: number;
    avg_score: number;
  };
  per_game: {
    game: string;
    reviews: number;
    avg_score: number;
  }[];
  sentiment_by_game: { game: string; sentiment: string; n: number }[];
}

export interface WeeklyReport {
  game: string;
  report_week: string;
  grade: "green" | "yellow" | "red";
  report: string;
  n_reviews: number;
  avg_score: number;
  window_start: string;
  window_end: string;
  _generated_at: string;
}

export interface Review {
  review_id: string;
  user_name: string;
  content: string;
  score: number;
  sentiment: string;
  bug_report: boolean;
  at: string;
  language: string;
}

export interface CollectRun {
  run_id: number;
  run_url: string;
}

export interface GameInput {
  name: string;
  package: string;
}

export interface GenieSpace {
  space_id: string;
  title: string;
  description: string;
  url: string;
  sample_questions: string[];
}

export interface GenieAnswer {
  conversation_id: string;
  message_id: string;
  status: string;
  done: boolean;
  text: string;
  sql: string | null;
  query_description: string | null;
  columns: string[];
  rows: (string | null)[][];
  row_count: number | null;
  truncated: boolean;
  suggested_questions: string[];
  error: string | null;
}

async function failure(res: Response, path: string): Promise<Error> {
  // Rotas do Genie devolvem {detail} com a causa — mostra na UI quando houver.
  const body = await res.json().catch(() => null);
  const detail = body && typeof body.detail === "string" ? `: ${body.detail}` : "";
  return new Error(`Erro ${res.status} em ${path}${detail}`);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw await failure(res, path);
  }
  return res.json();
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw await failure(res, path);
  }
  return res.json();
}

export const api = {
  config: () => get<AppConfig>("/api/config"),
  overview: () => get<Overview>("/api/overview"),
  reports: () => get<WeeklyReport[]>("/api/reports"),
  reviews: (game: string) => get<Review[]>(`/api/reviews/${encodeURIComponent(game)}`),
  games: () => get<Game[]>("/api/games"),
  addGames: (items: GameInput[]) => send<{ added: number }>("/api/games", "POST", items),
  removeGame: (pkg: string) =>
    send<{ removed: string }>(`/api/games/${encodeURIComponent(pkg)}`, "DELETE"),
  runCollect: () => send<CollectRun>("/api/jobs/collect/run", "POST", {}),
  genieSpace: () => get<GenieSpace>("/api/genie/space"),
  genieAsk: (question: string, conversation_id?: string | null) =>
    send<GenieAnswer>("/api/genie/ask", "POST", { question, conversation_id }),
  geniePoll: (conversation_id: string, message_id: string) =>
    get<GenieAnswer>(
      `/api/genie/conversations/${encodeURIComponent(conversation_id)}/messages/${encodeURIComponent(message_id)}`,
    ),
};
