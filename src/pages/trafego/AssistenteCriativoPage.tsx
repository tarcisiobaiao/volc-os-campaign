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
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, History, Loader2, Sparkles } from 'lucide-react';

import { assistenteIntegrado } from '@/components/trafego/meta/ponteAssistente';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';

import {
  ErroDoAssistente,
  assistenteConfigurado,
  criarOperacao,
  enfileirarRun,
  enviarFotografia,
  executarRun,
  lerCapacidades,
  lerOperacao,
  listarFotografias,
  listarOperacoes,
  gerarImagens,
  listarGeracoes,
  planejarGeracao,
  registrarDecisao,
  removerFotografia,
} from '@/features/creative-studio/api';
import { FormularioDeBriefing } from '@/features/creative-studio/componentes/FormularioDeBriefing';
import { HistoricoDeOperacoes } from '@/features/creative-studio/componentes/HistoricoDeOperacoes';
import { PainelDeEstrategia } from '@/features/creative-studio/componentes/PainelDeEstrategia';
import { PainelDeProducao } from '@/features/creative-studio/componentes/PainelDeProducao';
import { FotografiaReal } from '@/features/creative-studio/componentes/FotografiaReal';
import type {
  Anexo,
  Capacidades,
  EntradaNovaOperacao,
  EscopoFeedback,
  OperacaoCompleta,
  PedidoDeDecisao,
  GeracaoRegistrada,
  PlanoDeGeracao,
  ResumoDaOperacao,
  SaidaDoAgente,
} from '@/features/creative-studio/tipos';

import '@/features/creative-studio/studio.css';
import { GaleriaDeGeracoes } from '@/features/creative-studio/componentes/GaleriaDeGeracoes';

type Vista = 'briefing' | 'estrategia' | 'producao' | 'assets' | 'historico';

const VISTAS: { id: Vista; rotulo: string }[] = [
  { id: 'briefing', rotulo: 'Briefing' },
  { id: 'estrategia', rotulo: 'Estratégia' },
  { id: 'producao', rotulo: 'Produção' },
  { id: 'assets', rotulo: 'Criativos' },
];

function frase(erro: unknown): string {
  if (erro instanceof ErroDoAssistente) return erro.message;
  if (erro instanceof DOMException && erro.name === 'AbortError') return '';
  return 'O Assistente não conseguiu concluir esta operação.';
}

