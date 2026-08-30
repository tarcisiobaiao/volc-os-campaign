/**
 * A leitura de um build de vídeo OBSERVADO.
 *
 * ## O que esta tela é obrigada a dizer, e diz primeiro
 *
 * Que o VOLC O.S. **não renderizou** este vídeo. Ele leu um build congelado por
 * uma fábrica externa e guardou a prova: identificador do build, hash do
 * artefato e instante da observação. `procedenciaExecucao: 'observado'` existe
 * no contrato porque esta é a mentira mais fácil de cometer nesta fatia, e uma
 * tela que mostra player, contrato e QA sem dizer quem produziu convida a
 * conclusão errada por omissão.
 *
 * ## Três regiões no desktop, três abas no telefone
 *
 * SPEC §9.3 e §17. As abas usam Radix, que já traz `role="tablist"`, a relação
 * `aria-controls`/`aria-labelledby` e a navegação por setas. O estado do job
 * fica FORA das abas: esconder o estado atrás de uma aba faria alguém ler o
 * contrato sem saber que o build reprovou.
 */
import React from 'react';
import { Info } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Secao } from '@/components/criativos/comum/Painel';
import { SeloDoJob, SeloDeProcedencia } from '@/components/criativos/comum/Selo';
import { hashCurto, instante } from '@/components/criativos/comum/formato';
import { Direcao } from '@/components/criativos/video/Direcao';
import { Inspecao } from '@/components/criativos/video/Inspecao';
import { PlayerDoVideo } from '@/components/criativos/video/Player';
import { useIsMobile } from '@/hooks/useIsMobile';
import type { VideoObservado } from '@/types/criativos';

const DeclaracaoDeOrigem: React.FC<{ leitura: VideoObservado }> = ({ leitura }) => {
  const origem = leitura.job.origemExterna;
  return (
    <div className="rounded-md border border-border bg-muted/50 px-4 py-3">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <p className="font-display text-sm font-semibold text-foreground">
            Este build foi observado, não produzido aqui
          </p>
          <p className="mt-1 text-pretty text-[13px] leading-relaxed text-foreground">
            {origem
              ? `A fábrica ${origem.fabrica} produziu e congelou este vídeo. O VOLC O.S. leu o arquivo, guardou o hash e montou esta leitura. Ele não renderizou nada deste build.`
              : 'O VOLC O.S. leu este build de uma fábrica externa. Ele não renderizou nada deste build.'}
          </p>
          {origem && (
            <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-[12px] sm:grid-cols-2">
              <div className="min-w-0">
                <dt className="inline text-muted-foreground">Identificador do build: </dt>
                <dd className="inline break-words font-mono text-foreground">
                  {origem.identificadorDoBuild}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="inline text-muted-foreground">Hash do artefato: </dt>
                <dd
                  className="inline break-words font-mono text-foreground"
                  title={origem.hashDoArtefato}
                >
                  {hashCurto(origem.hashDoArtefato)}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="inline text-muted-foreground">Congelado em: </dt>
                <dd className="inline text-foreground">{instante(origem.congeladoEm)}</dd>
              </div>
              <div className="min-w-0">
                <dt className="inline text-muted-foreground">Observado em: </dt>
                <dd className="inline text-foreground">{instante(origem.observadoEm)}</dd>
              </div>
              <div className="min-w-0 sm:col-span-2">
                <dt className="inline text-muted-foreground">Versão do motor da fábrica: </dt>
                <dd className="inline text-foreground">
                  {origem.motorVersaoConhecida ??
                    'não gravada pela fábrica. Inventar uma seria pior que declarar a ausência.'}
                </dd>
              </div>
            </dl>
          )}
          <p className="mt-2 text-pretty text-[13px] leading-relaxed text-muted-foreground">
            {leitura.limitacaoDeclarada}
          </p>
        </div>
      </div>
    </div>
  );
};

export const LeituraDeVideo: React.FC<{ leitura: VideoObservado }> = ({ leitura }) => {
  const estreito = useIsMobile(1024);
  const titulo = leitura.contrato.titulo ?? leitura.job.projetoTitulo;

  const direcao = (
    <Secao
      titulo="Estrutura e cenas"
      descricao="A intenção narrativa registrada pelo build. Leitura, não edição."
    >
      <Direcao contrato={leitura.contrato} />
    </Secao>
  );

  const preview = (
    <Secao titulo="Preview" descricao="Controles nativos. Nada começa a tocar sozinho.">
      <PlayerDoVideo
        videoUrl={leitura.videoUrl}
        posterUrl={leitura.posterUrl}
        titulo={titulo}
      />
      {leitura.videoUrl && (
        <a
          href={leitura.videoUrl}
          download
          className="mt-3 inline-flex min-h-9 items-center rounded-md border border-input px-3 text-[13px] text-foreground transition-colors duration-150 ease-out hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Baixar o arquivo do build
        </a>
      )}
    </Secao>
  );

  const inspecao = (
    <Secao
      titulo="Contrato e inspeção"
      descricao="O que sustenta a decisão de usar ou não usar esta versão."
    >
      <Inspecao leitura={leitura} />
    </Secao>
  );

  return (
    <div className="space-y-6">
      {/* O estado do job fica FORA das abas, sempre visível. */}
      <div className="flex flex-wrap items-center gap-2">
        <SeloDoJob estado={leitura.job.estado} />
        <SeloDeProcedencia procedencia={leitura.job.procedenciaExecucao} />
        <span className="text-[12px] text-muted-foreground">
          Motor declarado {leitura.job.motor} {leitura.job.motorVersao}.
        </span>
      </div>

      <DeclaracaoDeOrigem leitura={leitura} />

      {estreito ? (
        <Tabs defaultValue="preview">
          <TabsList className="w-full">
            <TabsTrigger value="direcao" className="flex-1">
              Direção
            </TabsTrigger>
            <TabsTrigger value="preview" className="flex-1">
              Preview
            </TabsTrigger>
            <TabsTrigger value="inspecao" className="flex-1">
              Inspeção
            </TabsTrigger>
          </TabsList>
          <TabsContent value="direcao" className="mt-4">
            {direcao}
          </TabsContent>
          <TabsContent value="preview" className="mt-4">
            {preview}
          </TabsContent>
          <TabsContent value="inspecao" className="mt-4">
            {inspecao}
          </TabsContent>
        </Tabs>
      ) : (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)_minmax(0,360px)]">
          {direcao}
          {preview}
          {inspecao}
        </div>
      )}
    </div>
  );
};
