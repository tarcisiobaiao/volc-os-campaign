import { useEffect, useId, useRef } from 'react';
import { ImageIcon, Loader2 } from 'lucide-react';

import type { PlanoDeGeracao } from '../tipos';

/** A espera do pedido não revela etapas nem progresso interno do motor. */
export function ProgressoDeGeracao({ plano }: { plano: PlanoDeGeracao | null }) {
  const tituloId = useId();
  const descricaoId = useId();
  const painel = useRef<HTMLElement>(null);

  useEffect(() => {
    painel.current?.focus({ preventScroll: true });
  }, []);

  return (
    <section
      ref={painel}
      tabIndex={-1}
      aria-labelledby={tituloId}
      aria-describedby={descricaoId}
      className="rounded-lg border border-border bg-card p-6 shadow-card outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background md:p-8"
    >
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
        <div aria-hidden className="flex h-28 w-24 shrink-0 flex-col justify-between rounded-md border border-border bg-muted/20 p-3">
          <ImageIcon className="h-7 w-7 text-muted-foreground motion-safe:animate-pulse motion-reduce:animate-none" />
          <div className="space-y-2 motion-safe:animate-pulse motion-reduce:animate-none">
            <div className="h-2 w-full rounded-sm bg-muted" />
            <div className="h-2 w-2/3 rounded-sm bg-muted" />
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div role="status" aria-live="polite" aria-atomic="true">
            <p className="flex items-center gap-2 text-sm font-medium text-primary">
              <Loader2 className="h-4 w-4 shrink-0 motion-safe:animate-spin motion-reduce:animate-none" aria-hidden />
              Aguardando resposta
            </p>
            <h2 id={tituloId} className="mt-2 font-display text-xl font-semibold text-foreground">
              Geração solicitada
            </h2>
            <p id={descricaoId} className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
              Sua solicitação está em andamento. As imagens aparecem quando o resultado estiver disponível.
            </p>
          </div>

          {plano && (
            <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-3 border-t border-border pt-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Imagens solicitadas</dt>
                <dd className="mt-1 font-medium tabular-nums text-foreground">{plano.total_de_renders}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Modelo</dt>
                <dd className="mt-1 break-words font-medium text-foreground">{plano.modelo_de_imagem ?? 'Não informado'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Qualidade</dt>
                <dd className="mt-1 font-medium text-foreground">{plano.qualidade_de_imagem ?? 'Não informada'}</dd>
              </div>
            </dl>
          )}

          <p className="mt-5 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
            Mantenha esta página aberta para acompanhar. Se a conexão cair, reabra esta operação pelo Histórico e confira a aba Criativos antes de solicitar outra geração.
          </p>
        </div>
      </div>
    </section>
  );
}
