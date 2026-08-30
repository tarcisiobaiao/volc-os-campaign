/**
 * /redator/funil/:runId — UM funil, como grafo.
 *
 * ## Três correções de peso em relação à primeira versão
 *
 * **O custo dominava.** Ele abria a tela num cartão grande com aurora atrás,
 * como se a pergunta fosse "quanto gastei". Não é: durante o run a pergunta é
 * "onde o motor está", e depois dele é "o que ficou escrito". O gasto virou uma
 * linha na régua superior, ao lado das outras medidas.
 *
 * **A coluna de tentativas pesava demais.** Cinco execuções do mesmo card
 * ocupavam 220px permanentes de uma tela cuja manchete é o funil. Viraram um
 * seletor no cabeçalho, do tamanho do que são: navegação entre versões.
 *
 * **A grade de cards mentia sobre a estrutura.** Ver `GrafoDoFunil`.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, GitFork, RefreshCw } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { GrafoDoFunil } from '@/components/redator/GrafoDoFunil';
import { Matriz } from '@/components/redator/MatrizDoRun';
import { LinhaDoFunil } from '@/components/redator/PainelDoRun';
import { useMatrizDoRun } from '@/hooks/redator/useMatrizDoRun';
import { pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { ReleituraDoWordPress, RunDoRedator } from '@/types/publicacao';
import type { FunilEscrito } from '@/types/redatorPaginas';

const VIVO = new Set(['queued', 'running']);
const ABA = cn(
  'rounded-md px-3 py-2 text-sm font-medium',
  'bg-transparent text-muted-foreground shadow-none',
  'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-card',
);

const ROTULO_DE_STATUS: Record<string, string> = {
  queued: 'na fila', running: 'escrevendo', done: 'concluído',
  failed: 'falhou', cancelled: 'cancelado',
};

function quando(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function relogio(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Uma medida da régua. Todas do mesmo tamanho de propósito: o custo é UMA das
 *  coisas que se olha, não a manchete. */
const Medida: React.FC<{ rotulo: string; valor: string; nota?: string; alerta?: boolean }> =
  ({ rotulo, valor, nota, alerta }) => (
    <Card className="relative min-w-[10rem] flex-1 overflow-hidden shadow-card">
      <span className={cn('pointer-events-none absolute inset-x-0 top-0 h-0.5', alerta ? 'bg-warning' : 'bg-primary')} />
      <CardContent className="p-4">
        <div className="kicker">{rotulo}</div>
        <div className={cn('mt-2 font-display text-2xl font-bold tracking-tight tabular', alerta && 'text-muted-foreground')}>
          {valor}
        </div>
        {nota && <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{nota}</p>}
      </CardContent>
    </Card>
  );

const FunilPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const escolhido = Number(runId) || null;

  const { matriz, carregando, erro, pulsou, corrente, segundosSemCobranca, recarregar }
    = useMatrizDoRun(escolhido);

  const [funil, setFunil] = useState<FunilEscrito | null>(null);
  const [irmaos, setIrmaos] = useState<RunDoRedator[]>([]);
  const statusDoRun = matriz?.run.status;
  const cardDoRun = matriz?.run.opportunity_id;

  useEffect(() => {
    if (escolhido == null) { setFunil(null); return; }
    let ativo = true;
    pautadorApi.paginasDoRun(escolhido)
      .then((f) => ativo && setFunil(f))
      .catch(() => ativo && setFunil(null));
    return () => { ativo = false; };
  }, [escolhido, statusDoRun]);

  useEffect(() => {
    if (cardDoRun == null) return;
    let ativo = true;
    pautadorApi.runsDoRedator(cardDoRun)
      .then((r) => ativo && setIrmaos(r))
      .catch(() => ativo && setIrmaos([]));
    return () => { ativo = false; };
  }, [cardDoRun]);

  const vivo = !!matriz && VIVO.has(matriz.run.status);
  const parado = vivo && segundosSemCobranca > 180;
  const totalPassos = useMemo(
    () => (matriz ? Object.keys(matriz.celulas).length + Object.keys(matriz.faixa).length : 0),
    [matriz],
  );
  const publicadas = matriz?.publicadas.length ?? 0;

  // ⚠️ "como rascunho" era texto FIXO nesta régua, e virava mentira no instante
  // em que alguém publicasse no WordPress. O motor sobe tudo como rascunho de
  // propósito (`engine/config.yaml: publish_status: draft` — "generate → draft
  // → human reviews and clicks publish"), então o rascunho é o estado normal;
  // o que faltava era a tela saber quando ele deixa de ser.
  const noAr = matriz?.publicadas.filter((p) => p.status_wp === 'publish').length ?? 0;
  const [relendo, setRelendo] = useState(false);
  const [releitura, setReleitura] = useState<ReleituraDoWordPress | null>(null);

  const reler = async () => {
    if (!escolhido) return;
    setRelendo(true);
    try {
      const r = await pautadorApi.relerDoWordPress(escolhido);
      setReleitura(r);
      // Recarrega a matriz: `status_wp` e `lp_url` acabaram de mudar no banco, e
      // a régua acima lê deles.
      if (r.mudaram > 0) recarregar();
    } catch (e) {
      setReleitura({
        run_row_id: escolhido, paginas: [], mudaram: 0, no_ar: 0,
        resumo: e instanceof Error ? e.message : 'Falhei ao reler o WordPress.',
      });
    } finally {
      setRelendo(false);
    }
  };

  // ⚠️ SINCRONIZA SOZINHO ao abrir, e a razão é de quem é a verdade.
  //
  // Quem publica é o humano, no WordPress — fora deste sistema. `status_wp` e
  // `url` são gravados UMA vez, pelo worker, no momento em que a página nasce
  // como rascunho. Daí em diante nosso banco é cache, e cache que só atualiza
  // no botão mente por padrão.
  //
  // Medido em 19/08/2026: o operador publicou as 6 páginas do run 7 no
  // WordPress e a tela continuou dizendo "rascunho no WP" nas seis. O botão
  // "reler do WordPress" existia; exigir que alguém lembre de clicá-lo é o
  // defeito, não a solução.
  //
  // Roda DEPOIS da matriz carregar e sem bloquear o render: são ~6 chamadas ao
  // WP. E só quando há página publicada e o run não está vivo — durante a
  // escrita o worker ainda está gravando, e reler competiria com ele.
  const [sincronizou, setSincronizou] = useState<number | null>(null);
  useEffect(() => {
    if (!escolhido || vivo || publicadas === 0) return;
    if (sincronizou === escolhido) return;      // uma vez por run, não em laço
    setSincronizou(escolhido);
    void reler();
    // `reler` é estável o bastante para este uso; incluí-lo aqui reinicia o
    // efeito a cada render e produz o laço que a guarda acima evita.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escolhido, vivo, publicadas, sincronizou]);

  return (
    <Layout>
      <div className="space-y-6 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Link to="/redator"
                className="kicker inline-flex items-center gap-1.5 text-muted-foreground transition-[color] duration-150 hover:text-foreground">
            <ArrowLeft className="h-3 w-3" aria-hidden /> quadro do redator
          </Link>

          <div className="flex flex-wrap items-center gap-2">
            {/* As outras tentativas: navegação, não coluna. Um funil costuma
                ser reescrito duas ou três vezes antes de ficar bom — o card #73
                teve cinco — e comparar versões é uma troca de aba, não um
                painel permanente ocupando 220px da manchete. */}
            {irmaos.length > 1 && (
              <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted p-1">
                <span className="kicker px-1.5 text-muted-foreground">tentativas</span>
                {[...irmaos].reverse().map((r, i) => (
                  <Link key={r.id} to={`/redator/funil/${r.id}`}
                        title={`${ROTULO_DE_STATUS[r.status] ?? r.status} · ${quando(r.criado_em)}`}
                        aria-current={r.id === escolhido ? 'page' : undefined}
                        className={cn('flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 text-[11px] tabular',
                          r.id === escolhido
                            ? 'bg-card text-foreground shadow-card'
                            : r.status === 'done'
                              ? 'text-foreground hover:bg-card/70'
                              : 'text-muted-foreground hover:bg-card/70')}>
                    {i + 1}
                  </Link>
                ))}
              </div>
            )}
            {vivo && (
              <span className={cn('kicker flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 shadow-card transition-opacity duration-150',
                                  pulsou ? 'opacity-100' : 'opacity-60')}>
                <span className={cn('inline-block h-1.5 w-1.5 rounded-full', pulsou ? 'bg-primary' : 'bg-muted-foreground')} />
                3s · ao vivo
              </span>
            )}
            <Button variant="outline" size="sm" className="hover-lift" onClick={recarregar}>
              <RefreshCw className={cn('h-4 w-4', carregando && 'animate-spin')} aria-hidden />
              recarregar
            </Button>
          </div>
        </div>

        <header className="reveal" style={{ ['--i' as never]: 0 }}>
          <div className="kicker mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
              <GitFork className="h-3.5 w-3.5" aria-hidden />
            </span>
            funil escrito
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight leading-[1.05] sm:text-4xl">
            {matriz?.titulo || (matriz ? `card #${matriz.run.opportunity_id}` : 'Funil')}
          </h1>
          <div className="mt-3 aurora-rule w-16" />
        </header>

        {carregando && !matriz && <p className="mt-8 text-sm text-muted-foreground">Lendo a execução…</p>}
        {erro && <p className="mt-8 text-sm text-destructive">{erro}</p>}
        {!escolhido && (
          <p className="mt-8 max-w-[60ch] text-sm leading-relaxed text-muted-foreground">
            Endereço de funil inválido. Volte ao{' '}
            <Link to="/redator" className="underline underline-offset-4">quadro do redator</Link>.
          </p>
        )}

        {matriz && (
          <>
            <div className="overflow-hidden rounded-xl border border-border bg-card p-4 shadow-card">
              <LinhaDoFunil m={matriz} />
            </div>

            {/* A RÉGUA. O custo é uma medida entre outras — não o cartão com
                aurora que abria a tela antes. */}
            <div className="flex flex-wrap gap-4">
              <Medida rotulo="páginas no wordpress"
                      valor={`${publicadas}/${matriz.run.paginas_planejadas ?? '—'}`}
                      nota={publicadas === 0 ? undefined
                        : noAr === 0 ? 'todas como rascunho'
                        : noAr === publicadas ? 'todas no ar'
                        : `${noAr} no ar · ${publicadas - noAr} em rascunho`} />
              <Medida rotulo="custo"
                      valor={`US$ ${matriz.custo_total.toFixed(2).replace('.', ',')}`}
                      nota={matriz.teto_usd
                        ? `teto de US$ ${matriz.teto_usd.toFixed(2).replace('.', ',')}`
                        : matriz.subestimado ? 'pode estar abaixo da fatura' : undefined} />
              <Medida rotulo="etapas" valor={String(totalPassos)}
                      nota={vivo && corrente
                        ? `${corrente.etapa} · p${corrente.page_number} · ${corrente.segundos}s`
                        : ROTULO_DE_STATUS[matriz.run.status] ?? matriz.run.status} />
              {parado && (
                <Medida rotulo="sem cobrança há" valor={relogio(segundosSemCobranca)} alerta
                        nota="a pesquisa chega a levar três minutos" />
              )}
            </div>

            {/* O ELO QUE FECHA O CICLO PAUTA → FUNIL → CAMPANHA.
                `status_wp` e `lp_url` são gravados uma única vez, pelo worker.
                Sem reler, publicar a LP no WordPress não muda nada aqui — e o
                Hub de Tráfego, que barra LP em rascunho e URL provisória,
                barraria para sempre com a página já no ar. */}
            {publicadas > 0 && !vivo && (
              <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
                <Button variant="outline" size="sm" className="gap-2"
                        disabled={relendo} onClick={reler}>
                  <RefreshCw className={cn('h-3.5 w-3.5', relendo && 'animate-spin')} aria-hidden />
                  {relendo ? 'lendo o WordPress…' : 'reler do WordPress'}
                </Button>
                {/* ⚠️ O texto de antes ensinava a clicar no botão. Depois que
                    a leitura passou a rodar sozinha ao abrir, ensinar isso vira
                    ruído — o botão continua para forçar uma releitura no meio da
                    sessão, que é outro caso. */}
                <p className="max-w-[62ch] text-[11px] leading-relaxed text-muted-foreground">
                  {relendo
                    ? 'Lendo o WordPress — ele é quem sabe o que está publicado.'
                    : releitura
                      ? releitura.resumo
                      : 'Sincronizado com o WordPress ao abrir esta tela. Publicou '
                        + 'agora, noutra aba? Releia para trazer o permalink.'}
                </p>
              </div>
            )}

            {releitura && releitura.paginas.some((p) => p.mudou || p.erro) && (
              <ul className="mt-3 space-y-1.5 border-l border-border pl-3">
                {releitura.paginas.filter((p) => p.mudou || p.erro).map((p) => (
                  <li key={p.post_id} className="text-[11px] leading-relaxed">
                    <span className="kicker">{p.role || p.post_type}</span>{' '}
                    <span className="tabular text-muted-foreground">#{p.post_id}</span>{' '}
                    {p.erro
                      ? <span className="text-destructive">{p.erro}</span>
                      : (
                        <>
                          <span className="text-muted-foreground">
                            {p.status_antes} → </span>
                          <span className={p.status_agora === 'publish' ? 'text-success' : ''}>
                            {p.status_agora}
                          </span>
                          {p.url_agora !== p.url_antes && (
                            <span className="ml-2 break-all text-muted-foreground">
                              {p.url_agora}
                            </span>
                          )}
                        </>
                      )}
                  </li>
                ))}
              </ul>
            )}

            {matriz.run.erro && (
              <details className="rounded-lg border border-destructive/40 p-4">
                <summary className="cursor-pointer text-sm text-destructive">
                  {matriz.run.erro.slice(0, 200)}{matriz.run.erro.length > 200 && '…'}
                </summary>
                <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">
                  {matriz.run.erro}
                </pre>
              </details>
            )}

            <Tabs defaultValue="funil" className="mt-4">
              <TabsList className="h-auto min-h-11 w-full justify-start gap-1 rounded-lg border border-border bg-muted p-1">
                <TabsTrigger value="funil" className={ABA}>
                  o funil
                  {funil && !funil.sem_artefatos && (
                    <span className="ml-2 tabular text-muted-foreground">{funil.paginas.length}</span>
                  )}
                </TabsTrigger>
                <TabsTrigger value="etapas" className={ABA}>
                  etapas do motor
                  <span className="ml-2 tabular text-muted-foreground">{totalPassos}</span>
                </TabsTrigger>
              </TabsList>

              <TabsContent value="funil" className="mt-6">
                {!funil && <p className="text-sm text-muted-foreground">Lendo o funil…</p>}
                {funil?.sem_artefatos && (
                  <p className="max-w-[68ch] text-sm leading-relaxed text-muted-foreground">
                    {funil.motivo} As páginas publicadas continuam no WordPress —
                    o que se perdeu foi a prévia local.
                  </p>
                )}
                {funil && !funil.sem_artefatos && (
                  <GrafoDoFunil paginas={funil.paginas} runId={matriz.run.id} />
                )}
              </TabsContent>

              <TabsContent value="etapas" className="mt-6">
                <Matriz m={matriz} corrente={corrente} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </Layout>
  );
};

export default FunilPage;
