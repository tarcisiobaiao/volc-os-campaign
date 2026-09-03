/**
 * /trafego/nova/:opportunityId — o cockpit de lançamento.
 *
 * ## Continua não sendo um wizard, e agora tem um trilho
 *
 * O operador usa isto poucas vezes por semana, não memoriza nada e está prestes
 * a gastar dinheiro real: ele precisa VER o tamanho do trabalho, não descobrir
 * na próxima etapa. O que faltava não era esconder — era dizer onde ele está. O
 * trilho fixo no topo resolve isso sem partir a página em passos.
 *
 * ## O que mudou, e por quê (medido na versão anterior)
 *
 * | defeito | conserto |
 * |---|---|
 * | 23 linhas de keyword com peso idêntico | a régua sobe para o topo do cartão; a lista vira detalhe |
 * | "73% do volume está em 1 termo" era rodapé a 5.700px do topo | virou a primeira coisa do cartão de keywords |
 * | 6 avisos com tratamento igual | separados por severidade; o que barra o lançamento fica em cima |
 * | ação real numa coluna de 320px, botão nascendo morto | barra fixa no topo, com o que falta escrito |
 * | linguagem visual de outro produto | `card-volc`, badges e aurora — a mesma de Integrações |
 *
 * ## As travas são binárias, e quem as declara é o servidor
 *
 * A versão anterior tinha um `Set(['LP_EM_RASCUNHO','URL_PROVISORIA'])` aqui
 * dentro: o cliente escolhia quais códigos barravam. Qualquer código de
 * política que não estivesse na lista virava observação recolhida enquanto
 * `podeLancar` seguia verdadeiro — e a lista nunca cresceu junto com as regras.
 * Agora a decisão é do servidor por duas vias: a severidade do aviso (não
 * reconhecida BARRA, ver `avisoBarraOLancamento`) e o recibo do portão de
 * destino pago.
 *
 * O caso concreto continua barrando pelo mesmo motivo de sempre: a campanha
 * nasce pausada e não gasta, mas nasce apontando para `?post_type=r&p=2152`, e
 * quando a página for publicada o permalink muda — sobra uma campanha com
 * destino errado cuja falha some de vista. Só que quem diz isso agora é o
 * estado da publicação lido do WordPress, não uma lista de códigos no browser.
 *
 * ## O verde que este arquivo parou de pintar
 *
 * Medido nesta linha, na versão anterior:
 *
 * ```ts
 * estado={status_wp === 'draft' ? 'LP em rascunho' : 'LP no ar'}
 * pronto={status_wp !== 'draft'}
 * ```
 *
 * `status_wp` é `string | null`, e `null` significa "o servidor NUNCA leu o
 * WordPress". As duas linhas transformavam esse "ninguém leu" em "LP no ar" com
 * a etapa marcada como pronta. Agora o cartão lê a prontidão do destino, e
 * ausência de leitura é INDETERMINADO — que não abre nada.
 */
import React, { useEffect, useMemo, useState, useRef } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, ArrowLeft, Check, ChevronDown, Info, Lock, Rocket,
} from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CartaoCopy } from '@/components/trafego/CartaoCopy';
import { MesaDeLance } from '@/components/trafego/MesaDeLance';
import { JaNoAr } from '@/components/trafego/JaNoAr';
import { PortaoDePolitica } from '@/components/trafego/PortaoDePolitica';
import { VereditoDePolitica } from '@/components/trafego/VereditoDePolitica';
import { PainelDoLancamento } from '@/components/trafego/PainelDoLancamento';
import { Lancamento } from '@/components/trafego/Lancamento';
import { ListaDeKeywords } from '@/components/trafego/ListaDeKeywords';
import { ReguaDeLeilao, achatar } from '@/components/trafego/ReguaDeLeilao';
import { MesaDeCriterios } from '@/components/trafego/MesaDeCriterios';
import {
  FaixaDoDestinoPago, PainelDoDestinoPago,
} from '@/components/landing-policy/PainelDoDestinoPago';
import { pautadorApi } from '@/lib/pautadorApi';
import {
  avisoBarraOLancamento, leituraDoDestinoPago, pendenciasDoDestino, resumoDoDestino,
} from '@/lib/landing-policy/prontidao';
import { chave } from '@/lib/trafego/criterios';
import { cn } from '@/lib/utils';
import { DECORRE_DA_ESTRATEGIA } from '@/types/trafego';
import type {
  AvisoDoCockpit, Cockpit, CopyGerada, CopyPersistida, CriterioDeKeyword,
  EstadoDaTrava, EstrategiaDeLance, GrupoCandidato, MatchType,
  PedidoDeProvaSearch, VerticalDePolitica,
} from '@/types/trafego';

const chaveDe = (grupo: string, texto: string) => `${grupo}:${texto}`;

/** ⚠️ O cliente não decide mais o que barra — ver o cabeçalho. A severidade vem
 *  do servidor e a regra é fail-closed: só `informacao` e `atencao` passam. */
const barra = (a: AvisoDoCockpit) => avisoBarraOLancamento(a.severidade);

