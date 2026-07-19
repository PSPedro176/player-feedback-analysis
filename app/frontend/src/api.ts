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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`Erro ${res.status} em ${path}`);
  }
  return res.json();
}

export const api = {
  config: () => get<AppConfig>("/api/config"),
  overview: () => get<Overview>("/api/overview"),
  reports: () => get<WeeklyReport[]>("/api/reports"),
  reviews: (game: string) => get<Review[]>(`/api/reviews/${encodeURIComponent(game)}`),
};
