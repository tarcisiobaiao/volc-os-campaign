/**
 * A grade e a lista de ativos.
 *
 * A escolha entre as duas é preferência de quem olha, e mora em
 * `biblioteca/densidade.ts`. Nada de negócio passa por ali.
 */
import React from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';
import { Preview } from '@/components/criativos/comum/Preview';
import { SeloDaAprovacao, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { dimensoes, instante, kindLegivel } from '@/components/criativos/comum/formato';
import type { Densidade } from '@/components/criativos/biblioteca/densidade';
import type { AssetMaster } from '@/types/criativos';

function descricaoDoAtivo(asset: AssetMaster): string {
  return `${kindLegivel(asset.kind)} do trabalho ${asset.projetoTitulo}, slot ${asset.slot}, ${dimensoes(
    asset.largura,
    asset.altura,
  )}`;
}

const CARTAO = cn(
  'group flex flex-col overflow-hidden rounded-md border border-border bg-card',
  'transition-colors duration-150 ease-out hover:border-primary/40',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
);

export const Grade: React.FC<{
  assets: AssetMaster[];
  densidade: Densidade;
  aoRenovar: () => void;
}> = ({ assets, densidade, aoRenovar }) => {
  if (densidade === 'lista') {
    return (
      <ul className="rounded-md border border-border bg-card">
        {assets.map((asset) => (
          <li key={asset.id} className="border-b border-border/70 last:border-b-0">
            <Link
              to={`/criativos/assets/${asset.id}`}
              className="flex items-center gap-3 px-3 py-2.5 transition-colors duration-150 ease-out hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
            >
              <Preview
                url={asset.previewUrl}
                alt={descricaoDoAtivo(asset)}
                aoRenovar={aoRenovar}
                className="h-12 w-12 shrink-0 rounded-sm border border-border"
                classNameImagem="h-12 w-12"
                denso
                motivoSemArquivo="Arquivo indisponível nesta leitura. O ativo existe."
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-foreground">
                  {asset.projetoTitulo}
                </span>
                <span className="block truncate text-[12px] text-muted-foreground">
                  {kindLegivel(asset.kind)}, slot {asset.slot},{' '}
                  {dimensoes(asset.largura, asset.altura)}. Versão {asset.versao}. Criado em{' '}
                  {instante(asset.criadoEm)}.
                </span>
              </span>
              <span className="hidden shrink-0 sm:block">
                <SeloDaAprovacao decisao={asset.aprovacaoVigente?.decisao ?? null} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {assets.map((asset) => (
        <li key={asset.id}>
          <Link to={`/criativos/assets/${asset.id}`} className={CARTAO}>
            <Preview
              url={asset.previewUrl}
              alt={descricaoDoAtivo(asset)}
              aoRenovar={aoRenovar}
              className="aspect-square w-full border-b border-border"
              classNameImagem="h-full w-full"
              motivoSemArquivo="Arquivo indisponível nesta leitura. O ativo existe."
            />
            <span className="flex min-w-0 flex-1 flex-col gap-1.5 p-2.5">
              <span className="truncate text-[13px] font-medium text-foreground">
                {asset.projetoTitulo}
              </span>
              <span className="truncate text-[12px] text-muted-foreground">
                {kindLegivel(asset.kind)}, {dimensoes(asset.largura, asset.altura)}
              </span>
              <span className="flex flex-wrap gap-1">
                <SeloDaAprovacao decisao={asset.aprovacaoVigente?.decisao ?? null} />
                {asset.procedenciaExecucao === 'observado' && (
                  <SeloDeProcedencia procedencia={asset.procedenciaExecucao} />
                )}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
};
