import React from "react";
import { useQuery } from "@tanstack/react-query";

import { Frescor } from "@/components/sistema/Frescor";
import { secureApi } from "@/lib/secureApi";

/**
 * De onde vêm os números da home, e quando cada fonte foi lida pela última vez.
 *
 * ⚠️ Este bloco substitui "Status das Integrações", que era uma CONSTANTE:
 * Google Ads e Ad Manager "Online · 2 min atrás" e Analytics "Pendente · 15 min
 * atrás", fixos no código, em qualquer dia, com o banco no ar ou não. O
 * PRODUCT.md proíbe pelo nome: "um ponto verde fixo não afirma integração".
 *
 * Agora cada linha mostra o carimbo que o servidor guarda em `system_settings`
 * (`google_ads_last_update`, `gam_last_update`), lido pela rota autenticada
 * `/api/settings`. Sem carimbo, a linha diz que não há leitura registrada; se a
 * rota falhar, diz que não foi possível consultar. Nenhuma das duas vira
 * "online". Analytics saiu: nada no produto o lê hoje.
 */
const FONTES = [
  { chave: "google_ads_last_update", nome: "Google Ads", papel: "Investimento e cliques" },
  { chave: "gam_last_update", nome: "Ad Manager (GAM)", papel: "Receita de mídia" },
] as const;

export function FontesDeDados() {
  const consulta = useQuery({
    queryKey: ["home", "carimbos-das-fontes"],
    queryFn: () => secureApi.getSettings(FONTES.map((f) => f.chave)),
    staleTime: 60_000,
    retry: 1,
  });

  return (
    <ul className="divide-y divide-border/70" aria-busy={consulta.isLoading || undefined}>
      {FONTES.map((fonte) => {
        const carimbo = consulta.data?.find((c) => c.key === fonte.chave)?.value ?? null;
        return (
          <li key={fonte.chave} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{fonte.nome}</p>
              <p className="text-xs text-muted-foreground">{fonte.papel}</p>
            </div>
            {consulta.isLoading ? (
              <span className="text-xs text-muted-foreground">Consultando…</span>
            ) : consulta.isError ? (
              <span className="text-xs text-warning">Não foi possível consultar</span>
            ) : (
              <Frescor lidoEm={carimbo} fonte={fonte.nome} />
            )}
          </li>
        );
      })}
    </ul>
  );
}