const NovaCampanhaPage: React.FC = () => {
  const { opportunityId } = useParams<{ opportunityId: string }>();
  const [params] = useSearchParams();
  const runId = Number(params.get('run')) || undefined;
  const oid = Number(opportunityId) || 0;

  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [trava, setTrava] = useState<EstadoDaTrava | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());

  // ── as palavras, tipadas ───────────────────────────────────────────────────
  // As POSITIVAS não moram aqui: são derivadas de `gruposEscolhidos` a cada
  // render, dentro da mesa. Guardar uma cópia delas em estado deixaria um
  // critério órfão apontando para uma keyword desmarcada, e o `Brief` recusa o
  // pedido inteiro quando o contrato tipado não cobre a estrutura.
  //
  // O que mora aqui é só o que o operador ESCREVEU: o match type que ele trocou
  // (por keyword) e as exclusões que ele declarou.
  const [matchPorKeyword, setMatchPorKeyword] = useState<Record<string, MatchType>>({});
  const [negativas, setNegativas] = useState<CriterioDeKeyword[]>([]);

  const [budget, setBudget] = useState('10');
  const [lance, setLance] = useState('0.12');
  // Como a campanha nasce. MANUAL_CPC é o padrão da casa — ver
  // docs/SPEC-FRONT-CAMPANHAS.md §1. `graduacao` só REGISTRA a regra que o
  // motor de gestão vai executar; este lançamento não vigia a conta.
  const [estrategia, setEstrategia] = useState<EstrategiaDeLance>('MANUAL_CPC');
  const [graduacao, setGraduacao] = useState(30);
  // Vazio = o modelo do ambiente. Existe para comparar; ver MODELOS_DE_COPY.
  const [modeloDaCopy, setModeloDaCopy] = useState('');
  // A vertical é decisão de FATO sobre o negócio, e ela decide se o portão de
  // habilitação barra o lançamento. Chegava fixa da entidade; agora o operador
  // responde. Ver PortaoDePolitica.tsx para o porquê.
  const [verticais, setVerticais] = useState<VerticalDePolitica[]>([]);
  const [vertical, setVertical] = useState<string>('');
  const [certificacoes, setCertificacoes] = useState<string[]>([]);

  const [escrita, setEscrita] = useState<CopyPersistida | null>(null);
  const [lancando, setLancando] = useState(false);
  // O id da campanha que ACABOU de nascer. Enquanto `campaigns` não é gravada
  // no `/subir`, é o recibo que carrega esse id — e é ele que permite ler o
  // veredito de política sem sair da tela.
  const [campanhaCriada, setCampanhaCriada] = useState<string | null>(null);
  // A conta da campanha escolhida no cartão "já no ar" — pode ser outra que não
  // a vinculada ao projeto, se a campanha for antiga.
  const [contaDoVeredito, setContaDoVeredito] = useState<string | null>(null);

  // ⚠️ `escrevendo` DERIVA da linha do banco, e não de um `useState` local.
  //
  // A versão anterior guardava o resultado só na memória do browser: sair da
  // página descartava ~174 s de LLM pago, sem linha, sem log, sem sinal de que
  // tinha rodado — o operador voltava e via o botão de novo. Agora quem sabe se
  // está escrevendo é o servidor, e a tela pergunta.
  const escrevendo = escrita?.status === 'running' && !escrita.perdida;

  useEffect(() => {
    if (!oid) return;
    let ativo = true;
    Promise.all([
      pautadorApi.cockpitDeTrafego(oid, { runId }),
      pautadorApi.estadoDaTrava().catch(() => null),
      pautadorApi.verticaisEPortoes().catch(() => ({ verticais: [] })),
    ])
      .then(([c, t, v]) => {
        if (!ativo) return;
        setCockpit(c);
        setTrava(t);
        setVerticais(v.verticais);
        // O padrão é o que a entidade classificou — mudar é ato deliberado.
        setVertical(c.origem.vertical);
        // Pré-marca o que a mineração aprovou. A triagem já foi feita por quem
        // tinha os dados; começar do zero jogaria fora esse trabalho.
        setMarcadas(new Set(
          c.grupos.flatMap((g) => g.keywords.map((k) => chaveDe(g.tipo, k.texto)))));
      })
      .catch((e) => ativo && setErro(e instanceof Error ? e.message : 'Falhei ao ler o cockpit.'));
    return () => { ativo = false; };
  }, [oid, runId]);

  const selecionadas = useMemo(
    () => (cockpit ? achatar(cockpit.grupos, marcadas) : []), [cockpit, marcadas]);

  // ⚠️ UM CONJUNTO. A sub-intenção continua sendo a lente da TRIAGEM — ela é
  // como o operador enxerga e marca as keywords —, mas NÃO vira ad group.
  //
  // A doutrina fechada em 19/08/2026 é campanha = rei: um termo, uma campanha,
  // um conjunto (docs/SPEC-ARBITRAGEM.md P7). A razão é de mecânica: orçamento
  // é da CAMPANHA (`campaignBudgets`) e lance é do ad group. Separar em N
  // grupos não separa verba — só divide o aprendizado do RSA pela metade, e com
  // R$ 30/dia nenhum dos dois amadurece.
  //
  // O que o Google recomenda hoje é consolidar em grupos temáticos, não
  // fragmentar; o SKAG morreu. Ver docs/SPEC-FRONT-CAMPANHAS.md §1.
  // ⚠️ A tela continua mandando os grupos da TRIAGEM, e isso é deliberado.
  //
  // A consolidação em um ad group é DOUTRINA DO SISTEMA, e mora no backend
  // (`Escolha.conjunto_unico`), não aqui. A primeira tentativa foi consolidar
  // no front, mandando um grupo com o nome do nicho — e a ponte recusou com
  // "grupos inexistentes no cockpit", porque ela valida o tipo contra a
  // triagem antes de montar o brief. Estava certa em recusar: o front não pode
  // inventar um grupo que a mineração não produziu.
  //
  // Aqui a lista diz QUAIS keywords foram marcadas, agrupadas como o operador
  // as enxergou. Quantos ad groups isso vira é decisão de quem monta o payload.
  const gruposEscolhidos = useMemo(() => {
    if (!cockpit) return [];
    return cockpit.grupos
      .map((g) => ({
        tipo: g.tipo,
        keywords: g.keywords
          .filter((k) => marcadas.has(chaveDe(g.tipo, k.texto)))
          .map((k) => k.texto),
      }))
      // Grupo sem keyword marcada não vira ad group vazio: a API recusaria, e
      // recusar aqui é de graça.
      .filter((g) => g.keywords.length > 0);
  }, [cockpit, marcadas]);

  // Trocar a seleção depois de escrever invalida a copy: ela foi ancorada nos
  // termos que estavam marcados. Manter o texto antigo faria o anúncio falar de
  // uma keyword que saiu.
  // ⚠️ Mexer na seleção NÃO apaga mais a copy — ela custou ~174 s de LLM pago.
  //
  // A versão anterior fazia `setEscrita(null)` aqui, e isso somado ao estado
  // viver só na memória do browser era a perda dupla: trocar uma keyword jogava
  // fora o texto inteiro. Agora ele fica e a tela AVISA que foi escrito para
  // outros termos — quem decide reescrever é o operador, sabendo o preço.
  const copyDesatualizada = useMemo(() => {
    if (!escrita || escrita.status !== 'done') return false;
    const agora = selecionadas.map((k) => k.texto).sort().join(' ');
    return agora !== [...escrita.keywords].sort().join(' ');
  }, [escrita, selecionadas]);

  // A copy persistida, lida AO ABRIR e reconsultada enquanto o servidor escreve.
  // É isto que faz sair da página e voltar reencontrar o trabalho já pago.
  useEffect(() => {
    if (!oid) return;
    let ativo = true;
    const ler = () => pautadorApi.lerCopy(oid, runId ?? null)
      .then((r) => { if (ativo) setEscrita('existe' in r && r.existe ? r : null); })
      .catch(() => { /* a copy é opcional: o cockpit não cai por causa dela */ });
    void ler();
    // 4 s: a cascata leva ~174 s medidos, então perguntar mais rápido só produz
    // requisição sem novidade.
    const t = setInterval(() => { if (escrevendo) void ler(); }, 4000);
    return () => { ativo = false; clearInterval(t); };
  }, [oid, runId, escrevendo]);

  // ⚠️ A VERTICAL SALVA VENCE A INFERIDA — uma vez, e sem brigar depois.
  //
  // O efeito do cockpit põe `origem.vertical` (o que a entidade classificou).
  // Se esta oportunidade já teve copy escrita sob uma vertical DECLARADA pelo
  // operador, é ela que vale — foi decisão humana sobre o negócio, e a copy foi
  // escrita sob ela. Sem esta reposição, o F5 devolvia o inferido e a prova
  // reprovava por certificação que ninguém tinha escolhido exigir.
  //
  // `useRef` e não estado: repõe UMA vez, quando a copy salva chega. Repor a
  // cada releitura desfaria uma troca que o operador acabou de fazer, no meio
  // da escrita.
  const verticalReposta = useRef(false);
  useEffect(() => {
    if (verticalReposta.current || !escrita || !('existe' in escrita) || !escrita.existe) return;
    const salva = escrita.vertical;
    if (salva) {
      setVertical(salva);
      verticalReposta.current = true;
    }
  }, [escrita]);

  const alternar = (grupo: string, texto: string) => {
    setMarcadas((s) => {
      const n = new Set(s);
      const k = chaveDe(grupo, texto);
      if (n.has(k)) n.delete(k); else n.add(k);
      return n;
    });
  };

  const alternarGrupo = (g: GrupoCandidato) => {
    setMarcadas((s) => {
      const n = new Set(s);
      const chaves = g.keywords.map((k) => chaveDe(g.tipo, k.texto));
      const todas = chaves.every((c) => n.has(c));
      chaves.forEach((c) => (todas ? n.delete(c) : n.add(c)));
      return n;
    });
  };

  const escreverCopy = async () => {
    if (!cockpit) return;
    setErro(null);
    try {
      // Devolve em ~1,5 s com a linha `running`; quem acompanha daqui em diante
      // é a consulta acima. O servidor recusa disparar duas cascatas para o
      // mesmo card — dois cliques gastariam dobrado.
      const r = await pautadorApi.escreverCopy({
        opportunity_id: oid,
        run_id: runId ?? null,
        keywords: selecionadas.map((k) => k.texto),
        // Decorre da estratégia, como no pedido — a regra vive num lugar só.
        match_type: DECORRE_DA_ESTRATEGIA[estrategia].match_type,
        // ⚠️ A copy tem de ser escrita contra a MESMA vertical que a prova vai
        // usar. Sem isto o operador marcava `informativo` no portão e recebia
        // texto escrito sob as regras de `financeiro`.
        vertical: vertical || cockpit.origem.vertical,
        certificacoes,
        modelo: modeloDaCopy || null,
      });
      setEscrita('existe' in r && r.existe ? r : null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'A escrita da copy falhou.');
    }
  };

  const conta = cockpit?.conta ?? null;
  const bloqueios = (cockpit?.avisos ?? []).filter(barra);
  const observacoes = (cockpit?.avisos ?? []).filter((a) => !barra(a));

  // ⚠️ A PRONTIDÃO DO DESTINO PAGO, LIDA DO SERVIDOR — não inferida daqui.
  //
  // O recibo do portão viaja dentro de `origem`, sob `landing_policy_receipt`.
  // `origem` é tipada em `types/trafego.ts` sem esse campo (o tipo é de outro
  // dono), então o portador entra como `unknown` e o adaptador o abre — que é
  // também o comportamento certo para o dia em que ele não vier: recibo ausente
  // sai como INDETERMINADO, nunca como apto.
  //
  // ⚠️ `exige_ponto_de_campanha` é `true` aqui e não é decoração: esta tela É o
  // momento da elegibilidade de destino de campanha, onde o papel é FORÇADO
  // para destino pago. Um recibo emitido antes de publicar foi medido com rigor
  // menor e não responde a pergunta desta página.
  const destino = useMemo(
    () => leituraDoDestinoPago(cockpit?.origem as unknown, {
      status_wp: cockpit?.origem?.status_wp,
      exige_ponto_de_campanha: true,
    }),
    [cockpit],
  );

  const pendencias: string[] = [];
  if (!conta?.vinculada) pendencias.push('vincular a conta');
  if (gruposEscolhidos.length === 0) pendencias.push('marcar ao menos uma keyword');
  if (escrita?.status !== 'done') pendencias.push('escrever a copy');
  for (const b of bloqueios) pendencias.push(b.titulo.toLowerCase());
  // ⚠️ O destino entra nas pendências INTEIRO, e não só quando há bloqueio.
  // Testar apenas `bloqueadores.length` ignoraria os `desconhecidos` — a
  // verificação exigida que não pôde ser concluída — e foi assim que o handoff
  // anterior deixaria lançar contra uma página cuja varredura falhou.
  for (const r of pendenciasDoDestino(destino)) pendencias.push(r);

  const podeLancar = pendencias.length === 0;
  // O que este funil já produziu. Decide se a barra oferece "Lançar campanha"
  // ou "Lançar outra" — ver o ⚠️ na barra.
  const lancadas = cockpit?.campanhas_lancadas ?? [];
  const jaLancou = lancadas.length > 0;
  const volumeSelecionado = selecionadas.reduce((s, k) => s + (k.volume || 0), 0);

  // Volume medido por keyword, para a mesa. Ausência fica AUSENTE — a linha
  // mostra "volume não medido", nunca zero: zero é uma medição.
  const volumePorKeyword = useMemo(() => {
    const m: Record<string, number> = {};
    for (const g of cockpit?.grupos ?? []) {
      for (const k of g.keywords) {
        if (k.volume != null) m[chave(k.texto)] = k.volume;
      }
    }
    return m;
  }, [cockpit]);

  // O contrato tipado que vai no pedido: as positivas derivadas da seleção
  // (com o match type que o operador escolheu, ou o da estratégia) e as
  // exclusões que ele escreveu. Uma fonte só — a mesa mostra exatamente isto.
  const criterios = useMemo<CriterioDeKeyword[]>(() => {
    const padrao = DECORRE_DA_ESTRATEGIA[estrategia].match_type as MatchType;
    const positivas: CriterioDeKeyword[] = gruposEscolhidos.flatMap((g) =>
      g.keywords.map((texto) => ({
        texto,
        match_type: matchPorKeyword[chave(texto)] ?? padrao,
        negativa: false,
        nivel: 'AD_GROUP' as const,
        grupo: g.tipo,
        origem: 'PAUTADOR' as const,
        motivo: null,
        evidencia: null,
        observado_em: null,
        aprovado_por: null,
      })),
    );
    return [...positivas, ...negativas];
  }, [gruposEscolhidos, matchPorKeyword, estrategia, negativas]);

  const pedido: PedidoDeProvaSearch | null = cockpit ? {
    opportunity_id: oid,
    run_id: runId ?? null,
    customer_id: conta?.customer_id ?? '',
    login_customer_id: conta?.login_customer_id ?? '',
    grupos: gruposEscolhidos,
    copy: escrita?.copy ?? null,
    budget_diario: Number(budget) || 0,
    cpc_inicial: Number(lance) || 0,
    // ⚠️ ONDE O ANÚNCIO APARECE — declarado, e não herdado em silêncio.
    //
    // Até 01/09/2026 o builder ligava Search Partners como literal: inventário
    // diferente do Google Search, ativo em toda campanha da casa, invisível no
    // plano que o operador aprovava. O canário RECUSA pedido sem esta
    // declaração, e recusa parceiros ligados — ele mede o Google Search com um
    // plano conhecido, e misturar inventário torna o resultado inatribuível.
    //
    // Quando a Mesa de Lance ganhar o controle de rede, ele substitui este
    // literal. Enquanto isso o valor é explícito aqui em vez de omitido, porque
    // omitir devolveria o pedido ao default invisível que acabou de ser fechado.
    rede: { google_search: true, search_partners: false, display_expansion: false },
    // ⚠️ NÃO cravar 'PHRASE' aqui. O match type DECORRE da estratégia, e a
    // regra mora num lugar só (`DECORRE_DA_ESTRATEGIA`) para que a tela e o
    // engine nunca discordem: BROAD com CPC manual não tem sinal de leilão que
    // filtre a consulta, e o `Brief` recusa essa combinação.
    match_type: DECORRE_DA_ESTRATEGIA[estrategia].match_type,
    // O contrato TIPADO. `match_type` acima continua indo como o padrão do
    // pedido — é o que preenche a lacuna de quem não declara critério —, e o
    // backend usa este campo quando ele vem preenchido.
    criterios,
    canal: 'SEARCH' as const,
    estrategia_lance: estrategia,
    graduacao_em_conversoes: estrategia === 'MANUAL_CPC' ? graduacao : 0,
    meta_conversao_id: cockpit.conta?.meta_conversao?.primaria?.id ?? null,
    vertical: vertical || cockpit.origem.vertical,
    certificacoes,
    url_final: cockpit.origem.url_final,
  } : null;

  const titulo = cockpit?.origem.nicho || `card #${oid}`;

  return (
    <Layout>
      {/* A barra do instrumento: onde estou, o que falta, e a ação. Ela é fixa
          porque o operador precisa poder lançar de qualquer altura da página —
          na versão anterior a ação vivia numa coluna de 320px, abaixo de tudo. */}
      {cockpit && (
        // ⚠️ `top-14` abaixo de `md`, e o motivo é funcional: o `Layout`
        // renderiza um header `sticky top-0 z-30 h-14` só no MOBILE
        // (`useIsMobile`, 768px). Com `top-0` aqui, esta barra encosta no topo
        // e cobre o botão de menu — a navegação do app fica inalcançável no
        // celular. O `z-20` é a segunda garantia: se algo sobrepuser, quem
        // ganha é o header.
        <div className="sticky top-14 z-20 border-b border-border bg-background/85 backdrop-blur-md md:top-0">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 md:px-6">
            <Trilho
              origem
              keywords={selecionadas.length > 0}
              copy={!!escrita}
              conta={!!conta?.vinculada}
            />
            {/* ⚠️ A AÇÃO PRINCIPAL MUDA quando já existe campanha deste funil.
                Medido em 19/08/2026: depois de publicar, esta barra continuava
                oferecendo "Lançar campanha" como ação primária. A tela até
                passou a mostrar o cartão do que estava no ar, mas o botão não
                mudou — e é o botão que o operador olha.
                Isso convida ao lançamento duplicado, e duas campanhas para o
                mesmo termo competem no mesmo leilão (doutrina P7). Relançar
                continua possível: vira ação SECUNDÁRIA, não a óbvia. */}
            <div className="ml-auto flex items-center gap-3">
              {jaLancou ? (
                <>
                  <span className="flex items-center gap-1.5 text-[11px] text-success">
                    <Check className="h-3.5 w-3.5" aria-hidden />
                    {lancadas.length === 1 ? 'campanha no ar' : `${lancadas.length} campanhas no ar`}
                    {lancadas.every((c) => c.google_ads_status === 'PAUSED') && ' · pausada'}
                  </span>
                  <Button size="sm" variant="outline" className="gap-2"
                          disabled={!podeLancar} onClick={() => setLancando(true)}>
                    <Rocket className="h-3.5 w-3.5" aria-hidden />
                    Lançar outra
                  </Button>
                </>
              ) : (
                <>
                  {!podeLancar && (
                    <span className="hidden text-[11px] text-muted-foreground sm:block">
                      falta: {pendencias.slice(0, 2).join(' · ')}
                      {pendencias.length > 2 && ` +${pendencias.length - 2}`}
                    </span>
                  )}
                  <Button size="sm" className="gap-2" disabled={!podeLancar}
                          onClick={() => setLancando(true)}>
                    <Rocket className="h-3.5 w-3.5" aria-hidden />
                    Lançar campanha
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">
        <Link to="/trafego"
              className="kicker inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="h-3 w-3" aria-hidden /> tráfego
        </Link>

        <header className="reveal mt-3" style={{ ['--i' as string]: 0 }}>
          <div className="kicker">nova campanha · search</div>
          <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
            {titulo}
          </h1>
          <div className="aurora-rule mt-4 w-16" />
          {cockpit && (
            <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              <span>{cockpit.origem.dominio.replace(/^https?:\/\//, '')}</span>
              <span aria-hidden>·</span>
              <span className="uppercase">{cockpit.origem.pais}/{cockpit.origem.idioma}</span>
              <span aria-hidden>·</span>
              <span>{cockpit.origem.vertical}</span>
            </p>
          )}
        </header>

        {erro && (
          <div className="mt-6 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            {erro}
          </div>
        )}
        {!cockpit && !erro && <Esqueleto />}

        {cockpit && (
          <div className="mt-8 space-y-5">
            {/* Os bloqueios vêm antes de qualquer outra coisa. Cada um deles
                custou alguém descobrir tarde. */}
            {bloqueios.length > 0 && (
              <section className="reveal card-volc border-destructive/40 p-5"
                       style={{ ['--i' as string]: 1 }}>
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />
                  <h2 className="text-sm font-medium">
                    {bloqueios.length === 1
                      ? 'Uma trava impede o lançamento'
                      : `${bloqueios.length} travas impedem o lançamento`}
                  </h2>
                </div>
                <ul className="mt-3 space-y-3">
                  {bloqueios.map((a) => (
                    <li key={a.codigo}>
                      <p className="text-sm font-medium">{a.titulo}</p>
                      <p className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                        {a.detalhe}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* A faixa vem antes do painel de lançamento porque a primeira
                pergunta de um lançamento é PARA ONDE ele manda o clique. Ela é
                curta de propósito: o painel inteiro está no cartão 01. */}
            <FaixaDoDestinoPago leitura={destino} className="reveal"
                                key="faixa-destino" />

            <PainelDoLancamento cockpit={cockpit} trava={trava}
                                gruposEscolhidos={gruposEscolhidos} budget={budget}
                                estrategia={estrategia} />

            {/* ⚠️ `estado` e `pronto` vinham de `status_wp !== 'draft'`, que
                pintava "LP no ar" e marcava a etapa como pronta quando o
                servidor NUNCA tinha lido o WordPress (`status_wp: null`). Agora
                os dois vêm da leitura do destino, onde ausência é
                INDETERMINADO — e INDETERMINADO não abre nada. */}
            <Cartao n={1} titulo="de onde vem" indice={2}
                    estado={resumoDoDestino(destino)}
                    pronto={destino.apto_para_campanha}>
              <a href={cockpit.origem.url_final} target="_blank" rel="noreferrer"
                 className="tabular break-all text-sm underline-offset-4 hover:underline">
                {cockpit.origem.url_final}
              </a>

              {/* O painel inteiro mora aqui, no cartão da origem, porque é aqui
                  que o operador olha para a landing page. A faixa no topo da
                  página é só o resumo dele. */}
              <PainelDoDestinoPago leitura={destino} className="mt-4" />
              {cockpit.origem.vertical_declarada
                && cockpit.origem.vertical_declarada !== cockpit.origem.vertical && (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  O card dizia "{cockpit.origem.vertical_declarada}"; o portão de
                  habilitação usa "{cockpit.origem.vertical}".
                </p>
              )}
              {observacoes.length > 0 && <Observacoes avisos={observacoes} />}
            </Cartao>

            <Cartao n={2} titulo="keywords" indice={3}
                    pronto={selecionadas.length > 0}
                    estado={selecionadas.length
                      ? `${selecionadas.length} em ${gruposEscolhidos.length} ad group${gruposEscolhidos.length > 1 ? 's' : ''}`
                      : 'nenhuma marcada'}>
              {/* O número-herói: `.text-outline` é a assinatura da marca, e este
                  módulo nunca a tinha usado. O volume é o que dimensiona a
                  aposta — ele merece o peso. */}
              <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                <div>
                  <div className="kicker">volume/mês selecionado</div>
                  <div className="text-outline font-display text-4xl font-bold leading-none tabular-nums md:text-5xl">
                    {compacto(volumeSelecionado)}
                  </div>
                </div>
                {cockpit.triagem && (
                  <p className="max-w-[52ch] text-xs leading-relaxed text-muted-foreground">
                    A mineração analisou{' '}
                    <b className="tabular text-foreground">{cockpit.triagem.analisadas}</b>{' '}
                    termos e triou{' '}
                    <b className="tabular text-foreground">{cockpit.triagem.aprovadas_anuncio}</b>{' '}
                    para anúncio, {cockpit.triagem.para_conteudo} para conteúdo,{' '}
                    {cockpit.triagem.descartadas} descartados. Você pode discordar — o
                    motivo de cada um está no termo.
                  </p>
                )}
              </div>

              {/* A RÉGUA VEM ANTES DA LISTA, e essa inversão é a decisão de
                  desenho mais forte da tela. Medido no card 73: uma keyword é
                  73% do volume. Vinte e três linhas de altura igual escondem
                  isso; só a forma denuncia. */}
              <div className="mt-6">
                <ReguaDeLeilao selecionadas={selecionadas} lance={Number(lance) || undefined} />
              </div>

              <div className="mt-6 space-y-3">
                {cockpit.grupos.map((g) => (
                  <Grupo key={g.tipo} g={g} marcadas={marcadas}
                         onAlternar={alternar} onAlternarGrupo={alternarGrupo} />
                ))}
              </div>

              {/* A mesa vem DEPOIS da marcação porque ela revisa o que foi
                  marcado: a correspondência de cada termo e o que a campanha
                  não deve comprar. Antes desta peça o operador lançava sem ter
                  onde escrever uma exclusão, e sem saber que o alcance dela era
                  decidido no código. */}
              {selecionadas.length > 0 && (
                <div className="mt-8 border-t border-border pt-6">
                  <MesaDeCriterios
                    grupos={gruposEscolhidos}
                    volumePorKeyword={volumePorKeyword}
                    matchPadrao={DECORRE_DA_ESTRATEGIA[estrategia].match_type as MatchType}
                    permitirBroadPositivo={estrategia === 'MAXIMIZE_CONVERSIONS'}
                    matchPorKeyword={matchPorKeyword}
                    onMatchPorKeyword={setMatchPorKeyword}
                    negativas={negativas}
                    onNegativas={setNegativas}
                  />
                </div>
              )}
            </Cartao>

            {/* ⚠️ `escrita.copy` é NULO em `running`, `error` e na linha perdida.
                A versão anterior lia `escrita.copy.headlines.length` direto e
                derrubava a página inteira com TypeError no instante em que a
                escrita começava — tela branca, sem erro visível, com a cascata
                rodando atrás. */}
            <Cartao n={3} titulo="a copy" indice={4}
                    pronto={escrita?.status === 'done'}
                    estado={rotuloDaCopy(escrita)}>
              <CartaoCopy
                escrita={escrita}
                desatualizada={copyDesatualizada}
                escrevendo={escrevendo}
                podeEscrever={selecionadas.length > 0 && !escrevendo}
                motivoBloqueio={selecionadas.length === 0
                  ? 'Marque as keywords primeiro — é nelas que o texto ancora.'
                  : undefined}
                onEscrever={escreverCopy}
                onEditar={(c: CopyGerada) => {
                  // Estado local primeiro, para o campo não piscar; a gravação
                  // vai atrás. Sem ela a correção sumia ao recarregar — e o
                  // texto que não sobe voltava.
                  setEscrita((e) => (e ? { ...e, copy: c } : e));
                  void pautadorApi
                    .salvarCopyEditada({ opportunity_id: oid, run_id: runId ?? null, copy: c })
                    .then((salva) => setEscrita(salva))
                    .catch(() => { /* a edição local vale; a prova é quem julga */ });
                }}
                modelo={modeloDaCopy} onModelo={setModeloDaCopy}
              />
            </Cartao>

            {/* O portão vem ANTES de conta e lance de propósito: ele é o que
                pode barrar tudo, e descobrir isso depois de escolher lance e
                verba é desperdiçar o trabalho — o mesmo defeito que o
                PainelDoLancamento existe para não repetir. */}
            {/* O que já foi lançado vem ANTES de tudo: é a primeira coisa que
                o operador precisa saber ao reabrir a tela. */}
            {(cockpit?.campanhas_lancadas?.length ?? 0) > 0 && (
              <div className="reveal">
                <JaNoAr
                  campanhas={cockpit!.campanhas_lancadas!}
                  onVerVeredito={(cust, camp) => {
                    setContaDoVeredito(cust);
                    setCampanhaCriada(camp);
                  }}
                />
              </div>
            )}

            {campanhaCriada && (conta?.customer_id || contaDoVeredito) && (
              <div className="reveal">
                <VereditoDePolitica customerId={contaDoVeredito ?? conta!.customer_id!}
                                    campaignId={campanhaCriada} />
              </div>
            )}

            {cockpit && verticais.length > 0 && (
              <div className="reveal" style={{ animationDelay: '0.42s' }}>
                <PortaoDePolitica
                  verticais={verticais}
                  escolhida={vertical || cockpit.origem.vertical}
                  onEscolher={setVertical}
                  certificacoes={certificacoes}
                  onCertificacoes={setCertificacoes}
                  pais={cockpit.origem.pais}
                  sugeridaPelaEntidade={cockpit.origem.vertical}
                />
              </div>
            )}

            <Cartao n={4} titulo="conta e lance" indice={5} pronto={!!conta?.vinculada}
                    estado={conta?.vinculada ? conta.dominio : 'sem conta vinculada'}>
              {conta?.vinculada ? (
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                  <div>
                    <div className="kicker">conta de anúncios</div>
                    <div className="tabular mt-0.5 text-sm">{conta.customer_id}</div>
                  </div>
                  <div>
                    <div className="kicker">via MCC</div>
                    <div className="tabular mt-0.5 text-sm">{conta.login_customer_id}</div>
                  </div>
                  <Badge variant="success" className="gap-1">
                    <Check className="h-3 w-3" aria-hidden /> vinculada
                  </Badge>
                </div>
              ) : (
                <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
                  <p className="text-sm font-medium text-destructive">Conta não vinculada</p>
                  <p className="mt-1 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                    {conta?.motivo ?? 'Este funil não tem projeto conhecido.'}
                  </p>
                  <Link to="/settings/integrations"
                        className="mt-2 inline-block text-xs underline underline-offset-4">
                    Abrir Integrações
                  </Link>
                </div>
              )}

              {cockpit && (
                <div className="mt-6 border-t border-border pt-5">
                  <MesaDeLance
                    cockpit={cockpit}
                    estrategia={estrategia} onEstrategia={setEstrategia}
                    lance={lance} onLance={setLance}
                    budget={budget} onBudget={setBudget}
                    graduacao={graduacao} onGraduacao={setGraduacao}
                  />
                </div>
              )}

              {/* ⚠️ Este aviso era INCONDICIONAL, e virou mentira no instante em
                  que a Mesa passou a escolher a estratégia. Sob `manual_cpc` —
                  agora o padrão — o `cpc_bid_micros` do ad group É o lance.
                  Sob `maximize_conversions` a API o aceita e o ignora na
                  veiculação. Por isso o texto depende da escolha: o operador
                  precisa saber se o número que ele digitou vale alguma coisa. */}
              {estrategia === 'MAXIMIZE_CONVERSIONS' && (
                <p className="mt-4 max-w-[74ch] text-[11px] leading-relaxed text-warning">
                  <b>Sob lance automático, este valor não controla o leilão.</b>{' '}
                  O Google aceita o CPC do ad group e o ignora na veiculação —
                  quem decide é a meta de conversão. Ele fica como rede de
                  proteção, para o dia em que a estratégia virar manual.
                </p>
              )}
              <p className="mt-2 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
                O CPC que a régua de leilão mostra é <b>minerado</b>: superestima
                o real em 7,4× e inverte a ordem dentro do cluster. Não serve
                para preencher o lance — use CPC medido na conta.
              </p>

              {trava && !trava.env_presente && (
                <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
                  <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                  A trava de escrita está fechada. Você pode montar e provar à
                  vontade — a prova é leitura e não cria nada.
                </p>
              )}
            </Cartao>
          </div>
        )}
      </div>

      {lancando && pedido && (
        <Lancamento
          pedido={pedido}
          trava={trava}
          titulo={titulo}
          destino={destino}
          resumoDaCopy={escrita
            ? `${escrita.copy.headlines.length} títulos · ${escrita.copy.descriptions.length} descrições · ${escrita.segundos.toFixed(0)}s`
            : '—'}
          onCriada={(id) => {
            setCampanhaCriada(id);
            // ⚠️ RELÊ O COCKPIT. Sem isto a tela continuava oferecendo "lançar"
            // logo depois de lançar: `campanhas_lancadas` vem do servidor e
            // ficou defasado no instante em que a campanha nasceu.
            //
            // É a mesma classe de defeito que a copy persistida tinha — estado
            // que existe no servidor e a tela guarda como se fosse dela.
            void pautadorApi.cockpitDeTrafego(oid, { runId })
              .then(setCockpit)
              .catch(() => { /* o recibo já apareceu; recarregar resolve */ });
          }}
          onFechar={() => setLancando(false)}
        />
      )}
    </Layout>
  );
};

// ── peças ───────────────────────────────────────────────────────────────────

/** O estado do estágio 3 em duas palavras, sem tocar em `copy` quando ela é
 *  nula — que é o caso em `running`, `error` e na linha perdida. */
function rotuloDaCopy(e: CopyPersistida | null): string {
  if (!e) return 'não escrita';
  if (e.status === 'running') return e.perdida ? 'perdida' : 'escrevendo…';
  if (e.status === 'error') return 'falhou';
  if (!e.copy) return 'não escrita';
  return `${e.copy.headlines.length} títulos · ${e.copy.descriptions.length} descrições`;
}

function compacto(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`;
  return String(n);
}

/** Onde estou e quanto falta — a sensação de passo sem partir a página.
 *
 *  Os números são um SEQUÊNCIA de verdade: não dá para escrever a copy sem
 *  keywords, nem lançar sem conta. Numerar aqui codifica dependência, não
 *  decora. */
const Trilho: React.FC<{ origem: boolean; keywords: boolean; copy: boolean; conta: boolean }> =
  ({ origem, keywords, copy, conta }) => {
  const passos = [
    { n: 1, nome: 'origem', ok: origem },
    { n: 2, nome: 'keywords', ok: keywords },
    { n: 3, nome: 'copy', ok: copy },
    { n: 4, nome: 'conta', ok: conta },
  ];
  return (
    <ol className="flex items-center gap-1 overflow-x-auto">
      {passos.map((p) => (
        <li key={p.n}>
          <a href={`#estagio-${p.n}`}
             className={cn('flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors hover:bg-muted',
                           p.ok ? 'text-foreground' : 'text-muted-foreground')}>
            <span className={cn('flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[9px]',
                                p.ok ? 'border-success bg-success text-success-foreground'
                                     : 'border-muted-foreground/40')}>
              {p.ok ? <Check className="h-2.5 w-2.5" aria-hidden /> : p.n}
            </span>
            <span className="whitespace-nowrap">{p.nome}</span>
          </a>
        </li>
      ))}
    </ol>
  );
};

const Cartao: React.FC<{
  n: number; titulo: string; estado?: string; pronto?: boolean; indice: number;
  children: React.ReactNode;
}> = ({ n, titulo, estado, pronto, indice, children }) => (
  // `scroll-mt` maior no mobile porque lá são DUAS barras fixas: a do app
  // (h-14) e a do cockpit. Sem isso o trilho rola até o cartão e o título dele
  // fica escondido atrás delas.
  <section id={`estagio-${n}`} className="reveal card-volc scroll-mt-32 p-5 md:scroll-mt-20 md:p-6"
           style={{ ['--i' as string]: indice }}>
    <div className="mb-5 flex items-baseline gap-3">
      <span className={cn('tabular font-display text-sm font-bold tabular-nums',
                          pronto ? 'text-foreground' : 'text-muted-foreground/50')}>
        {String(n).padStart(2, '0')}
      </span>
      <h2 className="text-[15px] font-medium tracking-tight">{titulo}</h2>
      <span className="hairline flex-1" />
      {estado && (
        <span className={cn('shrink-0 text-[11px]',
                            pronto ? 'text-foreground' : 'text-muted-foreground')}>
          {estado}
        </span>
      )}
    </div>
    {children}
  </section>
);

/** As observações não barram nada, e por isso vêm colapsadas: dar a elas o
 *  mesmo espaço de uma trava foi o que fez "idioma ajustado" parecer tão grave
 *  quanto "a URL de destino é provisória". */
const Observacoes: React.FC<{ avisos: AvisoDoCockpit[] }> = ({ avisos }) => {
  const [aberto, setAberto] = useState(false);
  return (
    <div className="mt-4">
      <button type="button" onClick={() => setAberto((v) => !v)}
              aria-expanded={aberto}
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', aberto && 'rotate-180')}
                     aria-hidden />
        {avisos.length} {avisos.length === 1 ? 'observação' : 'observações'}
      </button>
      {aberto && (
        <ul className="mt-3 space-y-3">
          {avisos.map((a) => (
            <li key={a.codigo + a.titulo} className="flex items-start gap-2">
              {a.severidade === 'informacao'
                ? <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                : <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />}
              <div className="min-w-0">
                <p className="text-xs font-medium">{a.titulo}</p>
                {a.detalhe && (
                  <p className="mt-0.5 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
                    {a.detalhe}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const Grupo: React.FC<{
  g: GrupoCandidato; marcadas: Set<string>;
  onAlternar: (g: string, t: string) => void;
  onAlternarGrupo: (g: GrupoCandidato) => void;
}> = ({ g, marcadas, onAlternar, onAlternarGrupo }) => {
  const chaves = g.keywords.map((k) => chaveDe(g.tipo, k.texto));
  const n = chaves.filter((c) => marcadas.has(c)).length;
  const [aberto, setAberto] = useState(false);
  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
        <button type="button" onClick={() => onAlternarGrupo(g)}
                aria-label={`marcar todas de ${g.tipo}`}
                className="flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors"
                style={{ borderColor: n ? 'hsl(var(--primary))' : undefined }}>
          {n === chaves.length && <Check className="h-3 w-3 text-primary" aria-hidden />}
          {n > 0 && n < chaves.length && <span className="h-1.5 w-1.5 bg-primary" />}
        </button>
        <button type="button" onClick={() => setAberto((v) => !v)}
                aria-expanded={aberto}
                className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className="text-sm font-medium">{g.tipo}</span>
          <span className="tabular text-[11px] text-muted-foreground">
            {n}/{chaves.length} · vol {g.volume.toLocaleString('pt-BR')}
            {g.cpc_ponderado && ` · CPC ${g.cpc_ponderado.valor.toFixed(2).replace('.', ',')}`}
          </span>
          <ChevronDown className={cn('ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform',
                                     aberto && 'rotate-180')} aria-hidden />
        </button>
      </div>
      {g.descricao && !aberto && (
        <p className="max-w-[74ch] px-3 pb-2.5 text-[11px] leading-relaxed text-muted-foreground">
          {g.descricao}
        </p>
      )}
      {aberto && (
        <div className="border-t border-border px-3 pb-3 pt-2">
          {g.descricao && (
            <p className="mb-2 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
              {g.descricao}
            </p>
          )}
          <ListaDeKeywords
            grupo={g}
            marcadas={new Set(g.keywords
              .filter((k) => marcadas.has(chaveDe(g.tipo, k.texto)))
              .map((k) => k.texto))}
            onAlternar={(texto) => onAlternar(g.tipo, texto)}
          />
        </div>
      )}
    </div>
  );
};

const Campo: React.FC<{ rotulo: string; valor: string; onChange: (v: string) => void }> =
  ({ rotulo, valor, onChange }) => (
  <label className="block">
    <span className="kicker">{rotulo}</span>
    <Input value={valor} onChange={(e) => onChange(e.target.value)}
           inputMode="decimal"
           className="tabular mt-1.5 h-9 text-sm" />
  </label>
);

/** Esqueleto com a FORMA da tela, não um spinner: o layout é conhecido antes do
 *  dado chegar, e um "carregando…" descarta essa informação. */
const Esqueleto: React.FC = () => (
  <div className="mt-8 space-y-5">
    {[0, 1, 2].map((i) => (
      <div key={i} className="card-volc p-6">
        <div className="skeleton h-4 w-40" />
        <div className="mt-5 space-y-2">
          {[0, 1, 2].map((j) => (
            <div key={j} className="skeleton h-8" style={{ width: `${100 - j * 12}%` }} />
          ))}
        </div>
      </div>
    ))}
  </div>
);

export default NovaCampanhaPage;
