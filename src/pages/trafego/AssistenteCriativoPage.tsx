/**
 * Assistente Criativo — a jornada do briefing à estratégia aprovada.
 *
 * ## O que esta página NÃO faz
 *
 * Montar, recarregar, listar ou reabrir NUNCA dispara geração. O modelo só roda
 * em `executarRun`, e `executarRun` só é chamada por clique. É a mesma regra que
 * o Estúdio já aplica à imagem, e ela vale mais aqui porque a etapa seguinte
 * desta frente é que gasta dinheiro.
 *
 * ## Por que o estado mora na URL
 *
 * `?view=` e `/:projectRef` fazem recarregar a página recuperar o contexto. O
 * fluxo do Aprova guardava tudo em estado de um componente só: fechar a aba
 * perdia a operação inteira, e não havia como mandar um link para alguém.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, Sparkles } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';

import {
  ErroDoAssistente,
  assistenteConfigurado,
  criarOperacao,
  enfileirarRun,
  executarRun,
  lerOperacao,
  listarOperacoes,
  gerarImagens,
  listarGeracoes,
  planejarGeracao,
  registrarDecisao,
} from '@/features/creative-studio/api';
import { FormularioDeBriefing } from '@/features/creative-studio/componentes/FormularioDeBriefing';
import { HistoricoDeOperacoes } from '@/features/creative-studio/componentes/HistoricoDeOperacoes';
import { PainelDeEstrategia } from '@/features/creative-studio/componentes/PainelDeEstrategia';
import { PainelDeProducao } from '@/features/creative-studio/componentes/PainelDeProducao';
import type {
  EntradaNovaOperacao,
  EscopoFeedback,
  OperacaoCompleta,
  PedidoDeDecisao,
  GeracaoRegistrada,
  PlanoDeGeracao,
  ResumoDaOperacao,
  SaidaDoAgente,
} from '@/features/creative-studio/tipos';

type Vista = 'briefing' | 'estrategia' | 'producao' | 'historico';

const VISTAS: { id: Vista; rotulo: string }[] = [
  { id: 'historico', rotulo: 'Histórico' },
  { id: 'briefing', rotulo: 'Briefing' },
  { id: 'estrategia', rotulo: 'Estratégia' },
  { id: 'producao', rotulo: 'Produção' },
];

function frase(erro: unknown): string {
  if (erro instanceof ErroDoAssistente) return erro.message;
  if (erro instanceof DOMException && erro.name === 'AbortError') return '';
  return 'O Assistente não conseguiu concluir esta operação.';
}

export default function AssistenteCriativoPage() {
  const { projectRef } = useParams<{ projectRef?: string }>();
  const [busca, setBusca] = useSearchParams();
  const navegar = useNavigate();

  const vista = (busca.get('view') as Vista | null) ?? (projectRef ? 'estrategia' : 'historico');

  const [operacoes, setOperacoes] = useState<ResumoDaOperacao[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(false);
  const [erroLista, setErroLista] = useState<string | null>(null);

  const [detalhe, setDetalhe] = useState<OperacaoCompleta | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [erroDetalhe, setErroDetalhe] = useState<string | null>(null);

  const [ocupado, setOcupado] = useState(false);
  const [erroAcao, setErroAcao] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const abortar = useRef<AbortController | null>(null);
  useEffect(() => () => abortar.current?.abort(), []);

  const configurado = assistenteConfigurado();

  function irPara(v: Vista, ref?: string) {
    const alvo = ref ?? projectRef;
    const query = `?view=${v}`;
    navegar(alvo ? `/trafego/meta/assistente-criativo/${alvo}${query}` : `/trafego/meta/assistente-criativo${query}`);
  }

  // ── Histórico ─────────────────────────────────────────────────────────────
  const carregarLista = useCallback(async () => {
    if (!configurado) return;
    setCarregandoLista(true);
    setErroLista(null);
    try {
      const r = await listarOperacoes({ limite: 20 });
      setOperacoes(r.operacoes);
    } catch (e) {
      const f = frase(e);
      if (f) setErroLista(f);
    } finally {
      setCarregandoLista(false);
    }
  }, [configurado]);

  useEffect(() => {
    if (!projectRef) void carregarLista();
  }, [projectRef, carregarLista]);

  // ── Detalhe / retomada ────────────────────────────────────────────────────
  const carregarDetalhe = useCallback(
    async (ref: string) => {
      if (!configurado) return;
      setCarregandoDetalhe(true);
      setErroDetalhe(null);
      try {
        setDetalhe(await lerOperacao(ref));
      } catch (e) {
        const f = frase(e);
        if (f) setErroDetalhe(f);
      } finally {
        setCarregandoDetalhe(false);
      }
    },
    [configurado],
  );

  useEffect(() => {
    if (projectRef) void carregarDetalhe(projectRef);
  }, [projectRef, carregarDetalhe]);

  // A run concluída mais recente é o lote que está na tela.
  const runAtual = useMemo(() => {
    const runs = detalhe?.runs ?? [];
    return runs.find((r) => r.status === 'COMPLETED' && r.output) ?? null;
  }, [detalhe]);

  const runPendente = useMemo(() => {
    const runs = detalhe?.runs ?? [];
    return runs.find((r) => r.status === 'QUEUED') ?? null;
  }, [detalhe]);

  const saida: SaidaDoAgente | null = runAtual?.output ?? null;

  // Caminhos já congelados. Vem das decisões que o servidor guardou; a tela não
  // inventa aprovação local que sumiria no recarregamento.
  const [aprovados, setAprovados] = useState<Set<string>>(new Set());
  useEffect(() => {
    setAprovados(new Set());
  }, [projectRef]);

  const [plano, setPlano] = useState<PlanoDeGeracao | null>(null);
  const [planejando, setPlanejando] = useState(false);
  const [gerando, setGerando] = useState(false);
  const [geracoes, setGeracoes] = useState<GeracaoRegistrada[]>([]);

  // Trocar de peça ou de formato invalida o plano anterior: um total na tela
  // que não corresponde mais à seleção é pior que total nenhum.
  useEffect(() => {
    setPlano(null);
  }, [projectRef]);

  const carregarGeracoes = useCallback(
    async (ref: string) => {
      if (!configurado) return;
      try {
        const r = await listarGeracoes(ref);
        setGeracoes(r.geracoes);
      } catch {
        /* a procedência é complementar; a falta dela não derruba a tela */
      }
    },
    [configurado],
  );

  useEffect(() => {
    if (projectRef) void carregarGeracoes(projectRef);
  }, [projectRef, carregarGeracoes]);

  // ── Ações ─────────────────────────────────────────────────────────────────
  async function criar(entrada: EntradaNovaOperacao) {
    setOcupado(true);
    setErroAcao(null);
    try {
      const criada = await criarOperacao(entrada);
      // A identidade já é durável aqui: mesmo que a execução falhe adiante, a
      // operação está no histórico e a run está retomável.
      navegar(`/trafego/meta/assistente-criativo/${criada.project_ref}?view=estrategia`);
      setAviso('Operação criada. Execute a estratégia quando quiser.');
      await executar(criada.project_ref, criada.run_ref);
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
    } finally {
      setOcupado(false);
    }
  }

  async function executar(ref: string, runRef: string) {
    setOcupado(true);
    setErroAcao(null);
    try {
      await executarRun(ref, runRef);
      setAviso(null);
      await carregarDetalhe(ref);
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
      await carregarDetalhe(ref);
    } finally {
      setOcupado(false);
    }
  }

  async function decidir(pedido: PedidoDeDecisao) {
    if (!projectRef) return;
    setOcupado(true);
    setErroAcao(null);
    try {
      await registrarDecisao(projectRef, pedido);
      setAprovados((atual) => new Set(atual).add(pedido.caminho));
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
    } finally {
      setOcupado(false);
    }
  }

  async function refinar(feedback: string, escopo: EscopoFeedback) {
    if (!projectRef) return;
    setOcupado(true);
    setErroAcao(null);
    try {
      const nova = await enfileirarRun(projectRef, {
        fase: 'REFACAO',
        feedback,
        feedback_escopo: escopo,
      });
      await executar(projectRef, nova.run_ref);
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
    } finally {
      setOcupado(false);
    }
  }

  async function planejar(creativeRefs: string[], formatIds: string[]) {
    if (!projectRef || !runAtual) return;
    setPlanejando(true);
    setErroAcao(null);
    try {
      setPlano(
        await planejarGeracao(projectRef, {
          run_ref: runAtual.run_ref,
          selected_creative_refs: creativeRefs,
          format_ids: formatIds,
        }),
      );
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
      setPlano(null);
    } finally {
      setPlanejando(false);
    }
  }

  async function gerar(creativeRefs: string[], formatIds: string[]) {
    if (!projectRef || !runAtual) return;
    setGerando(true);
    setErroAcao(null);
    try {
      await gerarImagens(projectRef, {
        run_ref: runAtual.run_ref,
        selected_creative_refs: creativeRefs,
        format_ids: formatIds,
      });
      await carregarGeracoes(projectRef);
      setAviso('Produção pedida. Acompanhe as peças no Estúdio Criativo.');
    } catch (e) {
      const f = frase(e);
      if (f) setErroAcao(f);
    } finally {
      setGerando(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Layout>
      <div className="p-4 md:p-8">
        <header className="max-w-[70ch]">
          <div className="kicker mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
            </span>
            criativo meta
          </div>
          <h1 className="font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.5rem]">
            Assistente Criativo
          </h1>
          <div className="mt-3 aurora-rule w-16" />
          <p className="mt-3 text-pretty text-sm text-muted-foreground">
            Transforma fatos declarados em estratégia, peças e copies rastreáveis. Nada aqui
            cria campanha, sobe mídia ou chama a Meta.
          </p>
        </header>

        {!configurado && (
          <div
            role="alert"
            className="mt-6 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-4 text-sm text-warning"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              O endereço do Assistente não está configurado neste ambiente, então nenhuma
              das ações abaixo pode ser executada.
            </span>
          </div>
        )}

        {/* Abas segmentadas num poço, como o resto do produto. */}
        <nav className="mt-6" aria-label="Etapas do Assistente">
          <div className="inline-flex rounded-lg border border-border bg-muted p-1">
            {VISTAS.map((v) => {
              const ativa = vista === v.id;
              const desabilitada =
                (v.id === 'estrategia' || v.id === 'producao') && !projectRef;
              return (
                <button
                  key={v.id}
                  type="button"
                  disabled={desabilitada}
                  aria-current={ativa ? 'page' : undefined}
                  onClick={() => {
                    if (v.id === 'historico' && projectRef) {
                      navegar('/trafego/meta/assistente-criativo?view=historico');
                      return;
                    }
                    const proxima = new URLSearchParams(busca);
                    proxima.set('view', v.id);
                    setBusca(proxima, { replace: true });
                  }}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-[background-color,color,box-shadow] duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${
                    ativa
                      ? 'bg-card text-foreground shadow-card'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {v.rotulo}
                </button>
              );
            })}
          </div>
        </nav>

        {aviso && (
          <p className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
            {aviso}
          </p>
        )}

        <main className="mt-6">
          {vista === 'historico' && (
            <HistoricoDeOperacoes
              operacoes={operacoes}
              carregando={carregandoLista}
              erro={erroLista}
              onAbrir={(ref) =>
                navegar(`/trafego/meta/assistente-criativo/${ref}?view=estrategia`)
              }
              onNova={() => irPara('briefing')}
            />
          )}

          {vista === 'producao' && (
            <div className="space-y-4">
              {!saida && (
                <div className="rounded-lg border border-border bg-card p-6 shadow-card">
                  <p className="text-sm font-medium text-foreground">
                    Ainda não há estratégia concluída para produzir.
                  </p>
                  <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                    A imagem sai de uma peça aprovada; sem lote não há o que aprovar.
                  </p>
                </div>
              )}
              {saida && (
                <PainelDeProducao
                  saida={saida}
                  aprovados={aprovados}
                  plano={plano}
                  planejando={planejando}
                  gerando={gerando}
                  erro={erroAcao}
                  onPlanejar={planejar}
                  onGerar={gerar}
                />
              )}
              {geracoes.length > 0 && (
                <section className="rounded-lg border border-border bg-card p-4 shadow-card">
                  <h2 className="font-display text-lg font-semibold">Procedência</h2>
                  <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                    De qual peça aprovada saiu cada trabalho de mídia. A mesma peça da
                    mesma run não é produzida duas vezes.
                  </p>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full min-w-[34rem] border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-border text-left">
                          <th scope="col" className="px-3 py-2 font-semibold">Peça</th>
                          <th scope="col" className="px-3 py-2 font-semibold">Formatos</th>
                          <th scope="col" className="px-3 py-2 font-semibold">Trabalho</th>
                        </tr>
                      </thead>
                      <tbody>
                        {geracoes.map((g) => (
                          <tr key={g.ponte_ref} className="border-b border-border last:border-0">
                            <td className="px-3 py-2 font-mono text-[11px]">{g.creative_ref}</td>
                            <td className="px-3 py-2">{g.slots.join(' · ')}</td>
                            <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                              {g.job_id}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </div>
          )}

          {vista === 'briefing' && (
            <FormularioDeBriefing ocupado={ocupado} erro={erroAcao} onEnviar={criar} />
          )}

          {vista === 'estrategia' && (
            <div className="space-y-4">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => navegar('/trafego/meta/assistente-criativo?view=historico')}
              >
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Voltar ao histórico
              </Button>

              {erroDetalhe && (
                <p
                  role="alert"
                  className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
                >
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  {erroDetalhe}
                </p>
              )}

              {carregandoDetalhe && (
                <p role="status" className="text-sm text-muted-foreground">
                  Lendo a operação…
                </p>
              )}

              {!carregandoDetalhe && !saida && runPendente && projectRef && (
                <div className="rounded-lg border border-border bg-card p-6 shadow-card">
                  <p className="text-sm font-medium text-foreground">
                    Esta operação tem uma estratégia enfileirada e ainda não executada.
                  </p>
                  <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                    Executar chama o modelo uma vez. Abrir esta página não executa nada
                    sozinha — por isso a run continua esperando você.
                  </p>
                  {erroAcao && (
                    <p role="alert" className="mt-3 text-sm text-destructive">
                      {erroAcao}
                    </p>
                  )}
                  <Button
                    type="button"
                    className="mt-4"
                    disabled={ocupado || !configurado}
                    onClick={() => executar(projectRef, runPendente.run_ref)}
                  >
                    {ocupado ? 'Executando…' : 'Executar estratégia'}
                  </Button>
                </div>
              )}

              {!carregandoDetalhe && !saida && !runPendente && detalhe && (
                <div className="rounded-lg border border-border bg-card p-6 shadow-card">
                  <p className="text-sm font-medium text-foreground">
                    Esta operação ainda não tem um lote concluído.
                  </p>
                  <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                    A última execução não chegou a produzir uma estratégia válida. O
                    histórico de runs fica registrado; enfileirar outra é o caminho.
                  </p>
                </div>
              )}

              {saida && runAtual && (
                <PainelDeEstrategia
                  saida={saida}
                  runRef={runAtual.run_ref}
                  aprovados={aprovados}
                  ocupado={ocupado}
                  erro={erroAcao}
                  onDecidir={decidir}
                  onRefinar={refinar}
                />
              )}
            </div>
          )}
        </main>
      </div>
    </Layout>
  );
}
