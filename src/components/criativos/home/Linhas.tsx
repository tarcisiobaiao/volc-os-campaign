/**
 * As linhas da Home: um trabalho e um ativo.
 *
 * Linha densa com UMA identidade e UMA linha de metadados, no desenho que o
 * DESIGN.md pede para o inventário. Nada de grade de cartões iguais: quatro
 * cartões idênticos fazem quatro fatos diferentes parecerem o mesmo fato.
 */
import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';
import { SeloDaAprovacao, SeloDoJob, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import {
  custoDoJobLegivel,
  dimensoes,
  instante,
  kindLegivel,
} from '@/components/criativos/comum/formato';
import { frasePecas, resumirPecas } from '@/components/criativos/job/pecas';
import type { AssetMaster, CreativeJob } from '@/types/criativos';

const LINHA = cn(
  'group flex items-start gap-3 border-b border-border/70 px-3 py-3 last:border-b-0',
  'transition-colors duration-150 ease-out hover:bg-muted/50',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
);

export const LinhaDeJob: React.FC<{ job: CreativeJob }> = ({ job }) => {
  const resumo = resumirPecas(job.renditions);
  const mudou = job.terminadoEm ?? job.iniciadoEm ?? job.criadoEm;
  return (
    <Link to={`/criativos/jobs/${job.id}`} className={LINHA}>
      <span className="mt-0.5 shrink-0">
        <SeloDoJob estado={job.estado} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">
          {job.projetoTitulo}
        </span>
        <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">
          {kindLegivel(job.tipo)}, {resumo.total} {resumo.total === 1 ? 'peça' : 'peças'}.{' '}
          {frasePecas(resumo)} Motor {job.motor} {job.motorVersao}.{' '}
          {/* Estimativa e apuração não podem sair da mesma frase sem rótulo:
              o `??` anterior fazia a linha da Home parecer gasto realizado. */}
          {custoDoJobLegivel(job.custoRealUsd, job.custoEstimadoUsd)}. Última mudança{' '}
          {instante(mudou)}.
        </span>
        {job.procedenciaExecucao === 'observado' && (
          <span className="mt-1.5 block">
            <SeloDeProcedencia procedencia={job.procedenciaExecucao} />
          </span>
        )}
        {job.falha && (
          <span className="mt-1.5 block text-[12px] leading-relaxed text-foreground">
            {job.falha.mensagem}
          </span>
        )}
      </span>
      <ChevronRight
        className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-colors duration-150 ease-out group-hover:text-foreground"
        aria-hidden
      />
    </Link>
  );
};

export const LinhaDeAtivo: React.FC<{ asset: AssetMaster }> = ({ asset }) => (
  <Link to={`/criativos/assets/${asset.id}`} className={LINHA}>
    <span className="mt-0.5 shrink-0">
      <SeloDaAprovacao decisao={asset.aprovacaoVigente?.decisao ?? null} />
    </span>
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-medium text-foreground">
        {asset.projetoTitulo}
      </span>
      <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">
        {kindLegivel(asset.kind)}, slot {asset.slot}, {dimensoes(asset.largura, asset.altura)}.
        Versão {asset.versao}. Criado em {instante(asset.criadoEm)}.
        {asset.aprovacaoVigente?.atorNome
          ? ` Decidido por ${asset.aprovacaoVigente.atorNome}.`
          : ''}
      </span>
    </span>
    <ChevronRight
      className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-colors duration-150 ease-out group-hover:text-foreground"
      aria-hidden
    />
  </Link>
);
