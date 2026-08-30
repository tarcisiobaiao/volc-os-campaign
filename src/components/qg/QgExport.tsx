import * as React from "react";
import { pautadorApi } from "@/lib/pautadorApi";
import type { QgUrlState } from "@/features/work-road/url-state";

export function QgExport({ filters }: { filters: QgUrlState }) {
  const [scope, setScope] = React.useState<"full" | "current" | "next-wave" | "open">("full");
  const [format, setFormat] = React.useState<"pdf" | "html" | "json" | "docx">("pdf");
  const [status, setStatus] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  const onExport = async () => {
    setPending(true);
    setStatus(null);
    try {
      const blob = await pautadorApi.workRoadExport(format, scope, {
        iniciativa: filters.iniciativa,
        onda: filters.onda,
        status: filters.status,
        busca: filters.busca,
      });
      const name = `workbook-volc-os.${format}`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
      setStatus(`Arquivo gerado: ${name} (${blob.size} bytes).`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Falha ao exportar.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <label className="text-xs font-medium text-muted-foreground">
        Recorte
        <select
          className="mt-1 block h-10 min-h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={scope}
          onChange={(event) => setScope(event.target.value as typeof scope)}
        >
          <option value="full">Roadmap completo</option>
          <option value="current">Recorte atual</option>
          <option value="next-wave">Próxima onda</option>
          <option value="open">Somente pendências</option>
        </select>
      </label>
      <label className="text-xs font-medium text-muted-foreground">
        Formato
        <select
          className="mt-1 block h-10 min-h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={format}
          onChange={(event) => setFormat(event.target.value as typeof format)}
        >
          <option value="pdf">PDF imprimível</option>
          <option value="html">HTML imprimível</option>
          <option value="docx">DOCX existente</option>
          <option value="json">JSON de evidência</option>
        </select>
      </label>
      <button
        type="button"
        onClick={() => { void onExport(); }}
        disabled={pending}
        className="inline-flex min-h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-transform duration-150 ease-out active:scale-[0.96] disabled:opacity-60 motion-reduce:transition-none"
      >
        {pending ? "Gerando" : "Exportar workbook"}
      </button>
      {status ? <p className="text-xs text-foreground" role="status">{status}</p> : null}
    </div>
  );
}
