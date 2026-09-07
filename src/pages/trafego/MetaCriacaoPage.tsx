/**
 * A bancada de criação Meta.
 *
 * ## Por que ela é irmã da bancada Google, e não um produto novo
 *
 * `design.md` diz duas coisas que decidem esta página: "this file is the only
 * product-UI authority… Do not invent a third visual language" e "Create studio.
 * Creation is a channel-specific operational bench". As duas juntas significam
 * que o Meta tem a SUA jornada, mas no MESMO vocabulário do lançamento Google
 * (`NovaCampanhaPage.tsx`): `bancada-command-deck`, `bancada-route`,
 * `bancada-stage`, `bancada-grid` e as peças de `components/trafego/bancada`.
 *
 * O trilho de etapas é desenhado aqui em vez de reusar `MapaDeParadas` porque
 * aquele componente é tipado por `ParadaDaBancada`, uma união fechada das
 * paradas do Google. Estender a união arrastaria os `Record` exaustivos de
 * `bancada/paradas.ts` para dentro de uma missão que não é sobre o Google. O
 * DESENHO é o mesmo — as classes `.bancada-route*` são as mesmas — e é o
 * desenho que o contrato de UI governa.
 *
 * ## ⚠️ O que esta tela pode e o que ela não pode
 *
 * Ela lê a conta real, compila o plano no backend e — só depois de clique
 * explícito e liberação do servidor — pede à Meta uma validação que não cria
 * nada. Não existe caminho de criação nem de ativação para o contrato V2.
 *
 * ## ⚠️ DOIS CONTRATOS, UMA TELA, E A ESCOLHA É VISÍVEL
 *
 * `contratoDoPlano` (em `rascunho.ts`) decide se este rascunho fala V1 — a
 * receita única que a Meta aceitou em 05/09/2026, e a única com rota de
 * aprovação e criação PAUSED — ou V2, que descreve N conjuntos, ABO/CBO,
 * público de verdade e mensuração com propósito, e que só tem `compilar` e
 * `validar` no backend. A decisão é derivada da FORMA do plano e aparece na
 * revisão com o motivo. Um operador nunca precisa adivinhar por que o botão de
 * criar sumiu: a tela diz qual recurso levou o plano para o contrato sem rota
 * de nascimento.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, CircleCheck, CircleDot, Copy, Film, Image as ImageIcon,
  Lock, Megaphone, Plus, ShieldCheck, Trash2,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import {
  AcaoDominante, BlocoDeEvidencia, ChipDeEstado, LinhaDeFato, PainelDeBloqueio, Pedido,
} from '@/components/trafego/bancada';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import { MapaDoPlano } from '@/components/trafego/meta/MapaDoPlano';
import { PainelDeConjuntos } from '@/components/trafego/meta/PainelDeConjuntos';
import { PainelDeMensuracao } from '@/components/trafego/meta/PainelDeMensuracao';
import { PainelDeOrcamento } from '@/components/trafego/meta/PainelDeOrcamento';
import { PainelDePublico } from '@/components/trafego/meta/PainelDePublico';
import { PainelDeReceita } from '@/components/trafego/meta/PainelDeReceita';
import { Campo, Escolha, GrupoDeEscolha, campo } from '@/components/trafego/meta/primitivas';
import {
  BLOQUEIOS, CAPACIDADES_FECHADAS, CONFIRMACAO_DE_CRIACAO, ConjuntoDraft, Draft, EstadoDaEtapa,
  EtapaId, IDADE_MAXIMA_PADRAO, IDADE_MINIMA_PADRAO, LIMITE_CONJUNTOS, LIMITE_VARIACOES,
  MidiaDaVariacao, NivelDeOrcamento, PeriodoDeOrcamento, PropositoDeMensuracao, RECEITA_PADRAO,
  VariacaoDraft, conjuntoInicial, confirmacaoDeCriacaoValida, contratoDoPlano, dominioDoDestino,
  formatarBrl, inicioEmIso, nomeUnico, orcamentosDoPlano, paraPlano, paraPlanoV2,
  prontidaoDasEtapas, prontoParaCompilar, proximaChave, reaisParaMinor, variacaoCompleta,
  variacaoInicial, variacoesEmitidas, type CapacidadesDaBancada,
} from '@/components/trafego/meta/rascunho';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  fraseDaOperacao, lerOperacao,
} from '@/components/trafego/meta/estadoDaOperacao';
import { MetaOperationReceipt } from '@/components/trafego/meta/MetaOperationReceipt';
import {
  AprovacaoCriacaoMeta, AtivoCriacaoMeta, CatalogoDeReceitasMeta, ContaMetaLocal,
  ConversaoPersonalizadaMetaLocal, EnvelopeDeCatalogoMeta, FonteDeMensuracaoMeta,
  LugarDoCatalogoMeta, PautadorApiError, PublicoDoCatalogoMeta, pautadorApi,
  ReciboCriacaoMeta, ResultadoCompilacaoMeta, ResumoDoPlanoMetaV2,
  ResultadoReconciliacaoMeta, ResultadoValidacaoPlanoMeta,
} from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { AvisoDoCockpit, LinhaDoPedido } from '@/types/trafego';

const ETAPAS = [
  { id: 'base', nome: 'Base', pergunta: 'De qual conta e Página esta campanha nasce?' },
  { id: 'campanha', nome: 'Campanha', pergunta: 'Que campanha você está autorizando?' },
  { id: 'orcamento', nome: 'Orçamento', pergunta: 'Quanto ela pode gastar, e onde a verba mora?' },
  { id: 'conjunto', nome: 'Conjunto', pergunta: 'Quantos conjuntos, e como cada um entrega?' },
  { id: 'publico', nome: 'Público', pergunta: 'Quem pode ser alcançado?' },
  { id: 'criativo', nome: 'Anúncios', pergunta: 'Quais anúncios vão nascer, e em qual conjunto?' },
  { id: 'mensuracao', nome: 'Mensuração', pergunta: 'Para onde o clique leva, e o que é medido?' },
  { id: 'revisao', nome: 'Revisão', pergunta: 'O que exatamente será enviado à Meta?' },
] as const satisfies readonly { id: EtapaId; nome: string; pergunta: string }[];

const DESENHO_DO_ESTADO: Record<
  EstadoDaEtapa,
  { Glifo: React.ComponentType<{ className?: string }>; palavra: string; tinta: string }
> = {
  pronto: { Glifo: CircleCheck, palavra: 'pronto', tinta: 'text-success' },
  pendente: { Glifo: CircleDot, palavra: 'pendente', tinta: 'text-muted-foreground' },
  bloqueado: { Glifo: Lock, palavra: 'bloqueado', tinta: 'text-destructive' },
  validado: { Glifo: ShieldCheck, palavra: 'validado', tinta: 'text-verified' },
};

const CTAS: readonly [string, string][] = [
  ['LEARN_MORE', 'Saiba mais'],
  ['APPLY_NOW', 'Inscreva-se'],
  ['SIGN_UP', 'Cadastre-se'],
  ['GET_QUOTE', 'Solicitar cotação'],
  ['CONTACT_US', 'Fale conosco'],
];

/* ⚠️ `PALAVRA_DO_PASSO`, `TOM_DO_PASSO`, `GLIFO_DO_PASSO` e `DESCRICAO_DO_PASSO`
   viviam aqui e NÃO eram usados por nenhuma linha deste arquivo: as versões
   vivas moram em `estadoDaOperacao.ts`, que é quem `MetaOperationReceipt` lê.
   Duas cópias do mesmo vocabulário, uma delas morta, é como uma correção
   acontece no lugar errado e ninguém entende por que a tela não mudou. A cópia
   morta saiu. */

