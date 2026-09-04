/**
 * /trafego/nova/:opportunityId — a Bancada Guiada.
 *
 * ## O que ela substitui
 *
 * A versão anterior não era um wizard e não tinha passos: era uma coluna única
 * de quatro cartões numerados mais quatro blocos avulsos, todos renderizados ao
 * mesmo tempo, com ~15 `useState` planos. O "passo" existia só como decoração no
 * componente `Trilho` — uma `<ol>` de âncoras `#estagio-N` que não controlava o
 * que era exibido. E a numeração nem fechava: `JaNoAr`, `VereditoDePolitica` e
 * `PortaoDePolitica` ficavam ENTRE o cartão 03 e o 04.
 *
 * ## As três réguas que viraram uma
 *
 * A prontidão era recalculada no cliente, em três lugares que discordavam:
 *
 * 1. `const pendencias: string[] = []` montado a cada render, com
 *    `podeLancar = pendencias.length === 0` — e duas regras que eram política
 *    pura do browser ("marcar ao menos uma keyword", "escrever a copy");
 * 2. cada cartão com a sua própria expressão booleana ad-hoc
 *    (`pronto={selecionadas.length > 0}`, `pronto={!!conta?.vinculada}`, …);
 * 3. o trilho do topo, que passava `origem` como literal `true` — sempre verde,
 *    inclusive com o destino BLOQUEADO — e marcava a copy como pronta para
 *    `status: 'running'`, `'error'` e para uma linha `perdida`.
 *
 * Agora existe uma projeção só (`bancada/paradas.ts`), e ela não inventa
 * veredito: lê `Cockpit.bloqueado`/`bloqueios` (que o servidor passou a emitir),
 * o recibo do portão de destino pago, o `status` da copy, o `vinculada` da conta
 * e o `approved_set_sha256` do conjunto pago.
 *
 * ## O que a tela deixou de mandar no corpo
 *
 * As POSITIVAS. `NovaCampanhaPage.tsx:367-381,413` montava
 * `positivas` com `negativa: false` e as enfiava em `criterios` — e
 * `somente_negativas_do_corpo` recusa isso com
 * `CRITERIO_POSITIVO_DO_CORPO_RECUSADO`. O conjunto positivo é o aprovado na
 * mineração; daqui saem apenas as exclusões que o operador declarou.
 *
 * ## Estado na URL, rascunho na aba
 *
 * `?canal=SEARCH&etapa=destino&run=6`. Voltar paradas não perde o rascunho, e o
 * F5 preserva a etapa. O que o operador digitou vive em `sessionStorage`
 * (nenhum segredo, nenhum id de conta); o estado remoto continua sendo
 * autoridade e é sempre relido.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Rocket } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { JaNoAr } from '@/components/trafego/JaNoAr';
import { VereditoDePolitica } from '@/components/trafego/VereditoDePolitica';
import { Lancamento } from '@/components/trafego/Lancamento';
import { ReciboDaBancada } from '@/components/trafego/recibos/ReciboDaBancada';
import type { DesfechoDeclarado } from '@/components/trafego/recibos/ReciboDaBancada';
import {
  MapaDeParadas, PainelDeBloqueio, Pedido,
} from '@/components/trafego/bancada';
import {
  PERGUNTA_DA_PARADA, bloqueiosDoCockpit, faltasDaBancada, paradaAlcancavel,
  primeiraNaoConfirmada, projetarParadas, SEM_PARADA_ATUAL, type FatosDaBancada,
} from '@/components/trafego/bancada/paradas';
import { numeroDigitado, useRascunho } from '@/components/trafego/bancada/useRascunho';
import { ParadaDestino } from '@/components/trafego/bancada/paradas/Destino';
import { ParadaPolitica } from '@/components/trafego/bancada/paradas/Politica';
import { ParadaTermos } from '@/components/trafego/bancada/paradas/Termos';
import { ParadaAnuncio } from '@/components/trafego/bancada/paradas/Anuncio';
import { ParadaEconomia } from '@/components/trafego/bancada/paradas/Economia';
import { ParadaRevisao } from '@/components/trafego/bancada/paradas/Revisao';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import { leituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { idExternoDaCampanha } from '@/lib/trafego/lancamento';
import type { PlanoVigenteResposta } from '@/lib/trafego/portoes';
import { DECORRE_DA_ESTRATEGIA, PARADAS_DA_BANCADA } from '@/types/trafego';
import type {
  Cockpit, CopyGerada, CopyPersistida, CriterioDeKeyword, EstadoDaTrava,
  EstrategiaDeLance, LinhaDoPedido, MatchType, ParadaDaBancada,
  PedidoDeProvaSearch, ReciboDeLancamento, RevisaoDoConjuntoPago, VerticalDePolitica,
} from '@/types/trafego';

/** A etapa pedida na URL, quando ela é uma parada que existe. */
function etapaDaUrl(bruto: string | null): ParadaDaBancada | null {
  if (!bruto) return null;
  return (PARADAS_DA_BANCADA as readonly string[]).includes(bruto)
    ? (bruto as ParadaDaBancada)
    : null;
}