export default function AssistenteCriativoPage() {
  const { projectRef } = useParams<{ projectRef?: string }>();
  const projetoAtivo = useRef(projectRef);
  projetoAtivo.current = projectRef;
  const [busca, setBusca] = useSearchParams();
  const navegar = useNavigate();

  const solicitada = busca.get('view');
  const vista: Vista = ['briefing', 'estrategia', 'producao', 'assets', 'historico'].includes(solicitada ?? '') ? solicitada as Vista : projectRef ? 'estrategia' : 'briefing';
  const vistaAtiva = useRef(vista);
  vistaAtiva.current = vista;

  const [operacoes, setOperacoes] = useState<ResumoDaOperacao[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(false);
  const [erroLista, setErroLista] = useState<string | null>(null);

  const [detalhe, setDetalhe] = useState<OperacaoCompleta | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [erroDetalhe, setErroDetalhe] = useState<string | null>(null);

  const [ocupado, setOcupado] = useState(false);
  const [erroAcao, setErroAcao] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Only an explicit new-version action rotates this identity. Reload/retry
  // keeps it so a lost response cannot buy the same images again.
  const [versoesDeGeracao, setVersoesDeGeracao] = useState<Record<string, string>>(() => {
    try {
      const saved: unknown = JSON.parse(sessionStorage.getItem('volc:creative-generation-versions') || '{}');
      if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {};
      return Object.fromEntries(Object.entries(saved).filter(([key, value]) =>
        /^crproj_[a-f0-9]{24}$/.test(key) && typeof value === 'string' && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value)));
    }
    catch { return {}; }
  });
  const geracaoRef = projectRef ? versoesDeGeracao[projectRef] ?? null : null;
  function prepararNovaVersao() {
    if (!projectRef || geracaoEmCurso.current) return;
    const versoes = { ...versoesDeGeracao, [projectRef]: crypto.randomUUID() };
    setVersoesDeGeracao(versoes);
    try { sessionStorage.setItem('volc:creative-generation-versions', JSON.stringify(versoes)); } catch { /* memory remains valid */ }
    setPlano(null);
    setErroAcao(null);
    setAviso('Nova versão preparada. Confira as peças, os formatos e autorize a geração abaixo. Os arquivos anteriores permanecem na biblioteca.');
  }

  const abortar = useRef<AbortController | null>(null);
  useEffect(() => () => abortar.current?.abort(), []);

  const configurado = assistenteConfigurado();
  const emOperacao = Boolean(projectRef);

  // ── Capacidades: o catálogo de formatos e a identidade do motor ──────────
  //
  // Buscadas UMA vez por montagem, e são leitura pura: não geram, não gastam e
  // não criam nada. Antes o catálogo era uma constante escrita nesta feature,
  // com três dos quatro formatos que o motor produz — o `1.91x1` simplesmente
  // não existia na tela, e nenhum teste falhava.
  const [capacidades, setCapacidades] = useState<Capacidades | null>(null);
  useEffect(() => {
    if (!configurado) return;
    let vivo = true;
    void (async () => {
      try {
        const lidas = await lerCapacidades();
        if (vivo) setCapacidades(lidas);
      } catch {
        // Falhar aqui não pode derrubar a página: sem catálogo os seletores
        // dizem que não há formato, que é a verdade, e o resto continua legível.
      }
    })();
    return () => {
      vivo = false;
    };
  }, [configurado]);

  // ── Fotografia real ──────────────────────────────────────────────────────
  const [anexo, setAnexo] = useState<Anexo | null>(null);
  const [enviandoFoto, setEnviandoFoto] = useState(false);
  const [erroDaFoto, setErroDaFoto] = useState<string | null>(null);
  // Uma retomada não pode transformar inspiração em colagem silenciosamente.
  const [modoDeComposicao, setModoDeComposicao] = useState('');
  // Os formatos escolhidos no briefing, para a Produção herdar em vez de
  // marcar todos: o "até N imagens" da entrada não pode triplicar no ato que
  // gasta.
  const [formatosDoBriefing, setFormatosDoBriefing] = useState<string[]>([]);

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
    if (vista === 'historico') void carregarLista();
  }, [vista, carregarLista]);

  // ── Detalhe / retomada ────────────────────────────────────────────────────
  const carregarDetalhe = useCallback(
    async (ref: string) => {
      if (!configurado) return;
      setCarregandoDetalhe(true);
      setErroDetalhe(null);
      try {
        const recebido = await lerOperacao(ref);
        if (projetoAtivo.current === ref) setDetalhe(recebido);
      } catch (e) {
        const f = frase(e);
        if (f && projetoAtivo.current === ref) setErroDetalhe(f);
      } finally {
        if (projetoAtivo.current === ref) setCarregandoDetalhe(false);
      }
    },
    [configurado],
  );

  useEffect(() => {
    setDetalhe(null);
    if (projectRef) void carregarDetalhe(projectRef);
  }, [projectRef, carregarDetalhe]);

  // A fotografia é da OPERAÇÃO, e é relida ao abri-la. Sem esta leitura, um F5
  // mostrava a produção sem a foto que o operador já tinha enviado — e a peça
  // sairia diferente da que ele preparou.
  useEffect(() => {
    setAnexo(null);
    setModoDeComposicao('');
    setErroDaFoto(null);
    if (!projectRef || !configurado) return;
    let vivo = true;
    void (async () => {
      try {
        const { anexos } = await listarFotografias(projectRef);
        if (vivo) setAnexo(anexos[0] ?? null);
      } catch {
        // A ausência de anexo é o caso normal; um erro de leitura aqui não pode
        // impedir a revisão da estratégia.
      }
    })();
    return () => {
      vivo = false;
    };
  }, [projectRef, configurado]);

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

  // ── Aprovação: a autoridade é o servidor ──────────────────────────────────
  //
  // Antes isto era um `Set` de sessão. As decisões estavam gravadas no banco e
  // mesmo assim o F5 mostrava o lote inteiro como não revisado — o operador
  // reaprovava por engano ou achava que tinha perdido o trabalho.
  //
  // `aprovacoes_validas` chega POR RUN e já foi conferida contra o conteúdo
  // daquela run: uma peça refinada mantém a `ref` e perde a aprovação, porque
  // o que foi aprovado era o texto anterior. Essa conta não pode ser feita
  // aqui — a tela não tem o hash aprovado nem autoridade para comparar.
  const aprovadosDoServidor = useMemo(() => {
    const porRun = detalhe?.aprovacoes_validas ?? {};
    return new Set(runAtual ? porRun[runAtual.run_ref] ?? [] : []);
  }, [detalhe, runAtual]);

  // Sobreposição otimista, viva só entre o clique e a releitura do detalhe.
  // Sem ela o botão fica mudo por um round-trip; com ela, a resposta do
  // servidor ainda é quem manda, porque a releitura zera este mapa.
  const [decisoesPendentes, setDecisoesPendentes] = useState<Map<string, boolean>>(new Map());
  useEffect(() => {
    setDecisoesPendentes(new Map());
  }, [projectRef, detalhe]);

  const aprovados = useMemo(() => {
    const efetivos = new Set(aprovadosDoServidor);
    for (const [caminho, aprovado] of decisoesPendentes) {
      if (aprovado) efetivos.add(caminho);
      else efetivos.delete(caminho);
    }
    return efetivos;
  }, [aprovadosDoServidor, decisoesPendentes]);

  const [plano, setPlano] = useState<PlanoDeGeracao | null>(null);
  const [planejando, setPlanejando] = useState(false);
  const geracaoEmCurso = useRef<string | null>(null);
  const [geracaoPendente, setGeracaoPendente] = useState<{
    projectRef: string;
    plano: PlanoDeGeracao;
    runRef: string;
    geracaoRef: string | null;
  } | null>(null);
  const gerando = geracaoPendente !== null && geracaoPendente.projectRef === projectRef;
  const [falhaDaGeracao, setFalhaDaGeracao] = useState<{ projectRef: string; mensagem: string } | null>(null);
  const [geracoes, setGeracoes] = useState<GeracaoRegistrada[]>([]);
  const [erroGeracoes, setErroGeracoes] = useState<string | null>(null);
  const [lendoGeracoes, setLendoGeracoes] = useState(false);

  // Trocar de peça ou de formato invalida o plano anterior: um total na tela
  // que não corresponde mais à seleção é pior que total nenhum.
  useEffect(() => {
    setPlano(null);
    setGeracoes([]);
    setErroGeracoes(null);
  }, [projectRef]);

  const carregarGeracoes = useCallback(
    async (ref: string) => {
      if (!configurado) return;
      setLendoGeracoes(true);
      setErroGeracoes(null);
      try {
        const r = await listarGeracoes(ref);
        if (projetoAtivo.current === ref) setGeracoes(r.geracoes);
      } catch (e) {
        if (projetoAtivo.current === ref) setErroGeracoes(frase(e));
      } finally {
        if (projetoAtivo.current === ref) setLendoGeracoes(false);
      }
    },
    [configurado],
  );

  useEffect(() => {
    if (!projectRef) return;
    let saiu = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function acompanhar() {
      await carregarGeracoes(projectRef!);
      // Read-only registry polling also recovers bridges after a lost POST
      // response or a reload. It never submits another paid generation.
      if (!saiu && (gerando || vista === 'assets')) timer = setTimeout(acompanhar, 4000);
    }
    void acompanhar();
    return () => { saiu = true; clearTimeout(timer); };
  }, [projectRef, carregarGeracoes, gerando, vista]);

  // ── Ações ─────────────────────────────────────────────────────────────────
  async function criar(entrada: EntradaNovaOperacao) {
    setOcupado(true);
    setErroAcao(null);
    // A escolha da entrada viaja até a Produção. Antes ela era descartada, e a
    // Produção começava com três formatos marcados — o total que o operador
    // autorizava não era o que ele tinha lido no briefing.
    setFormatosDoBriefing([...(entrada.formatos_permitidos ?? [])]);
    try {
      const criada = await criarOperacao(entrada);
      // A identidade já é durável aqui: mesmo que a execução falhe adiante, a
      // operação está no histórico e a run está retomável.
      navegar(`/trafego/meta/assistente-criativo/${criada.project_ref}?view=estrategia`);
      // A frase anterior — "execute a estratégia quando quiser" — era falsa: a
      // linha seguinte já executa, e o modelo de texto já está rodando enquanto
      // ela aparece na tela. Um aviso que descreve o contrário do que está
      // acontecendo é pior que aviso nenhum quando o ato custa dinheiro.
      setAviso('Operação criada. Gerando a estratégia com o agente — isto leva alguns instantes.');
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
      setDecisoesPendentes((atual) =>
        new Map(atual).set(pedido.caminho, pedido.decisao === 'APROVADO'),
      );
      // Reler é o que faz a decisão virar estado durável em vez de memória de
      // aba: a partir daqui, recarregar a página mostra a mesma revisão.
      await carregarDetalhe(projectRef);
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
    if (!projectRef || !runAtual || geracaoEmCurso.current === projectRef) return;
    if (anexo && !modoDeComposicao) {
      setPlano(null);
      setErroAcao('Escolha como usar a imagem anexada: inspiração visual, fotografia preservada ou reinterpretação.');
      return;
    }
    setPlanejando(true);
    setErroAcao(null);
    try {
      setPlano(
        await planejarGeracao(projectRef, {
          run_ref: runAtual.run_ref,
          geracao_ref: geracaoRef,
          selected_creative_refs: creativeRefs,
          format_ids: formatIds,
          anexo_ref: anexo?.anexo_ref ?? null,
          modo_de_composicao: anexo ? modoDeComposicao : 'sem_foto',
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

  /**
   * O ato que gasta. Exige um plano conferido e a confirmação explícita dele.
   *
   * `autorizacao` não é telemetria: é o consentimento que a rota exige, e o
   * servidor reconfere os três campos contra o que ele mesmo mediu. Sem plano
   * na tela não há o que confirmar, então não há como chegar aqui — e se a
   * seleção mudou depois do plano, o servidor recusa com o total divergente em
   * vez de gerar um lote que ninguém aprovou.
   */
  async function gerar(
    creativeRefs: string[],
    formatIds: string[],
    teto: number | null,
    aceitoSemEstimativa: boolean,
  ) {
    // Sem selo não há o que autorizar: ele é emitido pelo plano e amarra o
    // consentimento ao CONTEÚDO exato que a pessoa leu.
    if (!projectRef || !runAtual || !plano || !plano.modelo_de_imagem) return;
    if (!plano.selo_do_plano) return;
    // A ref trava inclusive dois cliques antes do próximo render. O estado
    // guarda a operação e o plano autorizado, mesmo que a pessoa navegue.
    if (geracaoEmCurso.current) {
      if (geracaoEmCurso.current !== projectRef) {
        setErroAcao('Há uma geração em andamento em outra operação. Aguarde a resposta antes de iniciar outra.');
      }
      return;
    }
    const operacaoDoPedido = projectRef;
    geracaoEmCurso.current = operacaoDoPedido;
    setGeracaoPendente({ projectRef: operacaoDoPedido, plano, runRef: runAtual.run_ref, geracaoRef });
    setFalhaDaGeracao(null);
    setErroAcao(null);
    setAviso(null);
    irPara('assets', operacaoDoPedido);
    try {
      await gerarImagens(projectRef, {
        run_ref: runAtual.run_ref,
        geracao_ref: geracaoRef,
        selected_creative_refs: creativeRefs,
        format_ids: formatIds,
        anexo_ref: anexo?.anexo_ref ?? null,
        modo_de_composicao: anexo ? modoDeComposicao : 'sem_foto',
        autorizacao: {
          modelo: plano.modelo_de_imagem,
          total_de_renders: plano.total_de_renders,
          teto_custo_usd: teto,
          selo_do_plano: plano.selo_do_plano,
          aceito_sem_estimativa: aceitoSemEstimativa,
        },
      });
      if (projetoAtivo.current === operacaoDoPedido) {
        await carregarGeracoes(operacaoDoPedido);
        if (projetoAtivo.current === operacaoDoPedido) {
          setAviso('Resposta recebida. Confira as imagens e eventuais falhas em Criativos.');
          if (vistaAtiva.current === 'producao') irPara('assets', operacaoDoPedido);
        }
      }
    } catch (e) {
      const f = frase(e);
      if (f && projetoAtivo.current === operacaoDoPedido) {
        const mensagem = `${f} Confira a aba Criativos antes de solicitar outra geração: a solicitação pode ter sido recebida mesmo sem uma resposta nesta tela.`;
        setErroAcao(mensagem);
        setFalhaDaGeracao({ projectRef: operacaoDoPedido, mensagem });
      }
    } finally {
      geracaoEmCurso.current = null;
      setGeracaoPendente(null);
    }
  }

  async function anexarFoto(arquivo: File) {
    if (!projectRef || geracaoEmCurso.current === projectRef) return;
    setEnviandoFoto(true);
    setErroDaFoto(null);
    try {
      setAnexo(await enviarFotografia(projectRef, arquivo));
      setModoDeComposicao('');
      // A foto muda a peça: o plano conferido antes dela não descreve mais o
      // que este clique produziria.
      setPlano(null);
    } catch (e) {
      const f = frase(e);
      if (f) setErroDaFoto(f);
    } finally {
      setEnviandoFoto(false);
    }
  }

  async function removerFoto() {
    if (!projectRef || !anexo || geracaoEmCurso.current === projectRef) return;
    setErroDaFoto(null);
    const alvo = anexo.anexo_ref;
    // Otimista: o botão precisa responder na hora, e a releitura corrige.
    setAnexo(null);
    setPlano(null);
    try {
      await removerFotografia(projectRef, alvo);
    } catch (e) {
      const f = frase(e);
      if (f) setErroDaFoto(f);
    }
  }

  const integrado = assistenteIntegrado();
  const Moldura = integrado ? Fragment : Layout;
  useEffect(() => {
    if (integrado && projectRef) window.parent.postMessage({
      type: 'volc:creative-project', projectRef,
    }, window.location.origin);
  }, [integrado, projectRef]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Moldura>
      <div className={`studio-workspace ${emOperacao ? 'studio-workspace--wide' : ''}`}>
        <div className="mb-5 flex items-center justify-between gap-3">
          {!integrado && <Button variant="ghost" size="sm" onClick={() => navegar('/trafego?rede=meta')}><ArrowLeft className="h-4 w-4" aria-hidden />Tráfego Meta</Button>}
          <Button variant="ghost" size="sm" onClick={() => navegar('/trafego/meta/assistente-criativo?view=historico')}><History className="h-4 w-4" aria-hidden />Histórico</Button>
        </div>
        <header hidden={integrado} className={`mb-6 ${emOperacao ? 'text-left' : 'text-center'}`}>
          <div className={`kicker mb-3 flex items-center gap-2 ${emOperacao ? 'justify-start' : 'justify-center'}`}><span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Sparkles className="h-3.5 w-3.5" aria-hidden /></span>Estúdio · Meta Ads</div>
          <h1 className={`font-display font-bold leading-[1.05] tracking-tight ${emOperacao ? 'text-[2rem]' : 'text-[2rem] sm:text-[2.5rem]'}`}>Assistente Criativo</h1>
          <div className={`aurora-rule mt-4 w-16 ${emOperacao ? '' : 'mx-auto'}`} />
          <p className={`mt-4 max-w-2xl text-sm leading-relaxed text-muted-foreground ${emOperacao ? '' : 'mx-auto max-w-md'}`}>{emOperacao ? 'Revise as direções, aprove as peças que quer produzir e avance para escolher os formatos.' : 'Da primeira ideia à peça pronta. Escolha o formato e dê direção à sua próxima campanha.'}</p>
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
        <nav className="mb-6" aria-label="Etapas do Assistente">
          <div className="flex rounded-lg border border-border bg-muted p-1">
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
                    if (v.id === 'briefing' && projectRef) {
                      navegar('/trafego/meta/assistente-criativo?view=briefing');
                      return;
                    }
                    const proxima = new URLSearchParams(busca);
                    proxima.set('view', v.id);
                    setBusca(proxima, { replace: true });
                  }}
                  className={`min-w-0 flex-1 rounded-md px-2 py-2 text-sm font-medium transition-[background-color,color,box-shadow] duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${
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

        {gerando && vista !== 'producao' && vista !== 'assets' && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-4 shadow-card">
            <p role="status" className="flex items-center gap-2 text-sm text-foreground">
              <Loader2 className="h-4 w-4 text-primary motion-safe:animate-spin motion-reduce:animate-none" aria-hidden />
              As imagens desta operação estão em produção.
            </p>
            <Button variant="outline" size="sm" onClick={() => irPara('assets')}>
              Acompanhar geração
            </Button>
          </div>
        )}

        {aviso && (
          <p className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
            {aviso}
          </p>
        )}

        {vista === 'assets' && falhaDaGeracao && falhaDaGeracao.projectRef === projectRef && (
          <p role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {falhaDaGeracao.mensagem}
          </p>
        )}

        <div className="mt-5">
          {vista === 'assets' && <>
            {erroGeracoes && <div role="alert" className="studio-surface"><p className="text-sm text-destructive">Não foi possível atualizar a lista. {erroGeracoes} As imagens já carregadas continuam abaixo.</p><Button variant="outline" className="mt-4" onClick={() => projectRef && void carregarGeracoes(projectRef)}>Tentar novamente</Button></div>}
            <GaleriaDeGeracoes key={projectRef ?? 'sem-operacao'} geracoes={geracoes}
              consultando={lendoGeracoes}
              pedido={gerando && geracaoPendente ? { runRef: geracaoPendente.runRef, geracaoRef: geracaoPendente.geracaoRef, briefings: geracaoPendente.plano.briefings, modelo: geracaoPendente.plano.modelo_de_imagem, qualidade: geracaoPendente.plano.qualidade_de_imagem } : null}
              onConcluida={() => { if (projectRef) void carregarDetalhe(projectRef); }}
              onComecar={() => navegar('/trafego/meta/assistente-criativo?view=briefing')} />
          </>}
          {vista === 'historico' && (
            <HistoricoDeOperacoes
              operacoes={operacoes}
              carregando={carregandoLista}
              erro={erroLista}
              onAbrir={(ref) =>
                navegar(`/trafego/meta/assistente-criativo/${ref}?view=estrategia`)
              }
              onNova={() => navegar('/trafego/meta/assistente-criativo?view=briefing')}
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
                <>
                  {!gerando && geracoes.length > 0 && <section className="studio-surface flex flex-wrap items-center justify-between gap-4">
                    <div className="max-w-xl"><h2 className="text-base font-semibold">Quer outra versão destas peças?</h2><p className="mt-1 text-sm text-muted-foreground">Uma nova geração tem custo próprio. A estratégia aprovada e os arquivos anteriores são preservados.</p></div>
                    <Button type="button" variant="secondary" className="min-h-11" onClick={prepararNovaVersao}>Preparar nova versão</Button>
                  </section>}
                  {!gerando && <FotografiaReal
                    anexo={anexo}
                    modos={capacidades?.modos_de_composicao ?? []}
                    modo={modoDeComposicao}
                    enviando={enviandoFoto}
                    erro={erroDaFoto}
                    onEnviar={(arquivo) => void anexarFoto(arquivo)}
                    onRemover={() => void removerFoto()}
                    onModo={(id) => {
                      setModoDeComposicao(id);
                      // Trocar o modo muda a peça: o plano conferido não
                      // descreve mais o que este clique produziria.
                      setPlano(null);
                    }}
                  />}
                  <PainelDeProducao
                    saida={saida}
                    aprovados={aprovados}
                    capacidades={capacidades}
                    formatosDoBriefing={formatosDoBriefing}
                    anexo={anexo}
                    modoDeComposicao={anexo ? modoDeComposicao : 'sem_foto'}
                    plano={gerando ? geracaoPendente?.plano ?? plano : plano}
                    planejando={planejando}
                    gerando={gerando}
                    erro={erroAcao}
                    onPlanejar={planejar}
                    onGerar={gerar}
                  />
                </>
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
            <FormularioDeBriefing
              ocupado={ocupado}
              erro={erroAcao}
              formatos={capacidades?.formatos ?? []}
              carregandoFormatos={configurado && capacidades === null}
              onEnviar={criar}
            />
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

              {ocupado && <section role="status" className="studio-surface text-center"><Loader2 className="mx-auto h-7 w-7 animate-spin text-primary" aria-hidden /><h2 className="mt-4 font-display text-xl font-semibold">Sua estratégia está sendo preparada</h2><p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">Estamos aguardando o resultado do assistente. A operação já está salva; nenhuma imagem está sendo gerada nesta etapa.</p></section>}
              {carregandoDetalhe && (
                <p role="status" className="text-sm text-muted-foreground">
                  Lendo a operação…
                </p>
              )}

              {!ocupado && !carregandoDetalhe && !saida && runPendente && projectRef && (
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

              {!ocupado && !carregandoDetalhe && !saida && !runPendente && detalhe && (
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

              {detalhe?.operacao.input.contexto_da_pagina && <details className="studio-surface text-sm">
                <summary className="cursor-pointer font-semibold">Contexto da página salvo neste trabalho</summary>
                <p className="mt-3 break-words text-muted-foreground">{detalhe.operacao.input.contexto_da_pagina.titulo}</p>
                <p className="mt-1 break-all text-xs text-muted-foreground">{detalhe.operacao.input.url_destino}</p>
                <p className="mt-3 whitespace-pre-wrap">{detalhe.operacao.input.contexto_do_publico}</p>
                <ul className="mt-3 list-inside list-disc space-y-1">{detalhe.operacao.input.fatos_da_oferta.map(f => <li key={f.ref}>{f.declaracao}</li>)}</ul>
                <p className="mt-3 text-xs text-muted-foreground">Contexto usado na estratégia. A leitura original e suas escolhas permanecem vinculadas ao projeto.</p>
              </details>}
              {saida && runAtual && (
                <PainelDeEstrategia
                  saida={saida}
                  runRef={runAtual.run_ref}
                  aprovados={aprovados}
                  ocupado={ocupado}
                  erro={erroAcao}
                  nomeDaOperacao={detalhe?.operacao?.input?.nome_da_operacao ?? null}
                  onDecidir={decidir}
                  onRefinar={refinar}
                  onContinuar={() => irPara('producao')}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </Moldura>
  );
}
