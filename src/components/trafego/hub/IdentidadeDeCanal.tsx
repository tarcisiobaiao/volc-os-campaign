/**
 * Tags de identidade: plataforma e canal como PALAVRA, não como cor.
 *
 * Um operador com deuteranopia, um monitor mal calibrado e um print em preto
 * e branco precisam ler o mesmo fato. A cor, se existir, é o terceiro sinal.
 *
 * ⚠️ Sem `aria-label` e sem `<ul>`: a linha da campanha já calcula o nome a
 * partir do conteúdo, e uma lista extra dentro dela inflava o número de
 * `listitem` no telefone.
 */
import React from 'react';

import { cn } from '@/lib/utils';

import type { RedeDoHub } from './contrato';
import { canalDaUrl } from './adaptacao';

const ROTULO_DA_REDE: Record<RedeDoHub, string> = {
  google: 'Google Ads',
  meta: 'Meta Ads',
};

const ROTULO_DO_CANAL: Record<string, string> = {
  SEARCH: 'Search',
  DISPLAY: 'Display',
  DEMAND_GEN: 'Demand Gen',
  PMAX: 'Performance Max',
  PERFORMANCE_MAX: 'Performance Max',
  VIDEO: 'Vídeo',
  SHOPPING: 'Shopping',
};

export function rotuloDaRede(rede: RedeDoHub): string {
  return ROTULO_DA_REDE[rede];
}

export function rotuloDoCanal(canal: string | null | undefined): string | null {
  if (!canal) return null;
  const conhecido = canalDaUrl(canal) ?? canal;
  return ROTULO_DO_CANAL[conhecido] ?? `canal ${canal}`;
}

const chip = cn(
  'inline-flex min-h-6 items-center rounded-sm border border-border bg-transparent',
  'px-1.5 py-0.5 text-[11px] font-medium leading-none text-foreground',
);

export interface IdentidadeDeCanalProps {
  rede: RedeDoHub;
  canal?: string | null;
  className?: string;
}

export const IdentidadeDeCanal: React.FC<IdentidadeDeCanalProps> = ({
  rede,
  canal,
  className,
}) => {
  const palavraCanal = rotuloDoCanal(canal);

  return (
    <span className={cn('inline-flex flex-wrap items-center gap-1', className)}>
      <span className={chip}>{rotuloDaRede(rede)}</span>
      {palavraCanal && <span className={chip}>{palavraCanal}</span>}
    </span>
  );
};

export default IdentidadeDeCanal;