const inicioPadrao = () => {
  const data = new Date(Date.now() + 30 * 60 * 1000);
  data.setSeconds(0, 0);
  const local = new Date(data.getTime() - data.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const CHAVE_DO_PRIMEIRO_CONJUNTO = 'adset-001';

const DRAFT_INICIAL: Draft = {
  recipeId: RECEITA_PADRAO,
  accountRef: '', pageRef: '', instagramActorRef: '',
  campaignName: 'VOLC · Meta · Tráfego · LPV',
  destinationUrl: 'https://focogenial.com/',
  nivelDeOrcamento: 'ADSET',
  periodoDeOrcamento: 'DAILY',
  budgetBrl: '10,00',
  categoryConfirmed: false,
  creativeMode: 'single',
  conjuntos: [conjuntoInicial(
    CHAVE_DO_PRIMEIRO_CONJUNTO, 'Brasil · Amplo · LPV · Automático', inicioPadrao(), '10,00')],
  variations: [variacaoInicial('variation-001', 1, CHAVE_DO_PRIMEIRO_CONJUNTO)],
};
/** A prévia real da peça, servida pelo proxy autenticado do backend. */
const PreviaDaPeca: React.FC<{ accountRef: string; ativo?: AtivoCriacaoMeta }> = ({
  accountRef, ativo,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setErro(null);
    setUrl(null);
    if (!accountRef || !ativo?.referencia_opaca || !ativo.preview_disponivel) return;
    let vivo = true;
    let criada: string | null = null;
    pautadorApi.previewAtivoMeta(accountRef, ativo.referencia_opaca)
      .then((proxima) => {
        criada = proxima;
        if (vivo) setUrl(proxima);
        else URL.revokeObjectURL(proxima);
      })
      .catch((exc) => vivo && setErro(
        exc instanceof Error ? exc.message : 'Não foi possível carregar a prévia.'));
    return () => {
      vivo = false;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [accountRef, ativo?.referencia_opaca, ativo?.preview_disponivel]);

  const Glifo = ativo?.tipo === 'video_asset' ? Film : ImageIcon;
  return (
    <div className="flex min-h-40 items-center justify-center overflow-hidden rounded-lg border border-border/70 bg-muted/30">
      {url ? (
        <img
          src={url}
          alt={`Prévia de ${ativo?.nome || 'peça selecionada'}`}
          className="h-full max-h-64 w-full object-contain"
        />
      ) : (
        <div className="flex flex-col items-center gap-2 px-5 text-center text-sm text-muted-foreground">
          <Glifo className="h-7 w-7 opacity-50" aria-hidden />
          <span>{erro || (ativo?.preview_disponivel ? 'Carregando prévia…' : 'Prévia indisponível')}</span>
        </div>
      )}
    </div>
  );
};

/** Traduz a recusa do backend sem apagar código e subcódigo da Meta. */
function avisosDoErro(exc: unknown): AvisoDoCockpit[] {
  if (!(exc instanceof PautadorApiError)) {
    return [{
      codigo: 'ERRO_LOCAL', severidade: 'alta',
      titulo: 'A bancada não completou a operação',
      detalhe: exc instanceof Error ? exc.message : 'causa desconhecida',
    }];
  }
  const corpo = (exc.corpo ?? {}) as {
    codigo?: string;
    provedor?: {
      objeto?: string; code?: string; error_subcode?: string; messages?: string[];
    };
  };
  const provedor = corpo.provedor;

  // Timeout não é recusa. Sem este ramo o operador lê "Nenhum detalhe
  // adicional foi devolvido" e conclui que a Meta reprovou o plano — quando na
  // verdade ninguém do outro lado respondeu, e o plano segue intacto.
  if (corpo.codigo === 'META_VALIDATE_TIMEOUT') {
    return [{
      codigo: corpo.codigo,
      severidade: 'alta',
      titulo: exc.message,
      detalhe: 'A Meta não respondeu a tempo. Isto não é uma recusa: o plano não foi '
        + 'julgado e nada foi criado, porque o pedido levava validate_only. '
        + 'Pode clicar em validar de novo.',
    }];
  }

  // ⚠️ UMA recusa da Meta é UM impedimento.
  //
  // Antes, cada linha de explicação virava um aviso próprio: a recusa 100/4005
  // de 05/09/2026 chegou como `error_user_title`, `error_user_msg` e `message`,
  // e o painel anunciou "4 impedimentos" para um único incidente. Contar
  // explicações como impedimentos ensina o operador a achar que quatro coisas
  // quebraram — e a procurar três consertos que não existem.
  //
  // Nenhum texto se perde: título carrega objeto, código e subcódigo; as
  // explicações da Meta ficam agrupadas no detalhe, na ordem em que o backend
  // as sanitizou.
  if (provedor?.code) {
    const explicacoes = (provedor.messages ?? [])
      .map((m) => String(m ?? '').trim())
      .filter(Boolean);
    const objeto = provedor.objeto ? `${provedor.objeto} · ` : '';
    const subcodigo = provedor.error_subcode ? `/${provedor.error_subcode}` : '';
    return [{
      codigo: corpo.codigo || `HTTP_${exc.status}`,
      severidade: 'alta',
      titulo: `A Meta recusou ${objeto}código ${provedor.code}${subcodigo}`,
      detalhe: explicacoes.length
        ? explicacoes.join(' · ')
        : 'A Meta não devolveu explicação adicional.',
    }];
  }

  return [{
    codigo: corpo.codigo || `HTTP_${exc.status}`,
    severidade: 'alta',
    titulo: exc.message,
    detalhe: 'Nenhum detalhe adicional foi devolvido.',
  }];
}

const MetaCriacaoPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const pedida = params.get('etapa') as EtapaId | null;
  /** A referência OPACA da operação, e é só ela que viaja na URL.
   *
   * ⚠️ Nem token, nem id da Meta, nem o plano congelado: o `approval_id` é um
   * UUID que só significa alguma coisa dentro do banco, e o servidor ainda
   * confere se quem pede é quem aprovou. Uma referência malformada não chega
   * perto de credencial nenhuma — ela morre na validação da rota. */
  const operacaoRef = params.get('operacao');
  const etapa: EtapaId = ETAPAS.some((item) => item.id === pedida) ? pedida! : 'base';
  const indice = ETAPAS.findIndex((item) => item.id === etapa);

  const [draft, setDraft] = useState<Draft>(DRAFT_INICIAL);
  const [contas, setContas] = useState<ContaMetaLocal[]>([]);
  const [paginas, setPaginas] = useState<AtivoCriacaoMeta[]>([]);
  const [imagens, setImagens] = useState<AtivoCriacaoMeta[]>([]);
  const [videos, setVideos] = useState<AtivoCriacaoMeta[]>([]);
  const [capacidades, setCapacidades] = useState<CapacidadesDaBancada>(CAPACIDADES_FECHADAS);
  /** O catálogo de receitas do servidor. `null` = ainda não lido, e a tela diz
   *  isso em vez de inventar uma lista. */
  const [catalogo, setCatalogo] = useState<CatalogoDeReceitasMeta | null>(null);
  const [catalogoErro, setCatalogoErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState<
    'ativos' | 'compilar' | 'validar' | 'aprovar' | 'criar' | 'reconciliar'
    | 'conversoes' | 'publicos' | 'lugares' | null>(null);
  const [avisos, setAvisos] = useState<AvisoDoCockpit[]>([]);
  const [compilacao, setCompilacao] = useState<ResultadoCompilacaoMeta | null>(null);
  const [validacao, setValidacao] = useState<ResultadoValidacaoPlanoMeta | null>(null);
  /** ⚠️ O RESUMO É DO SERVIDOR, e a revisão não tem outra fonte (`F37`, `A33`).
   *  Ele cai junto com a compilação em `invalidar()`: um resumo que descreve o
   *  plano anterior sobre um rascunho novo seria a divergência que ele existe
   *  para impedir. */
  const [resumo, setResumo] = useState<ResumoDoPlanoMetaV2 | null>(null);
  const [aprovacao, setAprovacao] = useState<AprovacaoCriacaoMeta | null>(null);
  const [reconciliacao, setReconciliacao] = useState<
    { referencia: string; resultado: ResultadoReconciliacaoMeta } | null>(null);
  /** Os CATÁLOGOS lidos da conta, cada um com a conta a que pertence.
   *
   * ⚠️ O par com a referência da conta é a guarda de `A31`/`A13`: uma resposta
   * lenta da conta A não pode pousar sobre a conta B, e a lista da conta
   * anterior não pode continuar na tela da conta nova. Um público de outra
   * conta nunca poderia ser escolhido aqui — e a referência dele nem resolveria
   * no backend, que relê o catálogo da conta antes de traduzir.
   *
   * ⚠️ `null` significa NÃO LIDO, e isso é diferente de lista vazia. Nenhum
   * deles é buscado ao montar: o preflight desta lane já custa nove requisições
   * paginadas por clique, e um catálogo automático multiplicaria isso. */
  const [catalogoDeMensuracao, setCatalogoDeMensuracao] = useState<{
    contaRef: string;
    fontes: EnvelopeDeCatalogoMeta<FonteDeMensuracaoMeta>;
    conversoes: EnvelopeDeCatalogoMeta<ConversaoPersonalizadaMetaLocal>;
  } | null>(null);
  const [conversoesErro, setConversoesErro] = useState<string | null>(null);
  const [catalogoDePublicos, setCatalogoDePublicos] = useState<
    { contaRef: string; envelope: EnvelopeDeCatalogoMeta<PublicoDoCatalogoMeta> } | null>(null);
  const [publicosErro, setPublicosErro] = useState<string | null>(null);
  const [catalogoDeLugares, setCatalogoDeLugares] = useState<
    { contaRef: string; envelope: EnvelopeDeCatalogoMeta<LugarDoCatalogoMeta> } | null>(null);
  const [lugaresErro, setLugaresErro] = useState<string | null>(null);
  /** Ordena as respostas de catálogo entre si, pelo mesmo motivo do selo dos
   *  ativos: duas buscas seguidas podem voltar fora de ordem. */
  const seloDosCatalogos = useRef(0);
  /** A OPERAÇÃO DURÁVEL, e ela é deliberadamente separada do rascunho.
   *
   * ⚠️ `invalidar()` derruba tudo o que descreve o rascunho — compilação,
   * validação, aprovação. A operação NÃO entra nessa lista: ela descreve o que
   * já foi despachado, e editar um campo da tela não desfaz um objeto criado
   * numa conta real. Ela é recuperada por referência opaca e sobrevive ao
   * reload.
   *
   * ⚠️ E ela viaja SEMPRE COM A REFERÊNCIA a que pertence. Guardar o recibo
   * sozinho é o que deixava uma resposta atrasada da operação A cair sobre a
   * referência B. O par é a guarda: quem escreve confere o crachá antes de
   * gravar, e quem desenha confere de novo antes de renderizar. */
  const [operacao, setOperacao] = useState<
    { referencia: string; recibo: ReciboCriacaoMeta } | null>(null);
  const [operacaoCarregando, setOperacaoCarregando] = useState(false);
  const [operacaoErro, setOperacaoErro] = useState<
    { referencia: string; mensagem: string } | null>(null);
  /** Esta sessão JÁ MANDOU criar por esta referência. Marcado ANTES do POST. */
  const [despachadaNestaSessao, setDespachadaNestaSessao] = useState<string | null>(null);
  const [confirmacaoMarcada, setConfirmacaoMarcada] = useState(false);
  const [confirmacaoDigitada, setConfirmacaoDigitada] = useState('');
  /** Qual conjunto as etapas de público e mensuração estão editando. */
  const [conjuntoFocadoRef, setConjuntoFocadoRef] = useState<string>(CHAVE_DO_PRIMEIRO_CONJUNTO);

  /** ⚠️ TRAVA SÍNCRONA de duplo clique.
   *
   * `ocupado` é `useState`: ele só chega ao DOM no render seguinte, e entre o
   * primeiro clique e esse render cabe um segundo clique inteiro. Para
   * "Validar" isso custaria uma chamada repetida que não cria nada; para
   * "Criar campanha PAUSED" custaria uma segunda campanha na conta real. */
  const emVoo = useRef(false);

  const fixarOperacaoNaUrl = useCallback((referencia: string) => {
    setParams((atuais) => {
      const proximos = new URLSearchParams(atuais);
      proximos.set('operacao', referencia);
      return proximos;
    }, { replace: true });
  }, [setParams]);

  // ⚠️ Toda resposta assíncrona carrega o selo do rascunho que a pediu. Sem
  // isso, o operador troca a URL enquanto a Meta responde e a resposta antiga
  // marca como validado um plano que já não existe.
  const selo = useRef(0);

  /** ⚠️ O SELO DA OPERAÇÃO É OUTRO SELO, e a separação é deliberada. */
  const seloDaOperacao = useRef(0);
  /** ⚠️ E O SELO DOS ATIVOS É UM TERCEIRO. Ele ordena as leituras de
   *  inventário entre si: trocar de conta duas vezes rápido faz a resposta da
   *  PRIMEIRA conta chegar por último, e sem um número por requisição ela
   *  reescreveria Página e peça da conta que está na tela agora (`A31`). */
  const seloDosAtivos = useRef(0);

  const invalidar = useCallback(() => {
    selo.current += 1;
    setCompilacao(null);
    setValidacao(null);
    // ⚠️ O resumo do servidor cai junto. Ele descreve o plano que foi
    // compilado, e mantê-lo sobre um rascunho editado faria a revisão afirmar
    // números que o corpo enviado não tem mais (`A33`).
    setResumo(null);
    // ⚠️ Editar o rascunho derruba a APROVAÇÃO junto. Uma aprovação viva
    // descreve um hash; manter o botão "Criar" habilitado depois de o operador
    // mudar o orçamento deixaria a tela oferecendo a criação de um plano que
    // ninguém aprovou.
    setAprovacao(null);
    // ⚠️ `reconciliacao` e `operacao` NÃO são limpos aqui: eles descrevem uma
    // execução que já saiu do navegador.
    setConfirmacaoMarcada(false);
    setConfirmacaoDigitada('');
    setAvisos([]);
  }, []);

  const mudar = useCallback(<K extends keyof Draft>(chave: K, valor: Draft[K]) => {
    setDraft((atual) => ({ ...atual, [chave]: valor }));
    invalidar();
  }, [invalidar]);

  useEffect(() => {
    let vivo = true;
    pautadorApi.capacidadesCriacaoMeta()
      .then((cap) => {
        if (!vivo) return;
        const bloqueios = (cap.bloqueios ?? {}) as Record<string, string>;
        setCapacidades({
          validateOnly: cap.validate_only === 'ENABLED',
          loteEstatico: String(cap.static_batch ?? '').startsWith('AVAILABLE'),
          video: cap.video_creative === 'AVAILABLE',
          videoMotivo: bloqueios.video_creative ?? null,
          flexivel: cap.flexible_creative === 'AVAILABLE',
          flexivelMotivo: bloqueios.flexible_creative ?? null,
          budgetSharingMotivo: bloqueios.adset_budget_sharing ?? null,
          // Fechado por padrão: qualquer valor que não seja exatamente
          // 'ENABLED' deixa a criação indisponível na tela.
          criarPausada: cap.create_paused === 'ENABLED',
          criarPausadaMotivo: bloqueios.create_paused ?? null,
        });
      })
      .catch((exc) => vivo && setAvisos(avisosDoErro(exc)))
      .finally(() => vivo && setCarregando(false));
    return () => { vivo = false; };
  }, []);

  /** O catálogo de receitas. LEITURA LOCAL: a rota devolve o registro do
   *  servidor e não fala com a Meta, então ela pode sair na montagem sem violar
   *  "nenhuma chamada externa sem clique explícito".
   *
   * ⚠️ A falha NÃO vira aviso de operação. Sem catálogo a bancada continua com
   * a receita provada; anunciar isso no painel de impedimentos misturaria uma
   * leitura de configuração com a recusa de um ato. */
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const lido = await pautadorApi.receitasCriacaoMetaV2();
        if (vivo) { setCatalogo(lido); setCatalogoErro(null); }
      } catch (exc) {
        if (vivo) {
          setCatalogo(null);
          setCatalogoErro(exc instanceof Error ? exc.message : 'catálogo indisponível');
        }
      }
    })();
    return () => { vivo = false; };
  }, []);

  const carregarContas = async () => {
    setCarregando(true);
    try {
      const inventario = await pautadorApi.contasMetaLocal();
      setContas(inventario.contas);
      if (inventario.contas.length === 1) mudar('accountRef', inventario.contas[0].referencia_opaca);
    } catch (exc) {
      setAvisos(avisosDoErro(exc));
    } finally {
      setCarregando(false);
    }
  };

  /** Aplica um recibo só se ele for DESTA operação e mais novo que o exibido. */
  const aplicarRecibo = useCallback(
    (referencia: string, recibo: ReciboCriacaoMeta, meuSelo: number) => {
      if (meuSelo !== seloDaOperacao.current) return;
      if (recibo.approval_id !== referencia) return;
      setOperacao({ referencia, recibo });
      setOperacaoErro(null);
    }, []);

  /** A leitura do recibo durável, com o selo tomado NA IDA. */
  const lerRecibo = useCallback(async (referencia: string) => {
    const meu = ++seloDaOperacao.current;
    setOperacaoCarregando(true);
    setOperacaoErro(null);
    try {
      const resultado = await pautadorApi.reciboCriacaoMeta(referencia);
      aplicarRecibo(referencia, resultado.recibo, meu);
    } catch (exc) {
      // ⚠️ Falha de leitura NÃO vira "nenhum recibo".
      if (meu === seloDaOperacao.current) {
        setOperacaoErro({
          referencia,
          mensagem: exc instanceof PautadorApiError
            ? exc.message
            : 'Não foi possível ler o recibo desta operação.',
        });
      }
    } finally {
      if (meu === seloDaOperacao.current) setOperacaoCarregando(false);
    }
  }, [aplicarRecibo]);

  /** REIDRATA A OPERAÇÃO a partir da referência na URL. */
  useEffect(() => {
    if (!operacaoRef) return;
    void lerRecibo(operacaoRef);
  }, [operacaoRef, lerRecibo]);

  useEffect(() => {
    if (!draft.accountRef) { setPaginas([]); setImagens([]); setVideos([]); return; }
    const contaPedida = draft.accountRef;
    const meu = ++seloDosAtivos.current;
    let vivo = true;
    setOcupado('ativos');
    pautadorApi.ativosCriacaoMeta(contaPedida)
      .then((resultado) => {
        // ⚠️ DUAS GUARDAS, e nenhuma substitui a outra: `vivo` mata a resposta
        // de um efeito desmontado; o selo mata a resposta de uma conta ANTERIOR
        // que voltou depois da atual. Sem o selo, trocar de conta duas vezes
        // rápido deixaria a Página e as peças da primeira conta em cima da
        // segunda — e o operador aprovaria um plano da conta errada.
        if (!vivo || meu !== seloDosAtivos.current) return;
        setPaginas(resultado.paginas);
        setImagens(resultado.imagens);
        setVideos(resultado.videos ?? []);
        // A releitura pode trocar Página e peça do rascunho. Isso é mudança
        // material: a compilação anterior deixa de valer.
        invalidar();
        setDraft((atual) => ({
          ...atual,
          pageRef: resultado.paginas.some((item) => item.referencia_opaca === atual.pageRef)
            ? atual.pageRef : (resultado.paginas[0]?.referencia_opaca || ''),
          // ⚠️ TROCAR DE CONTA LIMPA SELEÇÃO INVÁLIDA. Identidade do Instagram
          // e conversão personalizada são objetos DAQUELA conta: mantê-los
          // deixaria o plano carregando referências que a nova conta não
          // resolve, e o erro chegaria como "referência não encontrada" sem o
          // operador entender que a culpa foi a troca de conta.
          instagramActorRef: '',
          // ⚠️ E as referências de PÚBLICO e de LUGAR saem junto: elas foram
          // resolvidas contra o catálogo da conta anterior. `publicos.py`
          // resolve LISTANDO o catálogo da conta escolhida, então uma
          // referência da conta antiga simplesmente não bate — e a tela não
          // pode continuar exibindo uma seleção que o plano não consegue mais
          // traduzir.
          conjuntos: atual.conjuntos.map((conjunto) => ({
            ...conjunto,
            mensuracao: {
              ...conjunto.mensuracao, conversaoRef: '', fonteRef: '', fonteTipo: '',
            },
            publico: {
              ...conjunto.publico,
              incluirRefs: [], excluirRefs: [], lookalikeRefs: [],
              interesseRefs: [], localeRefs: [],
              geo: { ...conjunto.publico.geo, lugares: [] },
            },
          })),
          variations: atual.variations.map((variacao) => ({
            ...variacao,
            assetRef: resultado.imagens.some((item) => item.referencia_opaca === variacao.assetRef)
              ? variacao.assetRef : (resultado.imagens[0]?.referencia_opaca || ''),
            videoRef: (resultado.videos ?? []).some(
              (item) => item.referencia_opaca === variacao.videoRef)
              ? variacao.videoRef : ((resultado.videos ?? [])[0]?.referencia_opaca || ''),
          })),
        }));
      })
      .catch((exc) => vivo && meu === seloDosAtivos.current && setAvisos(avisosDoErro(exc)))
      .finally(() => { if (vivo && meu === seloDosAtivos.current) setOcupado(null); });
    return () => { vivo = false; };
  }, [draft.accountRef, invalidar]);

  // ⚠️ TODO catálogo pertence a UMA conta. Trocar de conta os apaga — e apaga
  // também a mensagem de erro, que descrevia a conta anterior. Manter a lista
  // deixaria o operador escolhendo, na conta nova, um público que só existe na
  // antiga: o backend recusaria a referência, e a tela teria oferecido.
  useEffect(() => {
    const daConta = <T,>(atual: { contaRef: string } & T) => (
      atual.contaRef === draft.accountRef ? atual : null);
    setCatalogoDeMensuracao((atual) => (atual ? daConta(atual) : null));
    setCatalogoDePublicos((atual) => (atual ? daConta(atual) : null));
    setCatalogoDeLugares((atual) => (atual ? daConta(atual) : null));
    setConversoesErro(null);
    setPublicosErro(null);
    setLugaresErro(null);
  }, [draft.accountRef]);

  const mudarVariacao = <K extends keyof VariacaoDraft>(
    posicaoAlvo: number, chave: K, valor: VariacaoDraft[K],
  ) => {
    setDraft((atual) => ({
      ...atual,
      variations: atual.variations.map((item, posicao) => (
        posicao === posicaoAlvo ? {
          ...item,
          [chave]: valor,
          ...((chave === 'assetRef' || chave === 'videoRef' || chave === 'midia') ? {
            assetRightsConfirmed: false,
            thirdPartyIdentityCleared: false,
            assetPolicyConfirmedAt: '',
          } : {}),
        } : item
      )),
    }));
    invalidar();
  };
  const mudarPoliticaDaPeca = (
    posicaoAlvo: number,
    chave: 'assetRightsConfirmed' | 'thirdPartyIdentityCleared',
    valor: boolean,
  ) => {
    setDraft((atual) => ({
      ...atual,
      variations: atual.variations.map((item, posicao) => {
        if (posicao !== posicaoAlvo) return item;
        const proximo = { ...item, [chave]: valor };
        return {
          ...proximo,
          assetPolicyConfirmedAt: proximo.assetRightsConfirmed
            && proximo.thirdPartyIdentityCleared ? new Date().toISOString() : '',
        };
      }),
    }));
    invalidar();
  };
  const adicionarVariacao = (origem?: number) => {
    setDraft((atual) => {
      if (atual.variations.length >= LIMITE_VARIACOES) return atual;
      const chave = proximaChave(atual.variations.map((item) => item.key), 'variation');
      const numero = atual.variations.length + 1;
      const padrao = atual.conjuntos[0]?.key ?? '';
      const base = origem === undefined
        ? { ...variacaoInicial(chave, numero, padrao), ...pecaPadrao(atual) }
        : { ...atual.variations[origem], key: chave };
      return {
        ...atual,
        creativeMode: 'batch',
        variations: [...atual.variations, {
          ...base,
          key: chave,
          creativeName: nomeUnico(base.creativeName, atual.variations.map((i) => i.creativeName)),
          adName: nomeUnico(base.adName, atual.variations.map((i) => i.adName)),
        }],
      };
    });
    invalidar();
  };
  const removerVariacao = (posicaoAlvo: number) => {
    setDraft((atual) => {
      const restantes = atual.variations.filter((_, posicao) => posicao !== posicaoAlvo);
      return {
        ...atual,
        creativeMode: restantes.length === 1 ? 'single' : atual.creativeMode,
        variations: restantes,
      };
    });
    invalidar();
  };
  /** Trocar de modo muda o que será EMITIDO, não o que está guardado. */
  const mudarModo = (modo: Draft['creativeMode']) => {
    setDraft((atual) => ({ ...atual, creativeMode: modo }));
    invalidar();
  };
  function pecaPadrao(atual: Draft): Partial<VariacaoDraft> {
    const ultima = atual.variations.at(-1);
    return { assetRef: ultima?.assetRef ?? '', videoRef: ultima?.videoRef ?? '', midia: ultima?.midia ?? 'image' };
  }

  // ── Conjuntos ─────────────────────────────────────────────────────────────
  const mudarConjunto = useCallback((chave: string, patch: Partial<ConjuntoDraft>) => {
    setDraft((atual) => ({
      ...atual,
      conjuntos: atual.conjuntos.map(
        (item) => (item.key === chave ? { ...item, ...patch } : item)),
    }));
    invalidar();
  }, [invalidar]);

  const adicionarConjunto = (origem?: string) => {
    setDraft((atual) => {
      if (atual.conjuntos.length >= LIMITE_CONJUNTOS) return atual;
      const chave = proximaChave(atual.conjuntos.map((item) => item.key), 'adset');
      const base = origem
        ? atual.conjuntos.find((item) => item.key === origem)
        : undefined;
      const modelo = base
        ? { ...base, key: chave }
        : conjuntoInicial(
          chave, `Conjunto ${atual.conjuntos.length + 1}`,
          atual.conjuntos[0]?.startTime ?? inicioPadrao(),
          atual.conjuntos[0]?.orcamentoBrl ?? '10,00');
      return {
        ...atual,
        conjuntos: [...atual.conjuntos, {
          ...modelo,
          key: chave,
          nome: nomeUnico(modelo.nome, atual.conjuntos.map((item) => item.nome)),
        }],
      };
    });
    invalidar();
  };

  const removerConjunto = (chave: string) => {
    setDraft((atual) => (atual.conjuntos.length === 1 ? atual : {
      ...atual,
      conjuntos: atual.conjuntos.filter((item) => item.key !== chave),
    }));
    invalidar();
  };

  /** ⚠️ REORDENAR MOVE A POSIÇÃO, NUNCA A IDENTIDADE. Nenhuma chave é
   *  recalculada aqui, e por isso todo anúncio continua apontando para o mesmo
   *  conjunto depois do movimento. */
  const moverConjunto = (chave: string, direcao: -1 | 1) => {
    setDraft((atual) => {
      const de = atual.conjuntos.findIndex((item) => item.key === chave);
      const para = de + direcao;
      if (de < 0 || para < 0 || para >= atual.conjuntos.length) return atual;
      const proximos = [...atual.conjuntos];
      [proximos[de], proximos[para]] = [proximos[para], proximos[de]];
      return { ...atual, conjuntos: proximos };
    });
    invalidar();
  };

  /** A troca de modo de orçamento, já CONFIRMADA pelo painel.
   *
   * ⚠️ Nenhum valor é convertido: trocar diário por total não divide nem
   * multiplica o número que a pessoa escreveu. O que muda é o significado, e
   * quem decide o novo número é ela. */
  const trocarModoDeOrcamento = (nivel: NivelDeOrcamento, periodo: PeriodoDeOrcamento) => {
    setDraft((atual) => ({ ...atual, nivelDeOrcamento: nivel, periodoDeOrcamento: periodo }));
    invalidar();
  };

  const navegar = (proxima: EtapaId) => {
    const novos = new URLSearchParams(params);
    novos.set('etapa', proxima);
    setParams(novos);
    const reduzido = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduzido ? 'auto' : 'smooth' });
  };

  const conta = contas.find((item) => item.referencia_opaca === draft.accountRef);
  const pagina = paginas.find((item) => item.referencia_opaca === draft.pageRef);
  const emitidas = variacoesEmitidas(draft);
  const receitas = catalogo?.receitas ?? [];
  const receita = receitas.find((item) => item.id === draft.recipeId) ?? null;
  /** ⚠️ Memorizado porque `prontidaoDasEtapas` depende dele: um array novo a
   *  cada render recalcularia a prontidão de todas as etapas em todo teclado. */
  const propositosDaReceita = useMemo<readonly PropositoDeMensuracao[]>(
    () => receita?.propositos_de_mensuracao ?? [], [receita]);
  const limitesDeIdade = {
    min: catalogo?.idade.min ?? IDADE_MINIMA_PADRAO,
    max: catalogo?.idade.max ?? IDADE_MAXIMA_PADRAO,
    motivo: catalogo?.idade.motivo ?? null,
  };
  /** ⚠️ Qual contrato este rascunho fala, e por quê. A revisão mostra os dois. */
  const { contrato, motivos: motivosDoV2 } = contratoDoPlano(draft);
  const conjuntoFocado = draft.conjuntos.find((item) => item.key === conjuntoFocadoRef)
    ?? draft.conjuntos[0];
  const resumoDoFocado = resumo?.conjuntos.find(
    (item) => item.adset_key === conjuntoFocado?.key) ?? null;

  const estados = useMemo(
    () => prontidaoDasEtapas(draft, {
      capacidades,
      compilado: Boolean(compilacao),
      validado: Boolean(validacao?.ok),
      propositosDaReceita,
    }),
    [draft, capacidades, compilacao, validacao, propositosDaReceita],
  );
  const podeCompilar = prontoParaCompilar(draft, capacidades, propositosDaReceita);

  /** O que ainda impede o próximo ato — inteiro, em linguagem de operador. */
  const faltas = useMemo(() => {
    const lista: string[] = [];
    if (!draft.accountRef) lista.push('Escolha a conta de anúncios.');
    if (!draft.pageRef) lista.push('Escolha a Página que assina os anúncios.');
    if (!draft.campaignName.trim()) lista.push('Dê um nome à campanha.');
    if (!draft.categoryConfirmed) lista.push('Confirme o enquadramento de categoria especial.');
    const varios = draft.conjuntos.length > 1;
    const palavraDaVerba = draft.periodoDeOrcamento === 'DAILY' ? 'diário' : 'total';
    orcamentosDoPlano(draft).forEach((item) => {
      if (item.minor <= 0) {
        lista.push(`Informe um orçamento ${palavraDaVerba} maior que zero${
          varios && draft.nivelDeOrcamento === 'ADSET' ? ` no conjunto "${item.rotulo}"` : ''}.`);
      }
    });
    draft.conjuntos.forEach((conjunto) => {
      const onde = varios ? ` do conjunto "${conjunto.nome || 'sem nome'}"` : '';
      if (!conjunto.nome.trim()) lista.push('Dê um nome ao conjunto.');
      if (!inicioEmIso(conjunto.startTime)) {
        lista.push(`Informe uma data e hora de início válidas${onde}.`);
      }
      if (draft.periodoDeOrcamento === 'LIFETIME' && !inicioEmIso(conjunto.endTime)) {
        lista.push(`Orçamento total exige data de término${onde}.`);
      }
      if (!emitidas.some((item) => item.adsetKey === conjunto.key)) {
        lista.push(
          `Nenhum anúncio aponta para o conjunto "${conjunto.nome || 'sem nome'}"; `
          + 'um conjunto sem anúncio é recusado pelo backend.');
      }
      if (conjunto.posicionamentoValores.includes('instagram') && !draft.instagramActorRef) {
        lista.push(BLOQUEIOS.identidadeInstagram);
      }
      if (conjunto.posicionamentoModo === 'MANUAL' && conjunto.posicionamentoValores.length === 0) {
        lista.push(`Escolha ao menos uma plataforma${onde}.`);
      }
      if (conjunto.mensuracao.proposito === 'OPTIMIZE' && !conjunto.mensuracao.fonteRef) {
        lista.push(BLOQUEIOS.fonteDeMensuracao);
      }
    });
    if (estados.publico !== 'pronto') {
      lista.push('Confira o público: escolha ao menos um lugar para alcançar e uma faixa etária válida.');
    }
    if (estados.mensuracao !== 'pronto') lista.push('Informe uma URL de destino HTTPS válida.');
    if (draft.creativeMode === 'flexible') {
      lista.push('O criativo flexível não emite payload: escolha Individual ou Lote.');
    } else {
      if (emitidas.some((item) => item.midia === 'video')) {
        lista.push(`Um anúncio usa vídeo. ${BLOQUEIOS.videoNoCorpo}`);
      }
      const chaves = new Set(draft.conjuntos.map((item) => item.key));
      emitidas.forEach((item, posicao) => {
        if (!chaves.has(item.adsetKey)) {
          lista.push(`O anúncio ${posicao + 1} aponta para um conjunto que não existe mais.`);
        }
        if (!variacaoCompleta(item) && item.midia !== 'video') {
          lista.push(`O anúncio ${posicao + 1} está incompleto.`);
        }
      });
    }
    return [...new Set(lista)];
  }, [draft, estados, emitidas]);

  /** ⚠️ UMA PORTA POR CONTRATO, e a escolha é a forma do plano.
   *
   * A resposta do V2 carrega `resumo`; a do V1 não tem esse campo, e a revisão
   * do V1 continua sendo a que sempre foi. Fundir os dois numa chamada só faria
   * um plano de conjunto único perder a rota que ainda sustenta aprovação e
   * criação PAUSED. */
  const compilar = async () => {
    const meu = ++selo.current;
    setOcupado('compilar');
    setAvisos([]);
    try {
      if (contrato === 'V2') {
        const resultado = await pautadorApi.compilarPlanoMetaV2(paraPlanoV2(draft));
        if (meu !== selo.current) return;
        setCompilacao(resultado);
        setResumo(resultado.resumo);
      } else {
        const resultado = await pautadorApi.compilarPlanoMeta(paraPlano(draft));
        if (meu !== selo.current) return;
        setCompilacao(resultado);
        setResumo(null);
      }
      setValidacao(null);
    } catch (exc) {
      if (meu === selo.current) setAvisos(avisosDoErro(exc));
    } finally {
      // ⚠️ SEM condição: descartar a RESPOSTA obsoleta é correto; deixar a tela
      // ocupada por causa dela, não.
      setOcupado(null);
    }
  };

  const validar = async () => {
    const meu = ++selo.current;
    setOcupado('validar');
    setAvisos([]);
    try {
      if (contrato === 'V2') {
        const resultado = await pautadorApi.validarPlanoMetaV2(paraPlanoV2(draft));
        if (meu !== selo.current) return;
        setValidacao(resultado);
        setResumo(resultado.resumo);
      } else {
        const resultado = await pautadorApi.validarPlanoMeta(paraPlano(draft));
        if (meu !== selo.current) return;
        setValidacao(resultado);
      }
    } catch (exc) {
      if (meu === selo.current) setAvisos(avisosDoErro(exc));
    } finally {
      setOcupado(null);
    }
  };

  /** Um catálogo da conta. LEITURA REAL, e por isso SÓ POR CLIQUE.
   *
   * ⚠️ Três guardas, e nenhuma substitui a outra:
   *  · a conta é capturada NA IDA e viaja com o resultado — uma resposta lenta
   *    da conta A não pode pousar sobre a conta B;
   *  · o selo descarta a resposta de uma busca ANTERIOR que voltou por último;
   *  · a falha vira ERRO DE LEITURA nomeado, nunca "nenhum item": a conta pode
   *    ter exatamente o que a consulta não conseguiu ver.
   *
   * ⚠️ E nada disto sai da montagem da página. `_exigir_host_local` e o custo
   * real da leitura (nove requisições paginadas por clique no preflight desta
   * lane) fazem do carregamento automático um multiplicador, não uma
   * conveniência. */
  const lerCatalogo = async <T,>(
    rotulo: 'conversoes' | 'publicos' | 'lugares',
    ler: (contaRef: string) => Promise<T>,
    aplicar: (contaRef: string, resultado: T) => void,
    aoFalhar: (mensagem: string) => void,
    mensagemPadrao: string,
  ) => {
    const contaPedida = draft.accountRef;
    if (!contaPedida) return;
    const meu = ++seloDosCatalogos.current;
    setOcupado(rotulo);
    aoFalhar('');
    try {
      const resultado = await ler(contaPedida);
      if (meu !== seloDosCatalogos.current) return;
      aplicar(contaPedida, resultado);
    } catch (exc) {
      if (meu !== seloDosCatalogos.current) return;
      aoFalhar(exc instanceof Error ? exc.message : mensagemPadrao);
    } finally {
      // Sem condição: descartar a RESPOSTA obsoleta é correto; deixar a
      // bancada ocupada por causa dela, não.
      setOcupado(null);
    }
  };

  const lerConversoes = () => lerCatalogo(
    'conversoes',
    (contaRef) => pautadorApi.catalogoDeMensuracaoMeta(contaRef),
    (contaRef, resultado) => setCatalogoDeMensuracao({
      contaRef, fontes: resultado.fontes, conversoes: resultado.conversoes,
    }),
    (mensagem) => setConversoesErro(mensagem || null),
    'Não foi possível ler a mensuração desta conta.',
  );

  const lerPublicos = () => lerCatalogo(
    'publicos',
    (contaRef) => pautadorApi.catalogoDePublicosMeta(contaRef),
    (contaRef, envelope) => setCatalogoDePublicos({ contaRef, envelope }),
    (mensagem) => setPublicosErro(mensagem || null),
    'Não foi possível ler os públicos desta conta.',
  );

  /** ⚠️ O TERMO É BUSCA, NUNCA CHAVE. O que volta do catálogo é que carrega a
   *  `key` canônica; o texto digitado nunca entra no plano. */
  const buscarLugares = (termo: string) => lerCatalogo(
    'lugares',
    (contaRef) => pautadorApi.catalogoDeGeografiaMeta({ referenciaOpaca: contaRef, termo }),
    (contaRef, envelope) => setCatalogoDeLugares({ contaRef, envelope }),
    (mensagem) => setLugaresErro(mensagem || null),
    'Não foi possível buscar lugares no catálogo da Meta.',
  );

  /** Envolve um ato que não pode sair duas vezes do navegador. */
  const umaVezSo = async (
    rotulo: 'aprovar' | 'criar' | 'reconciliar',
    ato: (aindaEDoMesmoRascunho: () => boolean) => Promise<void>,
  ) => {
    if (emVoo.current) return;
    emVoo.current = true;
    const meu = ++selo.current;
    const meuAinda = () => meu === selo.current;
    setOcupado(rotulo);
    setAvisos([]);
    try {
      await ato(meuAinda);
    } catch (exc) {
      if (meuAinda()) setAvisos(avisosDoErro(exc));
    } finally {
      emVoo.current = false;
      setOcupado(null);
    }
  };

  const aprovar = () => umaVezSo('aprovar', async (aindaEDoMesmoRascunho) => {
    const prova = validacao?.prova_duravel;
    if (!validacao?.ok || !prova?.registrada || !prova.validation_id) {
      throw new PautadorApiError(
        'A validação desta versão não foi gravada como prova durável. Valide de novo '
        + 'antes de aprovar.', 409);
    }
    const resultado = await pautadorApi.aprovarCriacaoMeta({
      plano: paraPlano(draft),
      planoSha256: validacao.plano_sha256,
      validationId: prova.validation_id,
      confirmacaoDigitada,
    });
    // ⚠️ APROVAR ainda não criou nada, então a resposta obsoleta é DESCARTADA.
    if (!aindaEDoMesmoRascunho()) return;
    setAprovacao(resultado.aprovacao);
  });

  const criar = () => umaVezSo('criar', async () => {
    if (!aprovacao) return;
    const referencia = aprovacao.approval_id;
    // ⚠️ A REFERÊNCIA ENTRA NA URL ANTES DO DESPACHO, e a ordem é o conserto.
    fixarOperacaoNaUrl(referencia);
    // ⚠️ MARCADO ANTES DO POST: se o despacho falhar, ele PODE ter criado
    // objetos — e o botão de criar precisa fechar de qualquer jeito.
    setDespachadaNestaSessao(referencia);
    try {
      const resultado = await pautadorApi.criarCampanhaPausadaMeta(
        referencia, aprovacao.plano_sha256);
      // ⚠️ AQUI A RESPOSTA NUNCA É DESCARTADA: o despacho JÁ ACONTECEU.
      aplicarRecibo(referencia, resultado.recibo, ++seloDaOperacao.current);
    } catch (exc) {
      // ⚠️ UM DESPACHO QUE FALHA PODE TER CRIADO OBJETOS.
      await lerRecibo(referencia);
      throw exc;
    }
  });

  const reconciliar = () => umaVezSo('reconciliar', async () => {
    const referencia = operacaoRef || aprovacao?.approval_id;
    if (!referencia) return;
    const resultado = await pautadorApi.reconciliarCriacaoMeta(referencia);
    setReconciliacao({ referencia, resultado });
    aplicarRecibo(referencia, resultado.recibo, ++seloDaOperacao.current);
    fixarOperacaoNaUrl(referencia);
  });

  const referenciaAlvo = operacaoRef || aprovacao?.approval_id || null;

  const reciboVigente =
    operacao && referenciaAlvo && operacao.referencia === referenciaAlvo
      ? operacao.recibo
      : null;
  const leituraDaOperacao = useMemo(() => lerOperacao(reciboVigente), [reciboVigente]);
  const desfechoDaOperacao = reciboVigente ? fraseDaOperacao(leituraDaOperacao) : null;

  const jaDespachou = despachadaNestaSessao === referenciaAlvo
    || (reciboVigente?.steps.length ?? 0) > 0;
  const porQueNaoCriar = !jaDespachou
    ? null
    : (leituraDaOperacao.estado.tipo === 'CONFIRMADA'
      || leituraDaOperacao.estado.tipo === 'CRIADA_SEM_LEITURA')
      ? 'Esta aprovação já criou os objetos.'
      : 'Esta aprovação já despachou; repetir duplicaria. A saída é reconciliar por leitura.';
  const podeReconciliar = Boolean(referenciaAlvo);

  /** ⚠️ CRIAR SÓ EXISTE NO V1, e a razão é o backend, não uma preferência.
   *
   * `/criacao/aprovar` recebe `PedidoPlanoMetaPausado` — o DTO do contrato V1.
   * Não existe rota de aprovação para o plano V2. Deixar o painel de criação
   * aberto sobre um plano V2 ofereceria um ato que a rota recusaria pelo hash,
   * e a tela não pode depender dessa recusa para não mentir. */
  const criacaoDisponivel = capacidades.criarPausada && contrato === 'V1';

  const totalDeAnuncios = emitidas.length;
  const linhasDoPedido: LinhaDoPedido[] = [
    { rotulo: 'Conta', valor: conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : null, fonte: 'a Meta, agora' },
    { rotulo: 'Página', valor: pagina?.nome ?? null, fonte: 'a Meta, agora' },
    { rotulo: 'Campanha', valor: draft.campaignName || null, fonte: 'você, agora' },
    { rotulo: 'Receita', valor: receita ? receita.rotulo : draft.recipeId, fonte: receita ? 'o registro de receitas' : 'a receita padrão' },
    { rotulo: 'Contrato do plano', valor: contrato === 'V1' ? 'V1 · receita provada, criação liberada pelo servidor' : 'V2 · N conjuntos; criação não existe neste contrato', fonte: 'a forma deste plano' },
    {
      rotulo: draft.periodoDeOrcamento === 'DAILY' ? 'Orçamento diário' : 'Orçamento total',
      valor: (() => {
        const linhas = orcamentosDoPlano(draft).filter((item) => item.minor > 0);
        if (!linhas.length) return null;
        const onde = draft.nivelDeOrcamento === 'CAMPAIGN' ? 'na campanha' : 'no conjunto';
        return linhas.length === 1
          ? `${formatarBrl(linhas[0].minor)} · ${onde}`
          : linhas.map((item) => `${item.rotulo}: ${formatarBrl(item.minor)}`).join(' · ');
      })(),
      fonte: 'você, agora',
    },
    { rotulo: 'Onde a verba mora', valor: resumo ? resumo.orcamento.onde_a_verba_mora : null, fonte: 'o resumo do backend' },
    { rotulo: 'Compartilhar verba entre conjuntos', valor: 'Não · o contrato recusa true', fonte: 'a Meta, na validação real' },
    { rotulo: 'Advantage+ público', valor: draft.conjuntos.map((item) => (item.publico.expansao ? 'Aceito' : 'Recusado')).join(' · '), fonte: 'você, agora' },
    { rotulo: 'Estrutura', valor: `1 campanha · ${draft.conjuntos.length} conjunto${draft.conjuntos.length === 1 ? '' : 's'} · ${totalDeAnuncios} criativo${totalDeAnuncios === 1 ? '' : 's'} · ${totalDeAnuncios} anúncio${totalDeAnuncios === 1 ? '' : 's'}`, fonte: 'o compilador' },
    { rotulo: 'Estado ao nascer', valor: 'Pausada em todos os níveis veiculáveis', fonte: 'a receita provada' },
    { rotulo: 'Plano compilado', valor: compilacao ? `${compilacao.plano.plano_sha256.slice(0, 16)}…` : null, fonte: 'o backend' },
    { rotulo: 'Validação na Meta', valor: validacao?.ok ? `Aceita · ${validacao.operacoes_validadas.length} de ${validacao.operacoes_validadas.length + validacao.operacoes_dependentes_pendentes.length} operações` : null, fonte: 'a Meta' },
  ];

  const proximoAto = jaDespachou
    ? 'Nada mais nesta bancada: ativar é um ato separado e não existe aqui.'
    : aprovacao
      ? 'Criar a campanha PAUSED. Os objetos passam a existir, e nenhum veicula.'
      : validacao?.ok
        ? criacaoDisponivel
          ? 'Confirmar e aprovar o plano. Aprovar ainda não cria nada.'
          : contrato === 'V2'
            ? 'Nada mais nesta bancada: o contrato V2 não tem rota de criação.'
            : 'Nada mais nesta bancada: a criação PAUSED está fechada neste servidor.'
        : compilacao
          ? 'Validar na Meta, sem criar nenhum objeto.'
          : faltas.length > 0 ? null : 'Conferir o plano no backend.';

  /** Rótulos legíveis por `variation_key`, para o mapa da revisão. O resumo
   *  identifica por chave; nome é rótulo, não afirmação sobre o plano. */
  const rotuloDoAnuncio = (chave: string) => {
    const variacao = draft.variations.find((item) => item.key === chave);
    const lista = variacao?.midia === 'video' ? videos : imagens;
    const escolhida = variacao?.midia === 'video' ? variacao?.videoRef : variacao?.assetRef;
    return {
      anuncio: variacao?.adName || chave,
      peca: lista.find((item) => item.referencia_opaca === escolhida)?.nome ?? null,
    };
  };

  /** O seletor de conjunto das etapas por conjunto. Só aparece quando há mais
   *  de um: um seletor de um item só é ruído. */
  const trilhoDeConjuntos = draft.conjuntos.length > 1 && conjuntoFocado ? (
    <GrupoDeEscolha<string>
      rotuloAcessivel="Conjunto em edição"
      valor={conjuntoFocado.key}
      colunas="sm:grid-cols-2 lg:grid-cols-3"
      onEscolher={setConjuntoFocadoRef}
      opcoes={draft.conjuntos.map((item, posicao) => ({
        id: item.key,
        nome: item.nome || `Conjunto ${posicao + 1}`,
        detalhe: `conjunto ${posicao + 1} de ${draft.conjuntos.length}`,
      }))}
    />
  ) : null;

  const conteudo = (() => {
    switch (etapa) {
      case 'base': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-conta" rotulo="Conta de anúncios" ajuda="Só contas ativas em reais entram nesta receita. O navegador recebe uma referência, nunca o identificador da conta.">
              <select id="meta-conta" className={campo} value={draft.accountRef} disabled={carregando}
                onChange={(e) => mudar('accountRef', e.target.value)}>
                <option value="">Selecione uma conta real</option>
                {contas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado || 'ID protegido'} · {item.moeda || 'moeda não lida'}
                  </option>
                ))}
              </select>
              <Button type="button" variant="outline" className="mt-2" disabled={carregando}
                onClick={carregarContas}>Ler contas na Meta</Button>
            </Campo>
            <Campo id="meta-pagina" rotulo="Página do Facebook" ajuda="A Página assina os anúncios e precisa estar disponível para promoção nesta conta.">
              <select id="meta-pagina" className={campo} value={draft.pageRef}
                disabled={!draft.accountRef || ocupado === 'ativos'}
                onChange={(e) => mudar('pageRef', e.target.value)}>
                <option value="">Selecione uma Página desta conta</option>
                {paginas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
          <BlocoDeEvidencia titulo="O que foi lido da conta" tom="verificado">
            <LinhaDeFato rotulo="Moeda" valor={conta?.moeda ?? null} fonte="a Meta" ausencia="não lida" />
            <LinhaDeFato rotulo="Fuso da conta" valor={conta?.fuso ?? null} fonte="a Meta" ausencia="não lido" />
            <LinhaDeFato rotulo="Imagens disponíveis" valor={draft.accountRef ? imagens.length : null} fonte="a Meta" ausencia="não lidas" />
            <LinhaDeFato rotulo="Vídeos disponíveis" valor={draft.accountRef ? videos.length : null} fonte="a Meta" ausencia="não lidos" />
            {/* ⚠️ Identidade do Instagram: ausência DECLARADA, não silêncio. Sem
                ela o posicionamento no Instagram é recusado pelo backend, e a
                etapa de público mostra a caixa fechada com esta mesma causa. */}
            <LinhaDeFato rotulo="Identidade do Instagram" valor={draft.instagramActorRef || null} fonte="a Meta" ausencia="não lida por esta bancada" />
          </BlocoDeEvidencia>
        </>
      );
      case 'campanha': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-nome" rotulo="Nome da campanha" largo>
              <Input id="meta-nome" value={draft.campaignName}
                onChange={(e) => mudar('campaignName', e.target.value)} />
            </Campo>
            <Escolha marcado={draft.categoryConfirmed} onChange={(v) => mudar('categoryConfirmed', v)}
              titulo="Confirmo que esta campanha não é de crédito, emprego, moradia nem política">
              Declarar a ausência de categoria especial também é uma declaração. Esta bancada não
              tem caminho para DECLARAR uma categoria: o backend recusa qualquer uma delas
              (META_SPECIAL_CATEGORY_RECIPE_UNPROVEN), porque exigem público, texto e conferência
              próprios que esta receita ainda não prova. O que a caixa afirma é a AUSÊNCIA delas, e
              é uma lista vazia que viaja no corpo enviado.
            </Escolha>
          </div>
          <PainelDeReceita
            receitas={receitas}
            erroDoCatalogo={catalogoErro}
            escolhida={draft.recipeId}
            onEscolher={(id) => mudar('recipeId', id)}
          />
        </>
      );
      case 'orcamento': return (
        <PainelDeOrcamento
          draft={draft}
          modos={receita?.modos_de_orcamento ?? []}
          resumo={resumo}
          onTrocarModo={trocarModoDeOrcamento}
          onValorDaCampanha={(texto) => mudar('budgetBrl', texto)}
          onValorDoConjunto={(chave, texto) => mudarConjunto(chave, { orcamentoBrl: texto })}
          motivoDoCompartilhamento={capacidades.budgetSharingMotivo}
        />
      );
      case 'conjunto': return (
        <PainelDeConjuntos
          draft={draft}
          emitidas={emitidas}
          onCampo={(chave, qual, valor) => mudarConjunto(chave, { [qual]: valor } as Partial<ConjuntoDraft>)}
          onAdicionar={adicionarConjunto}
          onRemover={removerConjunto}
          onMover={moverConjunto}
        />
      );
      case 'publico': return conjuntoFocado ? (
        <>
          {trilhoDeConjuntos}
          <PainelDePublico
            draft={draft}
            conjunto={conjuntoFocado}
            idade={limitesDeIdade}
            resumoDoConjunto={resumoDoFocado}
            onConjunto={mudarConjunto}
            catalogoDePublicos={catalogoDePublicos?.contaRef === draft.accountRef
              ? catalogoDePublicos.envelope : null}
            lendoPublicos={ocupado === 'publicos'}
            erroDosPublicos={publicosErro}
            onLerPublicos={lerPublicos}
            catalogoDeLugares={catalogoDeLugares?.contaRef === draft.accountRef
              ? catalogoDeLugares.envelope : null}
            lendoLugares={ocupado === 'lugares'}
            erroDosLugares={lugaresErro}
            onBuscarLugares={buscarLugares}
          />
        </>
      ) : null;
      case 'criativo': return (
        <>
          <div>
            <div className="grid gap-2 rounded-lg border border-border bg-muted p-1 sm:grid-cols-3"
              role="radiogroup" aria-label="Modo de criativo">
              {([
                ['single', 'Individual', 'um anúncio'],
                ['batch', 'Lote controlado', `até ${LIMITE_VARIACOES} anúncios`],
                ['flexible', 'Flexível', 'inspeção do contrato'],
              ] as const).map(([id, nome, detalhe]) => (
                <button key={id} type="button" role="radio" aria-checked={draft.creativeMode === id}
                  onClick={() => mudarModo(id)}
                  className={cn(
                    'min-h-14 rounded-md px-3 py-2 text-left transition-volc duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    draft.creativeMode === id
                      ? 'bg-card text-foreground shadow-card'
                      : 'text-muted-foreground hover:text-foreground',
                  )}>
                  <strong className="block text-sm">{nome}</strong>
                  <span className="block text-sm">{detalhe}</span>
                </button>
              ))}
            </div>
            <p id="meta-limite-lote" className="mt-2 text-sm text-muted-foreground">
              <strong>{emitidas.length} de {LIMITE_VARIACOES}</strong> anúncios serão emitidos.
              Cada linha vira exatamente um criativo e um anúncio; não existe combinação implícita.
              O limite de {LIMITE_VARIACOES} é uma contenção operacional da VOLC, não um limite da Meta.
            </p>
          </div>

          {draft.creativeMode === 'flexible' ? (
            <>
              <PainelDeBloqueio
                titulo="Criativo flexível não emite payload"
                bloqueios={[{
                  codigo: 'META_ASSET_FEED_SPEC_UNPROVEN', severidade: 'alta',
                  titulo: 'Falta uma prova oficial para montar o criativo dinâmico',
                  detalhe: capacidades.flexivelMotivo
                    || 'O servidor não informou a causa do bloqueio.',
                }]}
              />
              <BlocoDeEvidencia titulo="O que já está provado do contrato flexível" tom="verificado">
                <LinhaDeFato rotulo="Formato do anúncio" valor="Obrigatório, um único formato por conjunto de peças" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="URLs de destino" valor="Obrigatórias, até 5" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Chamadas para ação" valor="Obrigatórias neste objetivo, até 5" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Imagens" valor="Obrigatórias no formato de imagem única, até 10" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Textos, títulos e descrições" valor="Opcionais, até 5 cada" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Chave interna da Meta e o resto" valor="Ainda sem prova pública" fonte="documentação Meta v26" ausencia="não comprovado" />
              </BlocoDeEvidencia>
            </>
          ) : (
            <div className="space-y-5">
              {/* ⚠️ O bloqueio de vídeo é do CONTRATO, não da capacidade: nem
                  `variations[]` (V1) nem `ads[]` (V2) têm campo de vídeo. Mesmo
                  que o servidor liberasse a capacidade, o corpo sairia com a
                  peça vazia. A capacidade continua sendo mostrada porque ela
                  explica a segunda metade do bloqueio. */}
              <PainelDeBloqueio
                titulo="Anúncio em vídeo não pode ser emitido"
                bloqueios={[{
                  codigo: 'META_VIDEO_NOT_IN_CONTRACT', severidade: 'alta',
                  titulo: 'Nenhum dos dois contratos transporta vídeo',
                  detalhe: `${BLOQUEIOS.videoNoCorpo}${
                    capacidades.video ? '' : ` ${capacidades.videoMotivo || ''}`}`,
                }]}
              />
              {draft.variations.slice(0, draft.creativeMode === 'single' ? 1 : undefined).map((variacao, posicao) => {
                const lista = variacao.midia === 'video' ? videos : imagens;
                const escolhida = variacao.midia === 'video' ? variacao.videoRef : variacao.assetRef;
                const ativo = lista.find((item) => item.referencia_opaca === escolhida);
                return (
                  <section key={variacao.key} className="overflow-hidden rounded-lg border border-border bg-muted/20">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                      <div className="min-w-0">
                        <p className="kicker">Anúncio {posicao + 1}</p>
                        <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
                          {variacao.headline || 'Sem título'}
                        </p>
                        <p className="sr-only" data-testid="variacao-chave">{variacao.key}</p>
                        <p className="sr-only" data-testid="variacao-conjunto">{variacao.adsetKey}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <ChipDeEstado
                          glifo={variacaoCompleta(variacao) ? CircleCheck : CircleDot}
                          palavra={variacaoCompleta(variacao) ? 'completo' : 'incompleto'}
                          descricao={variacaoCompleta(variacao)
                            ? 'este anúncio tem peça, textos e chamada para ação'
                            : 'falta preencher pelo menos um campo deste anúncio'}
                          tom={variacaoCompleta(variacao) ? 'bom' : 'atencao'}
                        />
                        {draft.creativeMode === 'batch' && (
                          <>
                            <Button type="button" variant="ghost" size="sm"
                              aria-describedby="meta-limite-lote"
                              disabled={draft.variations.length >= LIMITE_VARIACOES}
                              onClick={() => adicionarVariacao(posicao)}>
                              <Copy className="mr-1.5 h-4 w-4" aria-hidden />Duplicar
                            </Button>
                            <Button type="button" variant="ghost" size="sm"
                              disabled={draft.variations.length === 1}
                              onClick={() => removerVariacao(posicao)}>
                              <Trash2 className="mr-1.5 h-4 w-4" aria-hidden />Remover
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="grid gap-5 p-4 lg:grid-cols-[minmax(190px,30%)_1fr]">
                      <div>
                        <PreviaDaPeca accountRef={draft.accountRef} ativo={ativo} />
                        {/* ⚠️ `A30`: o nome fica curto e truncado, com o valor
                            inteiro no `title`. Um caminho de armazenamento como
                            título estoura a coluna e empurra o controle para
                            fora da tela. */}
                        <p className="mt-2 max-w-full truncate text-sm font-medium text-foreground"
                          title={ativo?.nome || undefined}>
                          {ativo?.nome || 'Escolha uma peça'}
                        </p>
                        {ativo?.largura && ativo?.altura && (
                          <p className="text-sm text-muted-foreground">{ativo.largura} × {ativo.altura} px</p>
                        )}
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        {/* ⚠️ `F34`: o conjunto de cada anúncio é ESCOLHA
                            explícita. Sem ela o backend teria de adivinhar um
                            pai, e adivinhar significa entregar no lugar errado
                            sem ninguém perceber. */}
                        <Campo id={`meta-conjunto-${posicao}`} rotulo="Conjunto deste anúncio" largo
                          ajuda="Cada anúncio nasce dentro de exatamente um conjunto, e é ele que define público, verba e posicionamento deste anúncio.">
                          <select id={`meta-conjunto-${posicao}`} className={campo}
                            value={variacao.adsetKey}
                            onChange={(e) => mudarVariacao(posicao, 'adsetKey', e.target.value)}>
                            {!draft.conjuntos.some((item) => item.key === variacao.adsetKey) && (
                              <option value={variacao.adsetKey}>
                                Conjunto removido · escolha outro
                              </option>
                            )}
                            {draft.conjuntos.map((item, indice) => (
                              <option key={item.key} value={item.key}>
                                {item.nome || `Conjunto ${indice + 1}`}
                              </option>
                            ))}
                          </select>
                        </Campo>
                        <Campo id={`meta-midia-${posicao}`} rotulo="Tipo de peça">
                          <select id={`meta-midia-${posicao}`} className={campo} value={variacao.midia}
                            onChange={(e) => mudarVariacao(posicao, 'midia', e.target.value as MidiaDaVariacao)}>
                            <option value="image">Imagem existente</option>
                            <option value="video">Vídeo existente · emissão bloqueada</option>
                          </select>
                        </Campo>
                        <Campo id={`meta-peca-${posicao}`} rotulo={variacao.midia === 'video' ? 'Vídeo da conta' : 'Imagem da conta'}>
                          <select id={`meta-peca-${posicao}`} className={campo} value={escolhida}
                            disabled={!draft.accountRef || ocupado === 'ativos'}
                            onChange={(e) => mudarVariacao(
                              posicao, variacao.midia === 'video' ? 'videoRef' : 'assetRef', e.target.value)}>
                            <option value="">
                              {lista.length === 0
                                ? `Nenhum ${variacao.midia === 'video' ? 'vídeo' : 'imagem'} nesta conta`
                                : 'Selecione uma peça existente'}
                            </option>
                            {lista.map((item) => (
                              <option key={item.referencia_opaca} value={item.referencia_opaca}>
                                {item.nome}{item.largura && item.altura ? ` · ${item.largura}×${item.altura}` : ''}
                              </option>
                            ))}
                          </select>
                        </Campo>
                        <Campo id={`meta-ad-name-${posicao}`} rotulo="Nome do anúncio">
                          <Input id={`meta-ad-name-${posicao}`} value={variacao.adName}
                            onChange={(e) => mudarVariacao(posicao, 'adName', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-creative-name-${posicao}`} rotulo="Nome do criativo">
                          <Input id={`meta-creative-name-${posicao}`} value={variacao.creativeName}
                            onChange={(e) => mudarVariacao(posicao, 'creativeName', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-primary-${posicao}`} rotulo="Texto principal" largo>
                          <Textarea id={`meta-primary-${posicao}`} rows={3} value={variacao.message}
                            onChange={(e) => mudarVariacao(posicao, 'message', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-headline-${posicao}`} rotulo="Título">
                          <Input id={`meta-headline-${posicao}`} value={variacao.headline}
                            onChange={(e) => mudarVariacao(posicao, 'headline', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-description-${posicao}`} rotulo="Descrição">
                          <Input id={`meta-description-${posicao}`} value={variacao.description}
                            onChange={(e) => mudarVariacao(posicao, 'description', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-cta-${posicao}`} rotulo="Chamada para ação" largo>
                          <select id={`meta-cta-${posicao}`} className={campo} value={variacao.cta}
                            onChange={(e) => mudarVariacao(posicao, 'cta', e.target.value)}>
                            {CTAS.map(([valor, rotulo]) => (
                              <option key={valor} value={valor}>{rotulo}</option>
                            ))}
                          </select>
                        </Campo>
                        <div className="grid gap-3 md:col-span-2">
                          <Escolha
                            marcado={variacao.assetRightsConfirmed}
                            onChange={(valor) => mudarPoliticaDaPeca(
                              posicao, 'assetRightsConfirmed', valor)}
                            titulo="Confirmo que esta peça é própria ou licenciada para mídia paga">
                            O backend ainda lê os bytes da imagem, calcula o hash e vincula esta
                            declaração ao image_hash exato usado no anúncio.
                          </Escolha>
                          <Escolha
                            marcado={variacao.thirdPartyIdentityCleared}
                            onChange={(valor) => mudarPoliticaDaPeca(
                              posicao, 'thirdPartyIdentityCleared', valor)}
                            titulo="Confirmei marcas, logos e identidades de terceiros nesta peça">
                            Marque somente se não houver identidade de terceiro sem autorização.
                            Sem esta confirmação, a peça não compila para mídia paga.
                          </Escolha>
                        </div>
                      </div>
                    </div>
                  </section>
                );
              })}
              {draft.creativeMode === 'batch' && (
                <Button type="button" variant="outline" className="w-full border-dashed"
                  aria-describedby="meta-limite-lote"
                  disabled={draft.variations.length >= LIMITE_VARIACOES}
                  onClick={() => adicionarVariacao()}>
                  <Plus className="mr-2 h-4 w-4" aria-hidden />Adicionar outro anúncio ao lote
                </Button>
              )}
            </div>
          )}
        </>
      );
      case 'mensuracao': return conjuntoFocado ? (
        <>
          {trilhoDeConjuntos}
          <PainelDeMensuracao
            draft={draft}
            conjunto={conjuntoFocado}
            propositosDaReceita={propositosDaReceita}
            motivoDaReceita={receita && !receita.propositos_de_mensuracao.includes('OPTIMIZE')
              ? 'Esta receita admite apenas relatar: otimizar mudaria o objetivo que ela declara.'
              : null}
            catalogoDeFontes={catalogoDeMensuracao?.contaRef === draft.accountRef
              ? catalogoDeMensuracao.fontes : null}
            catalogoDeConversoes={catalogoDeMensuracao?.contaRef === draft.accountRef
              ? catalogoDeMensuracao.conversoes : null}
            lendoConversoes={ocupado === 'conversoes'}
            erroDasConversoes={conversoesErro}
            resumoDoConjunto={resumoDoFocado}
            onDestino={(url) => mudar('destinationUrl', url)}
            onConjunto={mudarConjunto}
            onLerConversoes={lerConversoes}
          />
        </>
      ) : null;
      case 'revisao': return (
        <>
          <BlocoDeEvidencia titulo="O que será enviado à Meta" tom="verificado">
            <LinhaDeFato rotulo="Contrato do plano" valor={contrato === 'V1' ? 'V1 · a receita provada' : 'V2 · campanha com N conjuntos'} fonte="a forma deste plano" />
            <LinhaDeFato rotulo="Operações compiladas" valor={compilacao ? compilacao.plano.operacoes.length : null} fonte="o backend" ausencia="plano ainda não compilado" />
            <LinhaDeFato rotulo="Receita e tracking" valor={compilacao?.plano.tracking?.revenue_join ?? null}
              fonte="o plano compilado no backend" ausencia="recompile para conferir o vínculo GAM" />
            {compilacao?.plano.tracking && <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer py-2">Parâmetros incluídos nos criativos</summary>
              {[...new Set(compilacao.plano.tracking.url_tags)].map((tags, i) => <code className="block break-all py-1" key={i}>{tags ?? 'tracking não declarado neste criativo'}</code>)}
            </details>}
            <LinhaDeFato rotulo="Identidade do plano" valor={compilacao?.plano.plano_sha256 ?? null} fonte="o backend" ausencia="plano ainda não compilado" />
            <LinhaDeFato rotulo="Efeito externo da conferência" valor={compilacao ? 'Nenhum' : null} fonte="o backend" ausencia="—" />
          </BlocoDeEvidencia>

          {/* ⚠️ POR QUE ESTE PLANO NÃO É O V1. A lista existe para que ninguém
              precise adivinhar qual escolha fechou a criação: cada motivo é um
              recurso que só o contrato V2 descreve, e o V2 não tem rota de
              aprovação nem de nascimento. */}
          {contrato === 'V2' && (
            <BlocoDeEvidencia titulo="Por que este plano usa o contrato V2" tom="info">
              {motivosDoV2.map((motivo) => (
                <LinhaDeFato key={motivo} rotulo="Recurso do V2" valor={motivo} fonte="a forma deste plano" />
              ))}
              <LinhaDeFato
                rotulo="Consequência"
                valor="Conferir e validar continuam abertos; criar não existe neste contrato"
                fonte="as rotas do backend"
              />
            </BlocoDeEvidencia>
          )}

          {/* ⚠️ A REVISÃO RENDERIZA O RESUMO DO SERVIDOR, e não recalcula nada
              a partir do rascunho (`F37`, `A33`). Ele só existe depois de
              compilar ou validar, e cai junto com eles quando um campo muda. */}
          {resumo && <MapaDoPlano resumo={resumo} rotuloDoAnuncio={rotuloDoAnuncio} />}

          {compilacao && (
            <div className="overflow-x-auto rounded-lg border border-border/70">
              <table className="w-full min-w-[520px] text-sm">
                <caption className="sr-only">Operações que compõem o plano compilado</caption>
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Operação</th>
                    <th scope="col" className="px-3 py-2 font-medium">Objeto</th>
                    <th scope="col" className="px-3 py-2 font-medium">Estado ao nascer</th>
                    <th scope="col" className="px-3 py-2 font-medium">Validável sem criar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {compilacao.plano.operacoes.map((op) => (
                    <tr key={op.nome}>
                      <th scope="row" className="px-3 py-2 text-left font-medium text-foreground">{op.nome}</th>
                      <td className="px-3 py-2 text-muted-foreground">{op.tipo ?? '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{op.status ?? 'não veiculável'}</td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {op.validavel_sem_criar_pai ? 'Sim' : 'Não · depende de um objeto real'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {validacao && (
            <BlocoDeEvidencia titulo="Resultado da validação remota" tom={validacao.ok ? 'verificado' : 'atencao'}>
              <LinhaDeFato rotulo="Cobertura" valor="Parcial · apenas as operações que não dependem de um objeto real" fonte="a Meta" />
              <LinhaDeFato rotulo="Validadas" valor={validacao.operacoes_validadas.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              <LinhaDeFato rotulo="Ainda não validadas" valor={validacao.operacoes_dependentes_pendentes.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              <LinhaDeFato rotulo="Objetos criados" valor={String(validacao.objetos_criados)} fonte="a Meta" />
            </BlocoDeEvidencia>
          )}

          <div className="space-y-4">
            <AcaoDominante
              pode={podeCompilar && ocupado === null}
              enviando={ocupado === 'compilar'}
              faltas={faltas}
              onClick={compilar}
            >
              Conferir o plano
            </AcaoDominante>
            <div className="border-t border-border pt-4">
              <AcaoDominante
                pode={Boolean(compilacao) && capacidades.validateOnly && ocupado === null}
                enviando={ocupado === 'validar'}
                faltas={[
                  ...(compilacao ? [] : ['Confira o plano antes de falar com a Meta.']),
                  ...(capacidades.validateOnly ? [] : ['A validação remota está fechada neste servidor; um administrador precisa liberá-la.']),
                ]}
                onClick={validar}
              >
                Validar na Meta, sem criar nada
              </AcaoDominante>
            </div>
          </div>

          {!capacidades.criarPausada && (
            <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <div className="max-w-[74ch] space-y-2 text-sm leading-relaxed text-pretty text-foreground">
                <p><strong>Criação PAUSED ainda fechada neste servidor.</strong></p>
                <p className="text-muted-foreground">
                  {capacidades.criarPausadaMotivo
                    ?? 'Um administrador precisa liberar a criação antes de qualquer nascimento.'}
                </p>
              </div>
            </div>
          )}

          {/* ⚠️ O SERVIDOR AUTORIZA CRIAR, MAS ESTE PLANO NÃO PODE NASCER.
              São duas coisas diferentes e a tela as separa: a flag do servidor
              governa o ato; o contrato governa a FORMA do plano. `/aprovar`
              recebe o DTO do V1, e não existe rota de aprovação para o V2. */}
          {capacidades.criarPausada && contrato === 'V2' && (
            <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <div className="max-w-[74ch] space-y-2 text-sm leading-relaxed text-pretty text-foreground">
                <p><strong>Este plano não pode nascer nesta bancada.</strong></p>
                <p className="text-muted-foreground">
                  A criação PAUSED está aberta no servidor, mas ela existe apenas para o contrato
                  V1 — a receita de conjunto único que a Meta aceitou. Este plano usa recursos do
                  contrato V2, que tem conferência e validação, e não tem rota de aprovação nem de
                  nascimento. Conferir e validar continuam liberados, e nada é criado.
                </p>
              </div>
            </div>
          )}

          {criacaoDisponivel && (
            <div className="space-y-4 rounded-lg border border-border/70 p-4">
              <BlocoDeEvidencia titulo="O que será criado agora, de verdade" tom="atencao">
                <LinhaDeFato rotulo="Conta" valor={conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : null} fonte="a Meta" ausencia="não escolhida" />
                <LinhaDeFato rotulo="Orçamento diário" valor={reaisParaMinor(draft.conjuntos[0]?.orcamentoBrl ?? '') > 0 ? `${formatarBrl(reaisParaMinor(draft.conjuntos[0].orcamentoBrl))} · no conjunto` : null} fonte="você" ausencia="não informado" />
                <LinhaDeFato rotulo="Campanha" valor={draft.campaignName || null} fonte="você" ausencia="sem nome" />
                <LinhaDeFato rotulo="Conjunto" valor={draft.conjuntos[0]?.nome || null} fonte="você" ausencia="sem nome" />
                <LinhaDeFato rotulo="Criativos e anúncios" valor={`${emitidas.length} criativo${emitidas.length === 1 ? '' : 's'} · ${emitidas.length} anúncio${emitidas.length === 1 ? '' : 's'}`} fonte="o compilador" />
                <LinhaDeFato rotulo="Estado ao nascer" valor="Pausado em todos os níveis veiculáveis" fonte="a receita provada" />
                <LinhaDeFato rotulo="Identidade do plano" valor={compilacao?.plano.plano_sha256 ?? null} fonte="o backend" ausencia="plano ainda não compilado" />
                <LinhaDeFato rotulo="Validação remota" valor={validacao?.ok ? `Aceita · ${validacao.operacoes_validadas.join(', ')}` : null} fonte="a Meta" ausencia="ainda não validado" />
                <LinhaDeFato rotulo="Prova durável da validação" valor={validacao?.prova_duravel?.registrada ? 'Gravada no servidor' : null} fonte="o backend" ausencia="não gravada" />
                <LinhaDeFato rotulo="Ainda sem validação remota" valor={validacao?.operacoes_dependentes_pendentes.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              </BlocoDeEvidencia>

              {/* ⚠️ A cobertura parcial fica JUNTO do botão que cria, não numa
                  nota de rodapé: conjunto e anúncio nunca foram validados
                  remotamente, e é exatamente neles que a primeira criação real
                  pode falhar. */}
              <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
                A validação remota cobre apenas as operações que não dependem de um objeto
                real. O conjunto e os anúncios só serão exercitados contra a Meta agora,
                durante a criação — e cada passo é conferido por leitura antes do seguinte.
              </p>

              <Escolha
                marcado={confirmacaoMarcada}
                onChange={setConfirmacaoMarcada}
                titulo="Confirmo a criação real destes objetos em estado PAUSED"
              >
                Os objetos passam a existir na conta de anúncios. Nada veicula: tudo nasce
                pausado, e nenhuma rota desta bancada ativa.
              </Escolha>

              <Campo
                id="meta-confirmacao"
                rotulo={`Digite ${CONFIRMACAO_DE_CRIACAO} para liberar a aprovação`}
                ajuda="A frase é comparada exatamente, aqui e no servidor."
                largo
              >
                <Input
                  id="meta-confirmacao"
                  value={confirmacaoDigitada}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(e) => setConfirmacaoDigitada(e.target.value)}
                />
              </Campo>

              {/* Dois atos separados, e a separação é o desenho: aprovar
                  decide, criar executa. */}
              <div className="space-y-4">
                <AcaoDominante
                  pode={
                    Boolean(validacao?.ok && validacao.prova_duravel?.registrada)
                    && !aprovacao && confirmacaoMarcada
                    && confirmacaoDeCriacaoValida(confirmacaoDigitada)
                    && ocupado === null
                  }
                  enviando={ocupado === 'aprovar'}
                  faltas={[
                    ...(validacao?.ok ? [] : ['Valide o plano na Meta antes de aprovar.']),
                    ...(validacao?.ok && !validacao.prova_duravel?.registrada
                      ? ['A prova da validação não foi gravada no servidor; valide de novo.'] : []),
                    ...(confirmacaoMarcada ? [] : ['Marque a confirmação de criação real.']),
                    ...(confirmacaoDeCriacaoValida(confirmacaoDigitada)
                      ? [] : [`Digite ${CONFIRMACAO_DE_CRIACAO} exatamente como está escrito.`]),
                    ...(aprovacao ? ['Este plano já está aprovado.'] : []),
                  ]}
                  onClick={aprovar}
                >
                  Aprovar plano
                </AcaoDominante>

                <div className="border-t border-border pt-4">
                  <AcaoDominante
                    pode={Boolean(aprovacao) && !jaDespachou && ocupado === null}
                    enviando={ocupado === 'criar'}
                    faltas={[
                      ...(aprovacao ? [] : ['Aprove o plano antes de criar.']),
                      ...(porQueNaoCriar ? [porQueNaoCriar] : []),
                    ]}
                    onClick={criar}
                  >
                    Criar campanha PAUSED
                  </AcaoDominante>
                </div>
              </div>

            </div>
          )}

          {/* ================================================================
              A OPERAÇÃO DURÁVEL — fora do portão da criação, de propósito.
              Ler um recibo e reconciliar por leitura dependem só da autoridade
              do ledger; a flag de criação governa o POST que faz nascer objeto.
              ================================================================ */}
          {referenciaAlvo && (
            <section
              className="space-y-4 rounded-lg border border-border/70 p-4"
              aria-labelledby="meta-operacao-titulo"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 id="meta-operacao-titulo" className="font-display text-lg font-semibold text-foreground">
                  Operação despachada
                </h3>
                {referenciaAlvo && (
                  <span className="font-mono text-xs text-muted-foreground">
                    referência {referenciaAlvo.slice(0, 8)}…
                  </span>
                )}
              </div>

              {operacaoCarregando && (
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  Lendo o recibo desta operação…
                </p>
              )}

              {/* ⚠️ Falha de LEITURA nunca vira "nenhum recibo". */}
              {operacaoErro && operacaoErro.referencia === referenciaAlvo && !reciboVigente && (
                <PainelDeBloqueio
                  titulo="Não foi possível ler o recibo desta operação"
                  bloqueios={[{
                    codigo: 'META_RECEIPT_READ_FAILED',
                    severidade: 'alta',
                    titulo: operacaoErro.mensagem,
                    detalhe:
                      'A operação pode existir: isto é uma falha de LEITURA, não a '
                      + 'ausência de um recibo. Tente ler de novo antes de concluir '
                      + 'qualquer coisa sobre o que existe na conta.',
                  }]}
                />
              )}

              {aprovacao && !jaDespachou && !reciboVigente && (
                <BlocoDeEvidencia titulo="Aprovação registrada" tom="verificado">
                  <LinhaDeFato rotulo="Operações autorizadas" valor={String(aprovacao.operacoes)} fonte="o backend" />
                  <LinhaDeFato rotulo="Passos aprovados" valor={aprovacao.manifesto.join(' → ')} fonte="o backend" />
                  <LinhaDeFato rotulo="Orçamento aprovado" valor={`${formatarBrl(aprovacao.orcamento_diario_minor)} · ${aprovacao.moeda}`} fonte="o backend" />
                  <LinhaDeFato rotulo="Válida até" valor={aprovacao.expires_at} fonte="o backend" />
                </BlocoDeEvidencia>
              )}

              {reciboVigente && referenciaAlvo && (
                <MetaOperationReceipt recibo={reciboVigente} referencia={referenciaAlvo} />
              )}

              {podeReconciliar && (
                <div className="border-t border-border pt-4">
                  {/* ⚠️ Reconciliar LÊ. Não existe, e não pode existir, um botão
                      "tentar criar de novo": depois de um despacho, repetir
                      duplica. */}
                  <AcaoDominante
                    pode={ocupado === null}
                    enviando={ocupado === 'reconciliar'}
                    faltas={[]}
                    onClick={reconciliar}
                  >
                    Reconciliar por leitura
                  </AcaoDominante>
                  <p className="mt-2 max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
                    Ler a conta e fechar o que estiver provado. Nenhum objeto é criado
                    aqui, e ausência depois de um despacho nunca vira permissão para
                    enviar de novo.
                  </p>
                  {reconciliacao && reconciliacao.referencia === referenciaAlvo && (
                    <BlocoDeEvidencia
                      titulo="Reconciliação por leitura"
                      tom={reconciliacao.resultado.passos_ambiguos > 0 ? 'atencao' : 'verificado'}
                    >
                      <LinhaDeFato rotulo="Passos ambíguos" valor={String(reconciliacao.resultado.passos_ambiguos)} fonte="o recibo durável" />
                      <LinhaDeFato rotulo="Efeito externo" valor="Nenhum · apenas leitura" fonte="o backend" />
                      {(reconciliacao.resultado.passos_promovidos?.length ?? 0) > 0 && (
                        <LinhaDeFato
                          rotulo="Passos recuperados"
                          valor={`${reconciliacao.resultado.passos_promovidos!.join(', ')} · estavam em voo sem conclusão`}
                          fonte="o recibo durável"
                        />
                      )}
                      {(reconciliacao.resultado.passos_em_voo?.length ?? 0) > 0 && (
                        <LinhaDeFato
                          rotulo="Ainda em voo"
                          valor={`${reconciliacao.resultado.passos_em_voo!.join(', ')} · recentes demais para adjudicar`}
                          fonte="o recibo durável"
                        />
                      )}
                      {reconciliacao.resultado.conclusoes.map((item) => (
                        <LinhaDeFato key={item.passo} rotulo={item.passo} valor={item.explicacao} fonte="a leitura da conta" />
                      ))}
                    </BlocoDeEvidencia>
                  )}
                </div>
              )}
            </section>
          )}

          <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/30 p-4">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
              <strong className="text-foreground">Receita GAM por campaign_id.</strong>{' '}
              Novos planos usam utm_campaign e campaign_id com o ID dinâmico da campanha. A URL da LP permanece a escolhida;
              a validação do plano atual e a prova do tracking no destino ainda são necessárias.{' '}
              <strong className="text-foreground">Ativar continua sendo outro ato, e ele não existe.</strong>{' '}
              Nenhuma rota desta bancada leva um objeto a ENABLE. Tudo que veicula nasce
              pausado e só uma pessoa, fora daqui, pode ligar.
            </p>
          </div>
        </>
      );
      // ⚠️ O `default` não é decoração. Sem ele, uma `EtapaId` nova sem `case`
      // renderiza tela em branco — sem erro de compilação e sem erro de runtime,
      // porque o `switch` simplesmente devolve `undefined`. Um passo em branco
      // numa bancada de gasto é pior do que uma falha ruidosa.
      default: return (
        <PainelDeBloqueio
          titulo="Esta etapa não tem conteúdo desenhado"
          bloqueios={[{
            codigo: 'META_STEP_WITHOUT_CONTENT',
            severidade: 'alta',
            titulo: `A etapa "${etapa}" existe no trilho e não tem tela`,
            detalhe:
              'Nada foi perdido do rascunho. Volte uma etapa e siga pelo trilho; '
              + 'esta é uma falha da bancada, não do seu plano.',
          }]}
        />
      );
    }
  })();
  return (
    <Layout>
      <div className="bancada-shell mx-auto max-w-[1480px] px-4 pb-24 pt-4 md:px-6 md:pt-6">
        <section className="bancada-command-deck">
          <div className="bancada-command-topline" aria-hidden />
          <header className="bancada-command-header">
            <div className="min-w-0">
              <Link to="/trafego?rede=meta&aba=preparar" className="bancada-back-link">
                <ArrowLeft className="h-4 w-4" aria-hidden /> Tráfego · Meta Ads
              </Link>
              <div className="mt-5 flex items-center gap-2">
                <span className="bancada-command-icon">
                  <Megaphone className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="kicker text-slate-400">Nascimento controlado · Meta v26</span>
              </div>
              <h1 className="mt-2 max-w-[22ch] font-display text-[2rem] font-bold leading-[1.02] tracking-[-0.035em] text-white text-balance md:text-[2.5rem]">
                Nova campanha Meta
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <div className="bancada-safety-contract">
                <span className="bancada-safety-dot" aria-hidden />
                <div>
                  <p className="font-semibold text-white">Criação segura</p>
                  <p>Tudo que veicula nasce pausado</p>
                </div>
              </div>
              <MetaConfiguracaoLocal />
            </div>
          </header>

          <nav className="bancada-route" aria-label="Etapas da criação Meta">
            <div className="bancada-route-heading">
              <span>Plano de criação</span>
              <span>etapa {indice + 1} de {ETAPAS.length}</span>
            </div>
            <ol className="bancada-route-track">
              {ETAPAS.map((item, posicao) => {
                const estado = estados[item.id];
                const desenho = DESENHO_DO_ESTADO[estado];
                const atual = item.id === etapa;
                return (
                  <li key={item.id} className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => navegar(item.id)}
                      aria-current={atual ? 'step' : undefined}
                      className={cn(
                        'bancada-route-step transition-volc duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                        atual ? 'bancada-route-step-active' : 'bancada-route-step-idle',
                      )}
                    >
                      <span className="bancada-route-index" aria-hidden>
                        {estado === 'pronto' || estado === 'validado'
                          ? <desenho.Glifo className="h-3.5 w-3.5" />
                          : String(posicao + 1).padStart(2, '0')}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">{item.nome}</span>
                        <span className={cn('block truncate text-[0.6875rem]', desenho.tinta)}>
                          {desenho.palavra}
                        </span>
                      </span>
                      <span className="sr-only"> — {desenho.palavra}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </section>

        <div className="bancada-grid mt-6 grid gap-6">
          <main className="bancada-stage min-w-0">
            <header className="bancada-stage-header">
              <div>
                <p className="kicker text-primary">Etapa {indice + 1} de {ETAPAS.length}</p>
                <h2 className="mt-2 max-w-[30ch] font-display text-2xl font-semibold leading-tight tracking-tight text-balance text-foreground md:text-[2rem]">
                  {ETAPAS[indice].pergunta}
                </h2>
              </div>
              <p className="bancada-stage-hint">
                Uma decisão por vez. O contrato técnico fica disponível sem disputar a sua atenção.
              </p>
            </header>

            <div className="space-y-5 p-4 md:p-6">
              {/* ⚠️ Região viva: a falha de compilar ou validar chega depois do
                  clique, e sem isto ela aparece na tela sem ser anunciada a
                  quem usa leitor de tela. */}
              <div role="alert" aria-live="assertive">
                <PainelDeBloqueio bloqueios={avisos} titulo="A operação não foi concluída" />
              </div>
              {conteudo}
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
                <Button type="button" variant="outline" disabled={indice === 0}
                  onClick={() => navegar(ETAPAS[indice - 1].id)}>
                  <ArrowLeft className="mr-2 h-4 w-4" aria-hidden /> Voltar
                </Button>
                {indice < ETAPAS.length - 1 && (
                  <Button type="button" variant="outline"
                    onClick={() => navegar(ETAPAS[indice + 1].id)}>
                    Continuar <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                  </Button>
                )}
              </div>
            </div>
          </main>

          <aside className="min-w-0">
            <Pedido
              linhas={linhasDoPedido}
              faltas={faltas}
              proximoAto={proximoAto}
              lidoEm={null}
            />
          </aside>
        </div>
      </div>
    </Layout>
  );
};

export default MetaCriacaoPage;