const NovaCampanhaPage: React.FC = () => {
  const { opportunityId } = useParams<{ opportunityId: string }>();
  const [params, setParams] = useSearchParams();
  const runId = Number(params.get('run')) || undefined;
  // ⚠️ `Number(x) || 0` transformava uma URL com id não-numérico em `oid = 0`, e
  // o efeito fazia `if (!oid) return` sem setar erro: a página ficava no
  // esqueleto para sempre, sem uma palavra. Agora a ausência é ausência.
  const oidBruto = Number(opportunityId);
  const oid = Number.isInteger(oidBruto) && oidBruto > 0 ? oidBruto : null;
  const canal = (params.get('canal') || 'SEARCH').toUpperCase();

  // ── estado remoto: o servidor é autoridade de tudo aqui ───────────────────
  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [trava, setTrava] = useState<EstadoDaTrava | null>(null);
  const [verticais, setVerticais] = useState<VerticalDePolitica[]>([]);
  const [copy, setCopy] = useState<CopyPersistida | null>(null);
  const [conjunto, setConjunto] = useState<RevisaoDoConjuntoPago | null>(null);
  const [erroDoConjunto, setErroDoConjunto] = useState<string | null>(null);
  const [plano, setPlano] = useState<PlanoVigenteResposta | null>(null);
  const [planoIndisponivel, setPlanoIndisponivel] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  /**
   * ⚠️ Quem pode FECHAR o próprio recibo.
   *
   * `POST /reconciliar` exige admin (`routers/trafego.py:4442`,
   * `Depends(exigir_admin)`) enquanto todo o resto do fluxo exige apenas
   * usuário. Ou seja: o operador que cria a campanha NÃO fecha o recibo dela.
   *
   * O default é `false` e não `true`: sem leitura de capacidades, esconder o
   * botão e dizer quem pode é melhor que oferecer uma ação que vai voltar 403 —
   * um botão que falha ensina o operador a desconfiar dos que funcionam.
   */
  const [podeReconciliar, setPodeReconciliar] = useState(false);

  // ── estado local: o que o operador está fazendo ───────────────────────────
  const { rascunho, alterar } = useRascunho(oid ?? 0, runId);
  const [escrevendo, setEscrevendo] = useState(false);
  const [aprovando, setAprovando] = useState(false);
  const [lancando, setLancando] = useState(false);
  const [recibo, setRecibo] = useState<ReciboDeLancamento | null>(null);
  /** O desfecho declarado quando NAO houve recibo — 504 indeterminado ou 502
   *  recusado. Ver `DesfechoDeclarado`: e o caso em que os ids mais importam. */
  const [declarado, setDeclarado] = useState<DesfechoDeclarado | null>(null);
  const [campanhaCriada, setCampanhaCriada] = useState<string | null>(null);

  // ── carga ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!oid) { setErro('Esta URL não traz um número de oportunidade válido.'); return; }
    let ativo = true;
    setErro(null);
    void (async () => {
      try {
        const [c, t, v] = await Promise.all([
          pautadorApi.cockpitDeTrafego(oid, { runId }),
          // ⚠️ Estas duas engolem a falha de propósito e viram valor NEUTRO, não
          // permissivo: sem trava lida a tela assume fechada; sem verticais
          // lidas a política fica indeterminada, que não abre nada.
          pautadorApi.estadoDaTrava().catch(() => null),
          pautadorApi.verticaisEPortoes().catch(() => ({ verticais: [] })),
        ]);
        if (!ativo) return;
        setCockpit(c);
        setTrava(t);
        setVerticais(v.verticais);
      } catch (e) {
        if (ativo) setErro(e instanceof Error ? e.message : 'Não deu para ler esta oportunidade.');
      }
    })();
    return () => { ativo = false; };
  }, [oid, runId]);

  // A copy, lida ao abrir. É o que faz sair da página e voltar não jogar fora
  // ~174 s de LLM pago — inclusive num browser fechado e reaberto.
  const lerCopy = useCallback(async () => {
    if (!oid) return;
    try {
      const r = await pautadorApi.lerCopy(oid, runId ?? null);
      setCopy('existe' in r && r.existe ? r : null);
    } catch { /* a parada Anúncio já mostra "não escrito" */ }
  }, [oid, runId]);

  useEffect(() => { void lerCopy(); }, [lerCopy]);

  // Enquanto a escrita corre no servidor, relê. A escrita sobrevive a fechar a
  // aba, então o polling é sobre estado remoto, não sobre uma promessa local.
  useEffect(() => {
    if (copy?.status !== 'running') return;
    const t = setInterval(() => { void lerCopy(); }, 4000);
    return () => clearInterval(t);
  }, [copy?.status, lerCopy]);

  const lerConjunto = useCallback(async () => {
    if (!oid) return;
    try {
      setConjunto(await pautadorApi.revisarConjuntoPago(oid, runId ?? null));
      setErroDoConjunto(null);
    } catch (e) {
      setConjunto(null);
      setErroDoConjunto(e instanceof Error
        ? e.message
        : 'Não deu para ler o conjunto pago desta oportunidade.');
    }
  }, [oid, runId]);

  useEffect(() => { void lerConjunto(); }, [lerConjunto]);

  // As capacidades desta sessão. Só é lida quando existe recibo para fechar —
  // antes disso a resposta não muda nada na tela.
  useEffect(() => {
    if (!recibo && !declarado) return;
    let ativo = true;
    void pautadorApi.capacidades()
      .then((c) => { if (ativo) setPodeReconciliar(Boolean(c.is_admin)); })
      .catch(() => { if (ativo) setPodeReconciliar(false); });
    return () => { ativo = false; };
  }, [recibo, declarado]);

  // O plano gravado da conta. Zero rede ao Google — ver o comentário do cliente.
  useEffect(() => {
    const c = cockpit?.conta;
    if (!c?.customer_id || !c.login_customer_id) {
      if (cockpit) setPlanoIndisponivel(
        'Os portões dependem da conta, e este projeto ainda não tem conta vinculada.');
      return;
    }
    let ativo = true;
    setPlanoIndisponivel(null);
    void pautadorApi.planoDeMensuracaoVigente(c.customer_id, c.login_customer_id)
      .then((p) => { if (ativo) setPlano(p); })
      .catch((e) => {
        if (!ativo) return;
        setPlanoIndisponivel(e instanceof Error
          ? `Não deu para ler o plano gravado desta conta: ${e.message}`
          : 'Não deu para ler o plano gravado desta conta.');
      });
    return () => { ativo = false; };
  }, [cockpit]);

  // ── projeção ──────────────────────────────────────────────────────────────
  const destino = useMemo(
    () => leituraDoDestinoPago(cockpit?.origem as unknown, {
      status_wp: cockpit?.origem?.status_wp,
      exige_ponto_de_campanha: true,
    }),
    [cockpit],
  );

  const orcamento = numeroDigitado(rascunho.orcamento);
  const lance = numeroDigitado(rascunho.lance);
  const estrategia = rascunho.estrategia as EstrategiaDeLance;

  const fatos: FatosDaBancada = useMemo(() => ({
    cockpit, destino, conjunto, copy, verticais, orcamento, lance,
    certificacoes: rascunho.certificacoes,
  }), [cockpit, destino, conjunto, copy, verticais, orcamento, lance,
       rascunho.certificacoes]);

  const faltas = useMemo(() => faltasDaBancada(fatos), [fatos]);
  const bloqueios = useMemo(() => bloqueiosDoCockpit(cockpit), [cockpit]);

  const etapaPedida = etapaDaUrl(params.get('etapa'));
  // ⚠️ SEM viés de `atual`. Projetar com uma parada promovida a `atual` faria
  // `primeiraNaoConfirmada` devolver justamente essa parada — e a entrada sem
  // `?etapa` ficaria presa na primeira para sempre.
  const paradasSemAtual = useMemo(
    () => projetarParadas(fatos, SEM_PARADA_ATUAL), [fatos]);
  /**
   * ⚠️ A ETAPA É DERIVADA UMA VEZ E FIXADA. Derivá-la a cada render corrompia
   * dinheiro.
   *
   * O único caminho de entrada não traz `?etapa`
   * (`QuadroDeOportunidades.tsx:339` linka `/trafego/nova/:id?run=:run`), e com
   * ela ausente `etapa` virava função de `fatos` — que inclui `orcamento` e
   * `lance`, vindos do rascunho, atualizados a cada TECLA.
   *
   * Consequência medida: o operador na parada Economia digita "50" no orçamento.
   * No primeiro caractere, "5", `faltasDaParada('economia')` esvazia,
   * `primeiraNaoConfirmada` passa a devolver `'revisao'`, e `<ParadaEconomia>`
   * DESMONTA no meio da digitação. Fica gravado `orcamento: '5'` — e é esse 5
   * que entra em `budget_diario`. A Revisão que sobe no lugar já mostra "Provar
   * contra a conta" habilitado, porque a régua considera a economia completa.
   *
   * Havia ainda o efeito visível na carga: cockpit, conjunto e copy chegam em
   * efeitos separados, e o painel central trocava sozinho até três vezes.
   *
   * A correção fixa a parada de entrada assim que o cockpit aterrissa e a
   * escreve na URL — que passa a ser a autoridade, como o cabeçalho deste
   * arquivo já prometia.
   */
  const [etapaFixada, setEtapaFixada] = useState<ParadaDaBancada | null>(null);
  const etapa: ParadaDaBancada =
    etapaPedida ?? etapaFixada ?? primeiraNaoConfirmada(paradasSemAtual);

  useEffect(() => {
    // Só depois do cockpit: antes dele TODAS as paradas são `indeterminada`, e
    // fixar aí prenderia o operador em `destino` para sempre.
    if (etapaPedida || etapaFixada || !cockpit) return;
    const p = primeiraNaoConfirmada(paradasSemAtual);
    setEtapaFixada(p);
    const q = new URLSearchParams(params);
    q.set('canal', canal);
    q.set('etapa', p);
    setParams(q, { replace: true });
  }, [etapaPedida, etapaFixada, cockpit, paradasSemAtual, params, canal, setParams]);
  const paradas = useMemo(() => projetarParadas(fatos, etapa), [fatos, etapa]);

  const hrefDaParada = useCallback((p: ParadaDaBancada) => {
    const q = new URLSearchParams(params);
    q.set('canal', canal);
    q.set('etapa', p);
    return `?${q.toString()}`;
  }, [params, canal]);

  // Uma parada bloqueada na URL não abre: o operador cai na primeira alcançável.
  useEffect(() => {
    const alvo = paradas.find((p) => p.parada === etapa);
    if (alvo && !paradaAlcancavel(alvo)) {
      const q = new URLSearchParams(params);
      q.set('etapa', primeiraNaoConfirmada(paradas));
      setParams(q, { replace: true });
    }
  }, [paradas, etapa, params, setParams]);

  // ── o Pedido ──────────────────────────────────────────────────────────────
  const linhasDoPedido: LinhaDoPedido[] = useMemo(() => {
    const c = cockpit?.conta;
    const brl = (n: number | null) => (n == null ? null : `R$ ${n.toFixed(2).replace('.', ',')}`);
    return [
      { rotulo: 'conta', valor: c?.customer_id ?? null, fonte: 'o projeto' },
      { rotulo: 'canal', valor: canal, fonte: 'esta rota' },
      { rotulo: 'destino', valor: cockpit?.origem?.url_final ?? null, fonte: 'o funil' },
      {
        rotulo: 'conjunto',
        valor: conjunto ? `${conjunto.selecionadas.length} positivas` : null,
        fonte: conjunto?.approved_set_sha256 ? 'a mineração, aprovado' : 'a mineração',
      },
      {
        rotulo: 'anúncio',
        valor: copy?.status === 'done' && copy.copy
          ? `${copy.copy.headlines.length} títulos · ${copy.copy.descriptions.length} descrições`
          : null,
        fonte: 'a escrita',
      },
      { rotulo: 'orçamento diário', valor: brl(orcamento), fonte: 'você, agora' },
      {
        rotulo: 'pode servir até',
        valor: orcamento == null ? null : `R$ ${(orcamento * 2).toFixed(2).replace('.', ',')} no dia`,
        fonte: 'regra do Google, não teto garantido',
      },
      { rotulo: 'lance inicial', valor: brl(lance), fonte: 'você, agora' },
      { rotulo: 'estratégia', valor: estrategia, fonte: 'você, agora' },
      { rotulo: 'estado ao nascer', valor: 'PAUSED', fonte: 'a política do canário' },
      // ⚠️ O fato que impede um lançamento duplicado. Medido em 19/08/2026: a
      // campanha existia no Google Ads e as duas telas seguiam oferecendo
      // "Lançar campanha" como se nada tivesse acontecido. Duas campanhas do
      // mesmo funil competem entre si no mesmo leilão.
      {
        rotulo: 'campanhas deste funil já no ar',
        // `null` quando não há nenhuma: a linha some para "—", que é a leitura
        // certa de "nada existe ainda" — e não um "0" que soa como medição.
        valor: (cockpit?.campanhas_lancadas ?? []).length
          ? String((cockpit?.campanhas_lancadas ?? []).length)
          : null,
        fonte: 'a conta',
      },
    ];
  }, [cockpit, canal, conjunto, copy, orcamento, lance, estrategia]);

  const proximoAto = useMemo(() => {
    if (faltas.length > 0) return `Resolver: ${faltas[0].texto}.`;
    return 'Provar o pedido contra a conta. A prova não cria nada.';
  }, [faltas]);

  // ── o pedido que vai para /provar e /subir ────────────────────────────────
  //
  // ⚠️ SEM POSITIVAS. `criterios` leva SÓ as negativas que o operador declarou.
  // O conjunto positivo é o aprovado na mineração, e `somente_negativas_do_corpo`
  // recusa qualquer critério com `negativa: false`.
  // ⚠️ As exclusões vêm INTEIRAS do rascunho — com a correspondência e o motivo
  // que o operador declarou. A primeira versão desta página as remontava a
  // partir de `string[]` com `match_type: 'PHRASE'` fixo, e perdia as duas
  // coisas: excluir `simulador` em EXACT bloqueia um termo e em PHRASE bloqueia
  // uma família, e o motivo é o que responde "por que este termo está fora?"
  // três meses depois.
  //
  // O filtro é uma guarda, não uma conversão: se algo positivo entrasse aqui, o
  // servidor recusaria com `CRITERIO_POSITIVO_DO_CORPO_RECUSADO`, e é melhor a
  // tela nunca montar esse pedido do que descobrir no 409.
  const negativas: CriterioDeKeyword[] = useMemo(
    () => rascunho.negativas.filter((c) => c.negativa),
    [rascunho.negativas],
  );

  /**
   * ⚠️ MEMOIZADO, E ISSO NÃO É OTIMIZAÇÃO — É SEGURANÇA.
   *
   * `pedido` é prop de `<Lancamento>`. Lá dentro, `provar` é um `useCallback`
   * com deps `[pedido, trava, destino]`, e existe
   * `useEffect(() => { void provar(); }, [provar])`.
   *
   * Um objeto literal recriado a cada render dá identidade nova a cada render →
   * `provar` muda de identidade → o efeito dispara de novo. Ou seja: QUALQUER
   * re-render da página com o modal aberto rodava `POST /provar` outra vez — a
   * chamada mais lenta e mais cara do fluxo — e, pior, `provar()` começa com
   * `setEstado('provando')`: a escada VOLTAVA para o começo.
   *
   * O caminho concreto que isto fecha: `setRecibo` dispara o efeito de
   * capacidades, que faz `setPodeReconciliar`, que re-renderiza a página logo
   * DEPOIS da criação — e a máquina saía de `criada` para `provando`, apagando
   * da tela o recibo da campanha que acabou de nascer.
   *
   * As deps abaixo são exatamente o que compõe o payload. Nada de `cockpit`
   * inteiro: ele muda por releitura e não mudaria o pedido.
   */
  const temCockpit = cockpit !== null;
  const pedido: PedidoDeProvaSearch | null = useMemo(() => (
    (cockpit && oid && orcamento != null && lance != null)
      ? {
        opportunity_id: oid,
        run_id: runId ?? null,
        customer_id: cockpit.conta?.customer_id ?? '',
        login_customer_id: cockpit.conta?.login_customer_id ?? '',
        // ⚠️ Vazio de propósito: as positivas vêm do conjunto aprovado, no
        // servidor. `keywords_por_grupo(<conjunto aprovado>)` é quem as monta.
        grupos: [],
        copy: copy?.copy ?? null,
        budget_diario: orcamento,
        cpc_inicial: lance,
        rede: { google_search: true, search_partners: false, display_expansion: false },
        match_type: DECORRE_DA_ESTRATEGIA[estrategia].match_type,
        criterios: negativas,
        keywords_fora: rascunho.keywordsFora,
        canal: 'SEARCH' as const,
        estrategia_lance: estrategia,
        graduacao_em_conversoes: estrategia === 'MANUAL_CPC' ? rascunho.graduacao : 0,
        meta_conversao_id: cockpit.conta?.meta_conversao?.primaria?.id ?? null,
        vertical: rascunho.vertical || cockpit.origem?.vertical,
        certificacoes: rascunho.certificacoes,
        url_final: cockpit.origem?.url_final,
      }
      : null
  ), [
    // ⚠️ NUNCA `cockpit` INTEIRO nesta lista.
    //
    // `onCriada` relê o cockpit depois da criação — objeto novo, mesma
    // informação. Com `cockpit` aqui, essa releitura daria identidade nova ao
    // pedido e re-dispararia `/provar` justamente no instante em que a campanha
    // acabou de nascer, apagando o recibo da tela. Só os campos que o payload
    // de fato usa entram, e todos são primitivos: identidade estável.
    temCockpit,
    cockpit?.conta?.customer_id, cockpit?.conta?.login_customer_id,
    cockpit?.conta?.meta_conversao?.primaria?.id, cockpit?.origem?.vertical,
    cockpit?.origem?.url_final, oid, runId, orcamento, lance,
    copy?.copy, negativas, estrategia, rascunho.keywordsFora, rascunho.graduacao,
    rascunho.vertical, rascunho.certificacoes,
  ]);

  // ── atos ──────────────────────────────────────────────────────────────────
  const aprovarConjunto = async (motivo: string) => {
    if (!oid || !conjunto || aprovando) return;
    setAprovando(true);
    try {
      await pautadorApi.aprovarConjuntoPago({
        opportunity_id: oid, run_id: runId ?? null,
        hash_conferido: conjunto.selected_set_sha256, motivo,
      });
      await lerConjunto();
    } catch (e) {
      setErroDoConjunto(e instanceof PautadorApiError
        ? e.message
        : 'A aprovação do conjunto falhou.');
    } finally {
      setAprovando(false);
    }
  };

  const escreverCopy = async () => {
    if (!oid || !conjunto || escrevendo) return;
    setEscrevendo(true);
    try {
      await pautadorApi.escreverCopy({
        opportunity_id: oid,
        run_id: runId ?? null,
        // As keywords da copy saem do conjunto aprovado — a mesma fonte do
        // pedido. Duas listas produziriam um anúncio ancorado noutros termos.
        keywords: conjunto.selecionadas.map((k) => k.termo),
        match_type: DECORRE_DA_ESTRATEGIA[estrategia].match_type,
        vertical: rascunho.vertical || cockpit?.origem?.vertical || null,
        certificacoes: rascunho.certificacoes,
        modelo: rascunho.modeloDaCopy || null,
        url_final: cockpit?.origem?.url_final ?? null,
      });
      await lerCopy();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'A escrita da copy falhou.');
    } finally {
      setEscrevendo(false);
    }
  };

  const salvarCopyEditada = async (c: CopyGerada) => {
    if (!oid) return;
    setCopy((a) => (a ? { ...a, copy: c } : a));
    try {
      await pautadorApi.salvarCopyEditada({ opportunity_id: oid, run_id: runId ?? null, copy: c });
    } catch { await lerCopy(); }
  };

  // ── render ────────────────────────────────────────────────────────────────
  const titulo = cockpit?.origem?.nicho || (oid ? `oportunidade ${oid}` : 'oportunidade');
  const lancadas = cockpit?.campanhas_lancadas ?? [];
  const paradasAplicaveis = paradas.filter((p) => p.estado !== 'nao_se_aplica');
  const indiceDaEtapa = Math.max(0, paradasAplicaveis.findIndex((p) => p.parada === etapa));

  if (erro && !cockpit) {
    return (
      <Layout>
        <div className="mx-auto max-w-3xl px-4 py-10 md:px-6">
          <Link to="/trafego" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" aria-hidden /> Voltar ao Hub
          </Link>
          <div role="alert"
               className="mt-6 rounded-lg border border-destructive/40 bg-destructive/[0.06] p-5 text-sm leading-6 text-foreground">
            {erro}
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="bancada-shell mx-auto max-w-[1480px] px-4 pb-24 pt-4 md:px-6 md:pt-6">
        <section className="bancada-command-deck">
          <div className="bancada-command-topline" aria-hidden />
          <header className="bancada-command-header">
            <div className="min-w-0">
              <Link to="/trafego" className="bancada-back-link">
                <ArrowLeft className="h-4 w-4" aria-hidden /> Central de tráfego
              </Link>
              <div className="mt-5 flex items-center gap-2">
                <span className="bancada-command-icon">
                  <Rocket className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="kicker text-slate-400">Missão de lançamento · {canal}</span>
              </div>
              <h1 className="mt-2 max-w-[22ch] font-display text-[2rem] font-bold leading-[1.02] tracking-[-0.035em] text-white text-balance md:text-[2.75rem]">
                {titulo}
              </h1>
            </div>
            <div className="bancada-safety-contract">
              <span className="bancada-safety-dot" aria-hidden />
              <div>
                <p className="font-semibold text-white">Criação segura</p>
                <p>A campanha nasce pausada</p>
              </div>
            </div>
          </header>

          <MapaDeParadas paradas={paradas} atual={etapa} hrefDaParada={hrefDaParada} />
        </section>

        <div className="bancada-grid mt-6 grid gap-6">
          <main className="bancada-stage min-w-0">
            <header className="bancada-stage-header">
              <div>
                <p className="kicker text-primary">
                  Etapa {indiceDaEtapa + 1} de {paradasAplicaveis.length}
                </p>
                <h2 className="mt-2 max-w-[30ch] font-display text-2xl font-semibold leading-tight tracking-tight text-foreground text-balance md:text-[2rem]">
                  {PERGUNTA_DA_PARADA[etapa]}
                </h2>
              </div>
              <p className="bancada-stage-hint">
                Decida uma coisa por vez. Evidências técnicas ficam disponíveis sem disputar sua atenção.
              </p>
            </header>

            <div className="space-y-5 p-4 md:p-6">

            {/* Os bloqueios do servidor ficam PERTO da decisão, e não no rodapé.
                Fora da Revisão, que já os desenha por dentro. */}
            {etapa !== 'revisao' && (
              <PainelDeBloqueio bloqueios={bloqueios} lidoEm={cockpit?.lido_em ?? null} />
            )}

            {!cockpit ? (
              <p className="text-sm text-muted-foreground">Lendo a oportunidade…</p>
            ) : etapa === 'destino' ? (
              <ParadaDestino cockpit={cockpit} destino={destino} />
            ) : etapa === 'politica' ? (
              <ParadaPolitica
                cockpit={cockpit} verticais={verticais}
                vertical={rascunho.vertical} onVertical={(v) => alterar('vertical', v)}
                certificacoes={rascunho.certificacoes}
                onCertificacoes={(c) => alterar('certificacoes', c)}
              />
            ) : etapa === 'termos' ? (
              <ParadaTermos
                cockpit={cockpit}
                conjunto={conjunto}
                erroDoConjunto={erroDoConjunto}
                aprovando={aprovando}
                onAprovar={aprovarConjunto}
                matchPadrao={DECORRE_DA_ESTRATEGIA[estrategia].match_type as MatchType}
                permitirBroadPositivo={estrategia === 'MAXIMIZE_CONVERSIONS'}
                matchPorKeyword={rascunho.matchPorKeyword as Record<string, MatchType>}
                onMatchPorKeyword={(m) => alterar('matchPorKeyword', m)}
                negativas={negativas}
                // Guarda o que a mesa devolveu, INTEIRO. Reconstruir aqui é o
                // que perdia correspondência e motivo — ver o ⚠️ de `negativas`.
                onNegativas={(n) => alterar('negativas', n)}
              />
            ) : etapa === 'anuncio' ? (
              <ParadaAnuncio
                copy={copy}
                escrevendo={escrevendo || copy?.status === 'running'}
                podeEscrever={Boolean(conjunto?.approved_set_sha256) && !escrevendo}
                motivoBloqueio={conjunto?.approved_set_sha256
                  ? ''
                  : 'Aprove o conjunto positivo antes de escrever: a copy ancora nos termos.'}
                onEscrever={() => void escreverCopy()}
                onEditar={(c) => void salvarCopyEditada(c)}
                modelo={rascunho.modeloDaCopy}
                onModelo={(m) => alterar('modeloDaCopy', m)}
              />
            ) : etapa === 'economia' ? (
              <ParadaEconomia
                cockpit={cockpit}
                plano={plano}
                planoIndisponivel={planoIndisponivel}
                orcamento={orcamento}
                lance={lance}
                estrategia={estrategia}
                orcamentoBruto={rascunho.orcamento}
                onOrcamento={(v) => alterar('orcamento', v)}
                lanceBruto={rascunho.lance}
                onLance={(v) => alterar('lance', v)}
                onEstrategia={(e) => alterar('estrategia', e)}
                graduacao={rascunho.graduacao}
                onGraduacao={(g) => alterar('graduacao', g)}
              />
            ) : (
              <ParadaRevisao
                linhas={linhasDoPedido}
                faltas={faltas.map((f) => f.texto)}
                bloqueios={bloqueios}
                lidoEm={cockpit.lido_em ?? null}
                travaFechada={!trava?.env_presente}
                explicacaoDaTrava={trava?.explicacao ?? null}
                onProvar={() => setLancando(true)}
              />
            )}

            {/* O recibo FICA. Ele não morre quando a escada fecha. */}
            {(recibo || declarado) && (
              <ReciboDaBancada
                recibo={recibo}
                declarado={declarado}
                customerId={cockpit?.conta?.customer_id ?? null}
                canal={canal}
                podeReconciliar={podeReconciliar
                  && Boolean(recibo?.ledger?.item_id ?? declarado?.item_id)}
                onReconciliar={() => {
                  const item = recibo?.ledger?.item_id ?? declarado?.item_id;
                  const conta = recibo?.customer_id || cockpit?.conta?.customer_id;
                  if (!item || !conta) return;
                  const idExterno = recibo ? (idExternoDaCampanha(recibo) || null) : null;
                  void pautadorApi.reconciliarLancamento({
                    item_id: item,
                    customer_id: conta,
                    // ⚠️ SEM `campaign_id`, A `marca` É OBRIGATÓRIA.
                    //
                    // `ReconciliarEntrada` aceita os dois como opcionais, mas o
                    // validador do backend recusa o corpo em que NENHUM dos dois
                    // vem — e o caso que mais precisa desta rota é justamente o
                    // que não tem id externo, porque a chamada nunca respondeu.
                    // A marca é derivada do plano aprovado e estável entre
                    // tentativas: `VOLC-CANARY-<impressao[:12]>`.
                    campaign_id: idExterno,
                    marca: idExterno ? null : (declarado?.marca ?? null),
                  })
                    .then(() => {
                      if (oid) {
                        void pautadorApi.cockpitDeTrafego(oid, { runId })
                          .then(setCockpit).catch(() => {});
                      }
                    })
                    .catch((e) => setErro(e instanceof Error
                      ? e.message
                      : 'A reconciliação não pôde ser feita.'));
                }}
              />
            )}

            {lancadas.length > 0 && (
              <JaNoAr campanhas={lancadas} onVerVeredito={(id) => setCampanhaCriada(id)} />
            )}

            {campanhaCriada && cockpit.conta?.customer_id && (
              <VereditoDePolitica
                customerId={cockpit.conta.customer_id}
                campaignId={campanhaCriada}
              />
            )}
            </div>
          </main>

          <Pedido
            linhas={linhasDoPedido}
            faltas={faltas.map((f) => f.texto)}
            proximoAto={proximoAto}
            lidoEm={cockpit?.lido_em ?? null}
          />
        </div>
      </div>

      {lancando && pedido && (
        <Lancamento
          pedido={pedido}
          trava={trava}
          titulo={titulo}
          destino={destino}
          resumoDaCopy={copy?.copy
            ? `${copy.copy.headlines.length} títulos · ${copy.copy.descriptions.length} descrições`
            : 'sem copy'}
          onFechar={() => setLancando(false)}
          onCriada={(id) => {
            setCampanhaCriada(id);
            if (oid) void pautadorApi.cockpitDeTrafego(oid, { runId }).then(setCockpit).catch(() => {});
          }}
          onRecibo={setRecibo}
          onDesfechoDeclarado={(d) => setDeclarado({
            estado: d.estado === 'recusado' ? 'recusado' : 'indeterminado',
            mensagem: d.mensagem,
            recibo_id: d.recibo_id,
            item_id: d.item_id,
            erro_codigo: 'erro_codigo' in d ? d.erro_codigo : null,
            request_id: 'request_id' in d ? d.request_id : null,
            marca: d.marca,
          })}
        />
      )}
    </Layout>
  );
};

export default NovaCampanhaPage;
