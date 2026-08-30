/**
 * A trilha de etapas do briefing.
 *
 * ## Por que trilha e não wizard modal
 *
 * Um wizard modal prende o operador num túnel: ele não vê o que já respondeu,
 * não volta sem perder contexto e não sai sem desistir. A trilha mostra as
 * cinco etapas o tempo todo, deixa saltar para qualquer uma e diz quais já
 * estão completas. A revelação progressiva está no CONTEÚDO (só a etapa atual
 * pede campos), não no aprisionamento da navegação.
 *
 * ⚠️ Etapa incompleta não é bloqueada aqui. Quem bloqueia é o botão de gerar,
 * que valida o rascunho inteiro. Travar a navegação faria alguém que quer
 * conferir a etapa 4 ter que preencher a 2 antes de olhar.
 */
import React from 'react';
import { Check, Circle, CircleDot } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  ETAPAS,
  RESUMO_DA_ETAPA,
  TITULO_DA_ETAPA,
  etapaCompleta,
  type EtapaDoBriefing,
  type RascunhoDeImagem,
} from '@/components/criativos/briefing/contrato';

export const Trilha: React.FC<{
  atual: EtapaDoBriefing;
  rascunho: RascunhoDeImagem;
  aoIr: (etapa: EtapaDoBriefing) => void;
}> = ({ atual, rascunho, aoIr }) => (
  <nav aria-label="Etapas do briefing">
    <ol className="space-y-1">
      {ETAPAS.map((etapa, i) => {
        const ativa = etapa === atual;
        const completa = etapa !== 'revisao' && etapaCompleta(etapa, rascunho);
        const Glifo = ativa ? CircleDot : completa ? Check : Circle;
        return (
          <li key={etapa}>
            <button
              type="button"
              onClick={() => aoIr(etapa)}
              aria-current={ativa ? 'step' : undefined}
              className={cn(
                'flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left',
                'transition-colors duration-150 ease-out',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                ativa ? 'bg-primary/[0.08] text-foreground' : 'hover:bg-muted/60',
              )}
            >
              <Glifo
                className={cn(
                  'mt-0.5 h-4 w-4 shrink-0',
                  ativa ? 'text-primary' : completa ? 'text-success' : 'text-muted-foreground',
                )}
                aria-hidden
              />
              <span className="min-w-0">
                <span
                  className={cn(
                    'block text-[13px]',
                    ativa ? 'font-semibold text-foreground' : 'font-medium text-foreground/90',
                  )}
                >
                  {i + 1}. {TITULO_DA_ETAPA[etapa]}
                </span>
                <span className="mt-0.5 block text-[12px] leading-snug text-muted-foreground">
                  {RESUMO_DA_ETAPA[etapa]}
                </span>
                <span className="sr-only">
                  {ativa
                    ? ' Etapa atual.'
                    : completa
                      ? ' Etapa completa.'
                      : ' Etapa ainda incompleta.'}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  </nav>
);
