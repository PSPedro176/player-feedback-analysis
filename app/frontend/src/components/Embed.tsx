import { ArrowUpRight } from "lucide-react";

export default function Embed({
  url,
  title,
  note,
}: {
  url: string;
  title: string;
  note: string;
}) {
  return (
    <div className="flex h-[calc(100vh-180px)] min-h-[640px] flex-col border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <h2 className="display text-lg font-bold">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{note}</p>
        </div>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-brand px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-brand transition-colors hover:bg-brand hover:text-white"
          >
            Abrir <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
      {url ? (
        <iframe src={url} title={title} className="h-full w-full flex-1 bg-white" />
      ) : (
        <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted">
          Dashboard ainda não disponível. Confirme que o dashboard foi criado pelo bundle e
          <span className="mx-1 font-semibold text-ink">publicado</span> no workspace (o embed só
          renderiza dashboards publicados).
        </div>
      )}
    </div>
  );
}
