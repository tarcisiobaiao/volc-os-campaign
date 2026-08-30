/**
 * O acompanhamento ao vivo de um job, e a peça por formato.
 *
 * ## A regra mais importante deste arquivo
 *
 * Quando `percentual` é `null`, NÃO EXISTE BARRA. Existe a etapa escrita em
 * linguagem humana. Uma barra falsa é pior que nenhuma: ela vira um número que
 * alguém usa para decidir se espera ou se cancela, e ninguém mediu esse número.
 *
 * ## O anúncio para leitor de tela
 *
 * A mudança de estado é dita numa região `aria-live="polite"` dedicada. Marcar
 * a lista inteira como `live` faria o leitor reler todas as peças a cada
 * evento; a região separada diz só o que mudou.
 */
import React from 'react';
import { CircleAlert, Download } from 'lucide-react';

import { cn } from '@/lib/utils';
import { SeloDaPeca } from '@/components/criativos/comum/Selo';
import { SemArquivo } from '@/components/criativos/comum/Estados';
import { Preview } from '@/components/criativos/comum/Preview';
import {
  custoLegivel,
  dimensoes,
  enquadramentoLegivel,
  hashCurto,
  instante,
  mimeLegivel,
  bytesLegiveis,
} from '@/components/criativos/comum/formato';
import { lerProgresso } from '@/components/criativos/job/progresso';
import { DESCRICAO_DA_CONEXAO, type EstadoDaConexao } from '@/hooks/useCriativosEventos';
import { ROTULO_DO_JOB, type CreativeJob, type EventoDoJob, type Rendition } from '@/types/criativos';

export const PainelDeFase: React.FC<{
  job: CreativeJob;
  eventos: EventoDoJob[];
  conexao: EstadoDaConexao;
  falhaDoFluxo: string | null;
}> = ({ job, eventos, conexao, falhaDoFluxo }) => {
  const progresso = lerProgresso(eventos);
  const rotulo = ROTULO_DO_JOB[job.estado];

  return (
    <div className="space-y-3">
      {/* A região que o leitor de tela acompanha. Curta de propósito. */}
      <div aria-live="polite" role="status" className="sr-only">
        {`Trabalho ${rotulo.palavra}. ${rotulo.descricao} ${progresso.frase}`}
      </div>

      <div className="rounded-md border border-border bg-muted/40 px-4 py-3">
        <p className="kicker">Etapa observada</p>
        <p className="mt-1 text-pretty text-sm leading-relaxed text-foreground">
          {progresso.frase}
        </p>
        {progresso.detalhe && (
          <p className="mt-1 text-pretty text-[13px] leading-relaxed text-muted-foreground">
            {progresso.detalhe}
          </p>
        )}
        {progresso.slot && (
          <p className="mt-1 text-[12px] text-muted-foreground">
            Peça afetada: {progresso.slot}.
          </p>
        )}

        {progresso.percentual === null ? (
          <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
            Este motor não informa progresso em percentual. O que você vê acima é a etapa real
            relatada pelo servidor, não uma estimativa.
          </p>
        ) : (
          <div className="mt-3">
            <div
              role="progressbar"
              aria-valuenow={progresso.percentual}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Progresso informado pelo motor"
              className="h-2 w-full overflow-hidden rounded-full bg-border"
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out motion-reduce:transition-none"
                style={{ width: `${progresso.percentual}%` }}
              />
            </div>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {progresso.percentual}% informado pelo motor.
            </p>
          </div>
        )}
      </div>

      <p className="text-[12px] leading-relaxed text-muted-foreground">
        {DESCRICAO_DA_CONEXAO[conexao]}
        {falhaDoFluxo ? ` ${falhaDoFluxo}` : ''}
      </p>
    </div>
  );
};

export const PecaDoJob: React.FC<{ peca: Rendition; aoRenovar?: () => void }> = ({
  peca,
  aoRenovar,
}) => {
  const enquadramento = enquadramentoLegivel(peca.enquadramento);
  return (
    <li className="rounded-md border border-border bg-muted/30 p-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="font-display text-sm font-semibold text-foreground">{peca.rotulo}</p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Pedido {peca.larguraPedida} x {peca.alturaPedida} px, slot {peca.slot}.
          </p>
        </div>
        <SeloDaPeca estado={peca.estado} />
      </div>

      <div className="mt-3">
        {peca.previewUrl ? (
          <a
            href={peca.previewUrl}
            target="_blank"
            rel="noreferrer"
            className="block overflow-hidden rounded-md border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <Preview
              url={peca.previewUrl}
              alt={`Peça ${peca.rotulo}, ${peca.larguraPedida} por ${peca.alturaPedida} pixels, do trabalho em produção`}
              aoRenovar={aoRenovar}
              classNameImagem="mx-auto max-h-64 w-auto max-w-full"
            />
          </a>
        ) : peca.estado === 'pronta' ? (
          <SemArquivo motivo="A peça está pronta e o arquivo não veio nesta leitura. Recarregue para pedir uma nova URL." />
        ) : peca.estado === 'falhou' ? null : (
          <SemArquivo motivo="Ainda não há arquivo para esta peça." />
        )}
      </div>

      {peca.erro && (
        <div className="mt-3 rounded-md border border-destructive/50 bg-destructive/[0.06] px-3 py-2">
          <div className="flex items-start gap-2">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
            <div className="min-w-0">
              <p className="text-[13px] leading-relaxed text-foreground">{peca.erro.mensagem}</p>
              <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
                {peca.erro.permanente
                  ? 'Falha permanente: o mesmo insumo deve falhar igual. Ajuste o briefing em vez de repetir.'
                  : 'Falha temporária: repetir com o mesmo insumo pode dar certo.'}{' '}
                Registrada em {instante(peca.erro.em)}.
              </p>
            </div>
          </div>
        </div>
      )}

      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-[12px] sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Medido no arquivo</dt>
          <dd className="text-foreground">{dimensoes(peca.largura, peca.altura)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Entregue pelo motor</dt>
          <dd className="text-foreground">{dimensoes(peca.nativoLargura, peca.nativoAltura)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Enquadramento</dt>
          <dd className="text-foreground" title={enquadramento.descricao}>
            {enquadramento.palavra}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Arquivo</dt>
          <dd className="text-foreground">
            {mimeLegivel(peca.mime)}, {bytesLegiveis(peca.bytesTotais)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Custo desta peça</dt>
          <dd className="text-foreground">{custoLegivel(peca.custoUsd)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Hash do conteúdo</dt>
          <dd className="truncate font-mono text-foreground" title={peca.contentHash ?? undefined}>
            {hashCurto(peca.contentHash)}
          </dd>
        </div>
      </dl>

      {peca.previewUrl && (
        <a
          href={peca.previewUrl}
          download
          className={cn(
            'mt-3 inline-flex min-h-9 items-center gap-2 rounded-md border border-input px-3 text-[13px] text-foreground',
            'transition-colors duration-150 ease-out hover:bg-muted/60',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          )}
        >
          <Download className="h-4 w-4" aria-hidden />
          Baixar esta peça
        </a>
      )}
    </li>
  );
};
