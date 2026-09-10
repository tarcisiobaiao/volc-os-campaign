/**
 * Jornada guiada de criação Meta: uma decisão por tela, um único rascunho.
 * O compilador do servidor continua sendo a autoridade do plano e do hash.
 * V1 e V2 exigem aprovação durável, capacidades do servidor e nascimento PAUSED.
 * Navegar, escolher uma receita ou selecionar um asset não autoriza despacho.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, CircleCheck, CircleDot, Copy, Film, Image as ImageIcon,
  Lock, Megaphone, Plus, ShieldCheck, Trash2, Upload,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import {
  AcaoDominante, BlocoDeEvidencia, ChipDeEstado, LinhaDeFato, PainelDeBloqueio, Pedido,
} from '@/components/trafego/bancada';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import { RascunhosMeta } from '@/components/trafego/meta/RascunhosMeta';
import { MapaDoPlano } from '@/components/trafego/meta/MapaDoPlano';
import { PainelDeConjuntos } from '@/components/trafego/meta/PainelDeConjuntos';
import { PainelDeMensuracao } from '@/components/trafego/meta/PainelDeMensuracao';
import { IdentidadeDoAnunciante } from '@/components/trafego/meta/IdentidadeDoAnunciante';
import { criarLeitorDeIdentidadesCompartilhado } from '@/components/trafego/meta/leituraCompartilhadaDeIdentidades';
import { supabase } from '@/lib/supabase';
import { EscolherBusinessMeta } from '@/components/trafego/meta/EscolherBusinessMeta';
import { SelecionarAtivoMeta } from '@/components/trafego/meta/SelecionarAtivoMeta';
import { FormatoDeCriativos } from '@/components/trafego/meta/FormatoDeCriativos';
import { TextosDoAnuncioFlexivel } from '@/components/trafego/meta/TextosDoAnuncioFlexivel';
import { VarinhaDeCopy } from '@/components/trafego/meta/VarinhaDeCopy';
import { NomenclaturaAutomatica } from '@/components/trafego/meta/NomenclaturaAutomatica';
import { aplicarNomenclatura, siteDoDestino, tipoDoDestino } from '@/components/trafego/meta/nomenclatura';
import { PainelDeOrcamento } from '@/components/trafego/meta/PainelDeOrcamento';
import { PainelDePublico } from '@/components/trafego/meta/PainelDePublico';
import { PainelDeReceita } from '@/components/trafego/meta/PainelDeReceita';
import { TrackingAutomatico } from '@/components/trafego/meta/TrackingAutomatico';
import { Campo, Escolha, GrupoDeEscolha, campo } from '@/components/trafego/meta/primitivas';
import {
  BLOQUEIOS, CAPACIDADES_FECHADAS, CONFIRMACAO_DE_CRIACAO, ConjuntoDraft, Draft,
  EtapaId, IDADE_MAXIMA_PADRAO, IDADE_MINIMA_PADRAO, LIMITE_CONJUNTOS, LIMITE_VARIACOES,
  NivelDeOrcamento, PeriodoDeOrcamento, PropositoDeMensuracao, RECEITA_PADRAO,
  VariacaoDraft, conjuntoInicial, confirmacaoDeCriacaoValida, contratoDoPlano, dominioDoDestino, destinoValido,
  formatarBrl, inicioEmIso, nomeUnico, orcamentosDoPlano, paraPlano, paraPlanoV2,
  prontidaoDasEtapas, prontoParaCompilar, proximaChave, reaisParaMinor, variacaoCompleta, pendenciasDaVariacao,
  variacaoInicial, variacoesEmitidas, type CapacidadesDaBancada,
  textosFlexiveisDoConjunto, pendenciasDosTextosFlexiveis, variacaoEfetiva, type TextosFlexiveisDraft,
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
import { useMetaCampaignDraft } from '@/hooks/useMetaCampaignDraft';
import { perguntaDaUrl, perguntasMeta, type PerguntaMeta } from '@/components/trafego/meta/jornada';
import '@/components/trafego/meta/jornada.css';
import { lerSelecaoDoAssistente, lerSelecaoDeCopy, type SelecaoDeCopy } from '@/components/trafego/meta/ponteAssistente';
import { ImportarCopyDoAssistente } from '@/components/trafego/meta/ImportarCopyDoAssistente';
import { AssistenteNaJornada } from '@/components/trafego/meta/AssistenteNaJornada';
import {
  fixarPackNoConjunto, importarMidiaPrivada, listarSelecoesDePack, retirarPackDoConjunto, salvarPack,
  type DraftPackSelection,
} from '@/features/creative-studio/api';
import { EscolherPack } from '@/features/creative-studio/componentes/EscolherPack';
import { adicionarAnuncioNoConjunto, duplicarParaTrocarImagem, removerConjuntoSemAnuncios } from '@/components/trafego/meta/vinculos';
import { ReutilizarEmConjunto } from '@/components/trafego/meta/DistribuicaoDeAnuncios';
import { PrepararPackMeta } from '@/components/trafego/meta/PrepararPackMeta';
import { materializarPack, packMaterializado } from '@/components/trafego/meta/materializarPack';
import { RevisaoHumanaDosAnuncios } from '@/components/trafego/meta/RevisaoHumanaDosAnuncios';
import type { AvisoDoCockpit, LinhaDoPedido } from '@/types/trafego';

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

const novaReferenciaDeRascunho = () => (
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, caractere => {
      const valor = Math.floor(Math.random() * 16);
      return (caractere === 'x' ? valor : (valor & 0x3) | 0x8).toString(16);
    })
);

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
const PreviaDaPeca: React.FC<{
  accountRef: string; ativo?: AtivoCriacaoMeta; onUpload?: (file: File) => void; uploadBusy?: boolean;
}> = ({
  accountRef, ativo, onUpload, uploadBusy = false,
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
      ) : onUpload ? (
        <label className={cn('flex min-h-40 w-full cursor-pointer flex-col items-center justify-center gap-2 px-5 text-center text-sm transition-colors focus-within:ring-2 focus-within:ring-ring',
          uploadBusy ? 'pointer-events-none opacity-60' : 'hover:bg-primary/5 hover:text-foreground')}>
          <input type="file" className="sr-only" accept="image/jpeg,image/png" disabled={uploadBusy}
            onChange={event => { const file = event.currentTarget.files?.[0]; if (file) onUpload(file); event.currentTarget.value = ''; }} />
          <Glifo className="h-7 w-7 opacity-50" aria-hidden />
          <span>{uploadBusy ? 'Guardando imagem…' : erro || (ativo?.preview_disponivel ? 'Carregando prévia…' : 'Clique para enviar uma imagem')}</span>
          {!uploadBusy && <span className="inline-flex items-center gap-1 font-medium text-primary"><Upload className="h-4 w-4" aria-hidden />JPEG ou PNG</span>}
        </label>
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
    objetos_criados?: unknown;
    provedor?: {
      objeto?: string; code?: string; error_subcode?: string; messages?: string[];
    };
  };
  const provedor = corpo.provedor;

  const criacaoParcial = Array.isArray(corpo.objetos_criados) && corpo.objetos_criados.length > 0;
  const detalheParcial = criacaoParcial
    ? 'A criação foi parcial: já existem objetos registrados na Meta. Confira o recibo '
      + 'durável abaixo antes de continuar; não recomece a campanha do zero.'
    : '';

  if (corpo.codigo === 'META_VERIFIED_ADVERTISER_REQUIRED'
    || (String(provedor?.code) === '100' && String(provedor?.error_subcode) === '3858634')) {
    return [{
      codigo: 'META_VERIFIED_ADVERTISER_REQUIRED',
      severidade: 'alta',
      titulo: 'Escolha a identificação do anunciante deste conjunto',
      detalhe: 'A Meta recusou este conjunto (100/3858634). Na revisão, consulte as identificações da conta e escolha o cadastro correto. Nas Configurações de publicidade '
        + 'da Meta, confira a identidade verificada do anunciante e as informações de '
        + 'beneficiário e pagador exigidas para esta conta e público. Não escolhemos essa '
        + 'identidade nem alteramos o público automaticamente. '
        + (detalheParcial || 'Confira o recibo da operação antes de uma nova tentativa.'),
    }];
  }

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
      detalhe: (explicacoes.length
        ? explicacoes.join(' · ')
        : 'A Meta não devolveu explicação adicional.')
        + (detalheParcial ? ` ${detalheParcial}` : ''),
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
  const [epocaDaSessao, setEpocaDaSessao] = useState(0);
  const lerIdentidades = useMemo(() => criarLeitorDeIdentidadesCompartilhado(pautadorApi.identidadesRegulatoriasMeta), [epocaDaSessao]);
  const leitorAtual = useRef(lerIdentidades); leitorAtual.current = lerIdentidades;
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange(event => {
      if (event === 'INITIAL_SESSION') return;
      leitorAtual.current.clear(); setEpocaDaSessao(epoch => epoch + 1);
    });
    return () => { data.subscription.unsubscribe(); leitorAtual.current.clear(); };
  }, []);
  const [params, setParams] = useSearchParams();
  /** A referência OPACA da operação, e é só ela que viaja na URL.
   *
   * ⚠️ Nem token, nem id da Meta, nem o plano congelado: o `approval_id` é um
   * UUID que só significa alguma coisa dentro do banco, e o servidor ainda
   * confere se quem pede é quem aprovou. Uma referência malformada não chega
   * perto de credencial nenhuma — ela morre na validação da rota. */
  const operacaoRef = params.get('operacao');
  const [draft, setDraft] = useState<Draft>({ ...DRAFT_INICIAL, destinationUrl: '', campaignName: '' });
  const mostraConversao = draft.recipeId !== RECEITA_PADRAO || params.get('pergunta') === 'conversao' || params.get('etapa') === 'mensuracao';
  const perguntas = perguntasMeta(mostraConversao);
  const pergunta = perguntaDaUrl(params, mostraConversao);
  const etapa = pergunta.etapa;
  const indice = perguntas.findIndex(p => p.id === pergunta.id);
  const [origemCriativa, setOrigemCriativa] = useState<'conta' | 'assistente' | 'pack'>(params.get('pack') ? 'pack' : 'conta');
  const [assistenteAberto, setAssistenteAberto] = useState(false);
  const iframeAssistente = useRef<HTMLIFrameElement>(null);
  const [projetoCriativo, setProjetoCriativo] = useState<string | null>(null);
  const [mastersSelecionados, setMastersSelecionados] = useState<string[]>([]);
  const [packAviso, setPackAviso] = useState('');
  const [packOcupado, setPackOcupado] = useState(false);
  const [arquivoOcupado, setArquivoOcupado] = useState<string | null>(null);
  const alvoDoUpload = useRef<{ packId: string; variationKey: string } | null>(null);
  const [editandoPack, setEditandoPack] = useState(false);
  const [selecoesDePack, setSelecoesDePack] = useState<DraftPackSelection[]>([]);
  const [selecoesCarregadas, setSelecoesCarregadas] = useState(false);
  const [selecoesErro, setSelecoesErro] = useState(false);
  // Capture explicit resume before the new-draft effect adds its generated ID.
  // A missing existing ID must never be recreated by autosaving blank defaults.
  const [retomandoRascunho] = useState(() => params.has('rascunho'));
  const [draftRef] = useState(() => {
    const atual = params.get('rascunho');
    return atual && /^[0-9a-f-]{36}$/i.test(atual) ? atual : novaReferenciaDeRascunho();
  });
  const packRef = params.get('pack');
  useEffect(() => {
    if (params.get('rascunho') === draftRef) return;
    const nova = new URLSearchParams(params);
    nova.set('rascunho', draftRef);
    setParams(nova, { replace: true });
  }, [draftRef]); // a referência nasce uma vez; mudanças de etapa não criam outro rascunho
  useEffect(() => {
    let vivo = true;
    setSelecoesCarregadas(false);
    setSelecoesErro(false);
    if (params.get('modo') === 'demo') {
      setSelecoesDePack([]); setSelecoesCarregadas(true);
      return () => { vivo = false; };
    }
    listarSelecoesDePack(draftRef).then(resposta => {
      if (vivo) { setSelecoesDePack(resposta.selections); setSelecoesCarregadas(true); }
    }).catch(exc => {
      if (vivo) {
        setSelecoesErro(true);
        setPackAviso(exc instanceof Error ? exc.message : 'Não foi possível recuperar os packs deste rascunho.');
        setSelecoesCarregadas(true);
      }
    });
    return () => { vivo = false; };
  }, [draftRef]);
  const [copySelecionada, setCopySelecionada] = useState<SelecaoDeCopy | null>(null);
  const [copyAplicada, setCopyAplicada] = useState(false);
  useEffect(() => {
    function receber(evento: MessageEvent) {
      if (evento.origin !== window.location.origin || !iframeAssistente.current
          || evento.source !== iframeAssistente.current.contentWindow) return;
      if (evento.data?.type === 'volc:creative-project'
          && typeof evento.data.projectRef === 'string'
          && /^crproj_[a-zA-Z0-9_-]{8,160}$/.test(evento.data.projectRef)) setProjetoCriativo(evento.data.projectRef);
      const selecao = lerSelecaoDoAssistente(evento.data);
      if (selecao) setMastersSelecionados(selecao.masterRefs);
      const copy = lerSelecaoDeCopy(evento.data);
      if (copy) { setCopySelecionada(copy); setCopyAplicada(false); }
    }
    window.addEventListener('message', receber);
    return () => window.removeEventListener('message', receber);
  }, []);
  const [erroDaPergunta, setErroDaPergunta] = useState('');
  const [avisoDaDuplicacao, setAvisoDaDuplicacao] = useState('');
  const tituloDaPergunta = useRef<HTMLHeadingElement>(null);
  const [contas, setContas] = useState<ContaMetaLocal[]>([]);
  const [categoriaEspecial, setCategoriaEspecial] = useState(false);
  const [contaParaRestaurar, setContaParaRestaurar] = useState('');
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
  const [feedbackDoPlano, setFeedbackDoPlano] = useState('');
  const feedbackRef = useRef<HTMLDivElement>(null);
  const focarFeedback = useRef(false);
  useEffect(() => {
    if (feedbackDoPlano && focarFeedback.current) {
      focarFeedback.current = false;
      feedbackRef.current?.scrollIntoView?.({ block: 'center', behavior: 'auto' });
      feedbackRef.current?.focus({ preventScroll: true });
    }
  }, [feedbackDoPlano]);
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
   * deles é buscado em um rascunho novo: o preflight desta lane já custa nove
   * requisições paginadas por clique. Ao retomar, apenas a mensuração já
   * selecionada é relida para recuperar nomes e elegibilidade sem mudar escolhas. */
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
      const anterior = proximos.get('operacao');
      if (anterior && anterior !== referencia) proximos.set('operacao_anterior', anterior);
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
    setFeedbackDoPlano(anterior => anterior ? 'O plano mudou. Confira e valide novamente antes de aprovar.' : '');
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

  const rascunhoPersistido = useMetaCampaignDraft({
    draftRef, draft, enabled: params.get('modo') !== 'demo',
    requireExisting: retomandoRascunho,
    onRestore: (salvo) => {
      setDraft(salvo); invalidar();
      setContaParaRestaurar(salvo.accountRef);
      setConjuntoFocadoRef(salvo.conjuntos[0]?.key ?? CHAVE_DO_PRIMEIRO_CONJUNTO);
      // Respect explicit deep links. A plain "Continuar" goes to the next
      // meaningful decision instead of presenting the empty initial screen.
      setParams(atuais => {
        if (atuais.has('pergunta') || atuais.has('etapa')) return atuais;
        const id = !salvo.accountRef ? 'conta' : !salvo.pageRef ? 'pagina'
          : !destinoValido(salvo.destinationUrl) ? 'destino'
          : salvo.conjuntos.some(c => c.mensuracao.proposito === 'OPTIMIZE' && !c.mensuracao.fonteRef)
            ? 'conversao' : 'criativos';
        const alvo = perguntasMeta(true).find(p => p.id === id)!;
        const proximos = new URLSearchParams(atuais);
        proximos.set('pergunta', alvo.id); proximos.set('etapa', alvo.etapa);
        return proximos;
      }, { replace: true });
    },
  });
  useEffect(() => {
    if (!contaParaRestaurar || contaParaRestaurar !== draft.accountRef || params.get('modo') === 'demo') return;
    let vivo = true;
    // Rehydrate labels, not intent. Never auto-select the first account here.
    pautadorApi.contasMetaLocal().then(inventario => {
      if (vivo) setContas(inventario.contas);
    }).catch(exc => { if (vivo) setAvisos(avisosDoErro(exc)); });
    return () => { vivo = false; };
  }, [contaParaRestaurar, draft.accountRef]);
  const mensuracaoParaRestaurar = contaParaRestaurar === draft.accountRef
    && draft.conjuntos.some(c => c.mensuracao.fonteRef || c.mensuracao.conversaoRef)
      ? contaParaRestaurar : '';
  useEffect(() => {
    if (!mensuracaoParaRestaurar || params.get('modo') === 'demo') return;
    let vivo = true;
    const meuSelo = seloDosCatalogos.current;
    // Saved source IDs are intent; restore their live labels/eligibility too.
    // This read never changes the chosen pixel or conversion event.
    pautadorApi.catalogoDeMensuracaoMeta(mensuracaoParaRestaurar).then(resultado => {
      if (vivo && meuSelo === seloDosCatalogos.current) {
        setCatalogoDeMensuracao({ contaRef: mensuracaoParaRestaurar,
          fontes: resultado.fontes, conversoes: resultado.conversoes });
      }
    }).catch(exc => {
      if (vivo && meuSelo === seloDosCatalogos.current) {
        setConversoesErro(exc instanceof Error ? exc.message : 'Não foi possível conferir a fonte de mensuração salva.');
      }
    });
    return () => { vivo = false; };
  }, [mensuracaoParaRestaurar]);
  const contaAnteriorDosAtivos = useRef('');

  const tamanhosParaNomes = Object.fromEntries([...imagens, ...videos]
    .filter(a => a.largura && a.altura).map(a => [a.referencia_opaca, `${a.largura}x${a.altura}`]));
  const nomesSizeKey = JSON.stringify(tamanhosParaNomes);
  const conversoesParaNomes = Object.fromEntries((catalogoDeMensuracao?.contaRef === draft.accountRef
    ? catalogoDeMensuracao.conversoes.items : []).map(c => [c.referencia_opaca, c.nome]));
  const nomesConversoesKey = JSON.stringify(conversoesParaNomes);
  useEffect(() => {
    if (!draft.naming?.enabled || rascunhoPersistido.blocked) return;
    const next = aplicarNomenclatura(draft, draft.naming, tamanhosParaNomes, false, conversoesParaNomes);
    if (JSON.stringify(next) !== JSON.stringify(draft)) { setDraft(next); invalidar(); }
  }, [draft, nomesSizeKey, nomesConversoesKey, rascunhoPersistido.blocked, invalidar]);

  const mudar = useCallback(<K extends keyof Draft>(chave: K, valor: Draft[K]) => {
    setErroDaPergunta('');
    setDraft((atual) => ({ ...atual, [chave]: valor,
      ...(chave === 'destinationUrl' && atual.naming
        ? { naming: { ...atual.naming,
          landingType: ['', 'LP_R'].includes(atual.naming.landingType) ? tipoDoDestino(String(valor)) : atual.naming.landingType,
          site: !atual.naming.site || atual.naming.site === siteDoDestino(atual.destinationUrl) ? siteDoDestino(String(valor)) : atual.naming.site,
        } } : {}),
      ...((chave === 'accountRef' || chave === 'pageRef') && atual[chave] !== valor ? {
        variations: atual.variations.map(ad => ad.existingPostRef ? {
          ...ad, existingPostRef: undefined, assetRef: '', message: '', headline: '', description: '',
          assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
        } : ad),
      } : {}),
    }));
    invalidar();
  }, [invalidar]);

  // A selection from the studio changes operator intent even before upload.
  useEffect(() => { invalidar(); }, [mastersSelecionados, invalidar]);
  useEffect(() => { invalidar(); }, [selecoesDePack, invalidar]);

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
    const trocouDeConta = Boolean(contaAnteriorDosAtivos.current && contaAnteriorDosAtivos.current !== contaPedida);
    contaAnteriorDosAtivos.current = contaPedida;
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
          pageRef: !trocouDeConta && atual.pageRef ? atual.pageRef : resultado.paginas.some((item) => item.referencia_opaca === atual.pageRef)
            ? atual.pageRef : (resultado.paginas[0]?.referencia_opaca || ''),
          // ⚠️ TROCAR DE CONTA LIMPA SELEÇÃO INVÁLIDA. Identidade do Instagram
          // e conversão personalizada são objetos DAQUELA conta: mantê-los
          // deixaria o plano carregando referências que a nova conta não
          // resolve, e o erro chegaria como "referência não encontrada" sem o
          // operador entender que a culpa foi a troca de conta.
          instagramActorRef: trocouDeConta ? '' : atual.instagramActorRef,
          // ⚠️ E as referências de PÚBLICO e de LUGAR saem junto: elas foram
          // resolvidas contra o catálogo da conta anterior. `publicos.py`
          // resolve LISTANDO o catálogo da conta escolhida, então uma
          // referência da conta antiga simplesmente não bate — e a tela não
          // pode continuar exibindo uma seleção que o plano não consegue mais
          // traduzir.
          conjuntos: !trocouDeConta ? atual.conjuntos : atual.conjuntos.map((conjunto) => ({
            ...conjunto,
            regulatoryIdentityRef: undefined,
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
            ...(trocouDeConta ? { packOrigin: undefined, assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '' } : {}),
            assetRef: !trocouDeConta && variacao.assetRef ? variacao.assetRef : resultado.imagens.some((item) => item.referencia_opaca === variacao.assetRef)
              ? variacao.assetRef : (resultado.imagens[0]?.referencia_opaca || ''),
            videoRef: !trocouDeConta && variacao.videoRef ? variacao.videoRef : (resultado.videos ?? []).some(
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
          ...((['assetRef', 'videoRef', 'midia', 'adsetKey', 'message', 'headline', 'description', 'cta', 'existingPostRef'] as string[]).includes(chave) ? {
            assetRightsConfirmed: false,
            thirdPartyIdentityCleared: false,
            assetPolicyConfirmedAt: '',
          } : {}),
          ...((chave === 'assetRef' || chave === 'videoRef' || chave === 'midia') ? {packOrigin: undefined, existingPostRef: undefined} : {}),
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
  const adicionarVariacao = (origem?: number, destino?: string) => {
    setDraft((atual) => {
      const anterior = origem === undefined ? undefined : atual.variations[origem];
      const alvo = destino ?? anterior?.adsetKey ?? (atual.conjuntos.length === 1 ? atual.conjuntos[0].key : '');
      const next = adicionarAnuncioNoConjunto(atual, alvo, anterior?.key);
      return atual.creativeMode === 'flexible' ? { ...next, creativeMode: 'flexible' } : next;
    });
    invalidar();
  };
  const removerVariacao = (posicaoAlvo: number) => {
    setDraft((atual) => {
      const restantes = atual.variations.filter((_, posicao) => posicao !== posicaoAlvo);
      return {
        ...atual,
        creativeMode: atual.creativeMode === 'flexible' ? 'flexible' : restantes.length === 1 ? 'single' : atual.creativeMode,
        variations: restantes,
      };
    });
    invalidar();
  };
  /** Trocar de modo muda o que será EMITIDO, não o que está guardado. */
  const mudarModo = (modo: Draft['creativeMode']) => {
    setDraft((atual) => ({ ...atual, creativeMode: modo,
      conjuntos: modo === 'flexible' ? atual.conjuntos.map(c => ({ ...c,
        flexibleTexts: textosFlexiveisDoConjunto(atual, c.key),
      })) : atual.conjuntos,
      variations: modo === atual.creativeMode ? atual.variations : atual.variations.map(v => ({ ...v,
        assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      })),
    }));
    invalidar();
  };
  const mudarTextosFlexiveis = (chave: string, textos: TextosFlexiveisDraft) => {
    setDraft(atual => ({ ...atual,
      conjuntos: atual.conjuntos.map(c => c.key === chave ? { ...c, flexibleTexts: textos } : c),
      variations: atual.variations.map(v => v.adsetKey === chave ? { ...v,
        assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      } : v),
    }));
    invalidar();
  };
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
    const vinculo = selecoesDePack.find(item => item.adset_key === chave);
    if (vinculo) {
      // Não deixe um vínculo durável órfão e invisível. Retirar o conjunto e
      // apagar o pack em background seria uma decisão destrutiva implícita;
      // manter a linha faria o rascunho continuar bloqueado por um conjunto
      // que já não aparece. O operador desfaz o vínculo explicitamente antes.
      setConjuntoFocadoRef(chave);
      setOrigemCriativa('pack');
      setEditandoPack(true);
      setPackAviso(`Retire “${vinculo.pack_name}” deste conjunto antes de excluí-lo.`);
      return;
    }
    setDraft((atual) => removerConjuntoSemAnuncios(atual, chave));
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
    novos.delete('pergunta');
    novos.set('etapa', proxima);
    setParams(novos);
    const reduzido = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduzido ? 'auto' : 'smooth' });
  };

  function irParaPergunta(alvo: PerguntaMeta) {
    const novos = new URLSearchParams(params);
    novos.set('pergunta', alvo.id);
    novos.set('etapa', alvo.etapa);
    setErroDaPergunta('');
    setParams(novos);
  }
  useEffect(() => { tituloDaPergunta.current?.focus({ preventScroll: true }); }, [pergunta.id]);
  function continuar() {
    const faltando = pergunta.id === 'destino' ? (!destinoValido(draft.destinationUrl) ? 'Informe uma URL HTTPS válida, sem UTMs, para continuar.' : !draft.campaignName.trim() ? 'Dê um nome para reconhecer a campanha.' : '')
      : pergunta.id === 'conta' && !draft.accountRef ? 'Escolha a conta de anúncios.'
      : pergunta.id === 'pagina' && !draft.pageRef ? 'Escolha a Página que assina os anúncios.'
      : pergunta.id === 'resultado' && !draft.categoryConfirmed ? 'Confirme a categoria da campanha.'
      : pergunta.id === 'criativos' ? motivoDeMidiaPendente
      : '';
    if (faltando) { setErroDaPergunta(faltando); return; }
    if (indice < perguntas.length - 1) irParaPergunta(perguntas[indice + 1]);
  }

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
  const selecaoPackFocada = selecoesDePack.find(
    item => item.adset_key === conjuntoFocado?.key,
  ) ?? null;
  const contextoDePack = useRef({draft, selecoesDePack});
  contextoDePack.current = {draft, selecoesDePack};
  const focoDePack = useRef({ key: conjuntoFocado?.key, accountRef: draft.accountRef });
  focoDePack.current = { key: conjuntoFocado?.key, accountRef: draft.accountRef };
  const packsPendentes = selecoesDePack.filter(item => !packMaterializado(draft, item));
  const motivoDeMidiaPendente = !selecoesCarregadas ? 'Aguarde a recuperação dos packs deste rascunho.'
    : selecoesErro ? 'Não foi possível recuperar os packs deste rascunho. Recarregue a página antes de conferir ou enviar o plano.'
    : packsPendentes.length > 0 ? `Envie o pack e monte os anúncios em ${packsPendentes.map(item => draft.conjuntos.find(c => c.key === item.adset_key)?.nome || 'conjunto salvo').join(', ')}. Os anúncios anteriores não substituem o pack escolhido.`
    : mastersSelecionados.length > 0 ? 'Salve e envie as peças selecionadas no assistente antes de conferir o plano.' : '';
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
  const podeCompilar = !motivoDeMidiaPendente
    && prontoParaCompilar(draft, capacidades, propositosDaReceita);

  async function escolherPackNoConjunto(packId: string) {
    if (!conjuntoFocado || packOcupado) return;
    const alvo = { key: conjuntoFocado.key, name: conjuntoFocado.nome, accountRef: draft.accountRef };
    // Consume a deep-link once, before the request. A failure must not apply
    // the same pack silently when the operator focuses a different ad set.
    setParams(atuais => {
      if (atuais.get('pack') !== packId) return atuais;
      const nova = new URLSearchParams(atuais); nova.delete('pack'); return nova;
    }, { replace: true });
    setPackOcupado(true); setPackAviso('Gravando o vínculo deste conjunto…');
    try {
      const salva = await fixarPackNoConjunto(
        draftRef, alvo.key, packId, selecaoPackFocada?.version ?? 0,
      );
      if (focoDePack.current.accountRef !== alvo.accountRef) return;
      setSelecoesDePack(atuais => [
        ...atuais.filter(item => item.adset_key !== salva.adset_key), salva,
      ]);
      setDraft(atual => ({ ...atual, variations: atual.variations.map(ad => ad.adsetKey === salva.adset_key ? {
        ...ad, assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      } : ad) }));
      if (focoDePack.current.key === alvo.key) {
        setOrigemCriativa('pack'); setEditandoPack(false);
      }
      setPackAviso(`“${salva.pack_name}” ficou vinculado a ${alvo.name}. O vínculo está salvo; formato, imagens e copies continuam editáveis.`);
    } catch (exc) {
      setPackAviso(exc instanceof Error ? exc.message : 'Não foi possível fixar o pack neste conjunto.');
    } finally { setPackOcupado(false); }
  }

  async function importarImagemParaVariacao(variacao: VariacaoDraft, arquivo: File) {
    if (!conjuntoFocado || arquivoOcupado || packOcupado || !draft.accountRef) return;
    setArquivoOcupado(variacao.key);
    setPackAviso(`Guardando ${arquivo.name} na biblioteca privada…`);
    try {
      const imported = await importarMidiaPrivada(
        arquivo, `${draft.campaignName || 'Campanha Meta'} · ${variacao.adName || 'nova imagem'}`,
      );
      const entry = imported.entradas.find(item => item.masterId);
      if (!entry?.masterId) {
        const rejected = imported.entradas[0];
        throw new Error(rejected?.detalhe || rejected?.motivoRecusa || 'O arquivo não produziu uma imagem utilizável.');
      }
      const pack = await salvarPack(
        `Upload · ${arquivo.name.replace(/\.[^.]+$/, '').slice(0, 120)}`,
        [entry.masterId],
      );
      alvoDoUpload.current = { packId: pack.id, variationKey: variacao.key };
      setOrigemCriativa('pack');
      await escolherPackNoConjunto(pack.id);
      setPackAviso('Imagem guardada. Confira a prévia e registre-a na conta para concluir a troca.');
    } catch (exc) {
      setPackAviso(exc instanceof Error ? exc.message : 'Não foi possível guardar esta imagem.');
    } finally {
      setArquivoOcupado(null);
    }
  }

  async function retirarPackFocado() {
    if (!conjuntoFocado || !selecaoPackFocada || packOcupado) return;
    const alvo = { key: conjuntoFocado.key, name: conjuntoFocado.nome, accountRef: draft.accountRef };
    setPackOcupado(true); setPackAviso('Retirando o vínculo deste conjunto…');
    try {
      await retirarPackDoConjunto(
        draftRef, alvo.key, selecaoPackFocada.version,
      );
      if (focoDePack.current.accountRef !== alvo.accountRef) return;
      setSelecoesDePack(atuais => atuais.filter(
        item => item.adset_key !== alvo.key,
      ));
      if (focoDePack.current.key === alvo.key) { setOrigemCriativa('conta'); setEditandoPack(false); }
      setPackAviso(`O pack foi retirado de ${alvo.name}.`);
    } catch (exc) {
      setPackAviso(exc instanceof Error ? exc.message : 'Não foi possível retirar o pack deste conjunto.');
    } finally { setPackOcupado(false); }
  }

  const packDeLinkAplicado = useRef<string | null>(null);
  useEffect(() => {
    if (!packRef || rascunhoPersistido.blocked || !selecoesCarregadas || !conjuntoFocado
        || packDeLinkAplicado.current === `${draftRef}:${packRef}`) return;
    if (!/^[0-9a-f-]{36}$/i.test(packRef)) {
      setPackAviso('Referência de pack inválida.'); return;
    }
    packDeLinkAplicado.current = `${draftRef}:${packRef}`;
    void escolherPackNoConjunto(packRef);
  }, [packRef, selecoesCarregadas, conjuntoFocado?.key, rascunhoPersistido.blocked]);

  useEffect(() => {
    if (selecaoPackFocada) {
      setOrigemCriativa('pack');
      setEditandoPack(false);
    }
  }, [conjuntoFocado?.key, selecaoPackFocada?.pack_id]);

  /** O que ainda impede o próximo ato — inteiro, em linguagem de operador. */
  const faltas = useMemo(() => {
    const lista: string[] = [];
    if (motivoDeMidiaPendente) lista.push(motivoDeMidiaPendente);
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
      const m = conjunto.mensuracao;
      if (m.proposito === 'OPTIMIZE') {
        if (!m.fonteRef || !m.fonteTipo) lista.push(`Escolha o pixel ou dataset da conta${onde}, em Conversão.`);
        if (!m.conversaoRef && !m.eventoPadrao) lista.push(`Escolha um evento padrão ou uma conversão personalizada${onde}.`);
        if (m.conversaoRef && m.eventoPadrao) lista.push(`Escolha apenas um evento de otimização${onde}: padrão ou conversão personalizada.`);
      } else if (m.fonteRef && !m.fonteTipo) {
        lista.push(`Selecione novamente o pixel ou dataset${onde}, para identificar seu tipo.`);
      }
    });
    if (estados.publico !== 'pronto') {
      lista.push('Confira o público: escolha ao menos um lugar para alcançar e uma faixa etária válida.');
    }
    if (!destinoValido(draft.destinationUrl)) lista.push('Informe uma URL de destino HTTPS válida, sem credenciais ou UTMs.');
    if (draft.creativeMode === 'flexible') {
      if (draft.recipeId !== 'WEB_SALES_CONVERSION') lista.push('O formato flexível exige o resultado Vendas. Tráfego e Cadastros usam anúncios individuais.');
      if (emitidas.some(item => item.existingPostRef)) lista.push('Não misture publicação existente com grupos flexíveis: escolha imagens para um novo anúncio.');
      if (draft.conjuntos.some(c => new Set(emitidas.filter(v => v.adsetKey === c.key).map(v => v.cta)).size > 1)) lista.push('Use o mesmo botão em todas as peças flexíveis de cada conjunto.');
      draft.conjuntos.forEach(c => pendenciasDosTextosFlexiveis(textosFlexiveisDoConjunto(draft, c.key)).forEach(f => lista.push(`${c.nome}: ${f}`)));
    }
    {
      if (emitidas.some((item) => item.midia === 'video')) {
        lista.push(`Um anúncio usa vídeo. ${BLOQUEIOS.videoNoCorpo}`);
      }
      const chaves = new Set(draft.conjuntos.map((item) => item.key));
      emitidas.forEach((item, posicao) => {
        if (!chaves.has(item.adsetKey)) {
          lista.push(`O anúncio ${posicao + 1} aponta para um conjunto que não existe mais.`);
        }
        if (item.midia !== 'video') {
          pendenciasDaVariacao(item, draft).forEach(falta => lista.push(`Anúncio ${posicao + 1}: ${falta}`));
        }
      });
    }
    return [...new Set(lista)];
  }, [draft, estados, emitidas, motivoDeMidiaPendente]);

  /** ⚠️ UMA PORTA POR CONTRATO, e a escolha é a forma do plano.
   *
   * A resposta do V2 carrega `resumo`; a do V1 não tem esse campo, e a revisão
   * do V1 continua sendo a que sempre foi. Fundir os dois numa chamada só faria
   * um plano de conjunto único perder a rota que ainda sustenta aprovação e
   * criação PAUSED. */
  const compilar = async (automatico = false) => {
    if (motivoDeMidiaPendente) { setErroDaPergunta(motivoDeMidiaPendente); return; }
    const meu = ++selo.current;
    focarFeedback.current = !automatico;
    setOcupado('compilar');
    setFeedbackDoPlano('Conferindo o plano no servidor… Nenhum anúncio será criado.');
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
      setFeedbackDoPlano('Plano conferido. Próximo passo: validar na Meta, sem criar nada.');
    } catch (exc) {
      if (meu === selo.current) {
        setAvisos(avisosDoErro(exc));
        setFeedbackDoPlano('Não foi possível conferir o plano. Veja o motivo abaixo e tente novamente.');
      }
    } finally {
      // ⚠️ SEM condição: descartar a RESPOSTA obsoleta é correto; deixar a tela
      // ocupada por causa dela, não.
      setOcupado(null);
    }
  };

  const validar = async (automatico = false) => {
    if (motivoDeMidiaPendente) { setErroDaPergunta(motivoDeMidiaPendente); return; }
    const meu = ++selo.current;
    focarFeedback.current = !automatico;
    setOcupado('validar');
    setFeedbackDoPlano('Validando na Meta… Aguarde o resultado. Nenhum anúncio será criado.');
    setAvisos([]);
    try {
      if (contrato === 'V2') {
        const resultado = await pautadorApi.validarPlanoMetaV2(paraPlanoV2(draft));
        if (meu !== selo.current) return;
        setValidacao(resultado);
        setResumo(resultado.resumo);
        setFeedbackDoPlano(resultado.ok ? 'Validação concluída nas operações independentes. As demais serão verificadas durante a criação pausada.' : 'A validação retornou pendências. Confira o resultado abaixo.');
      } else {
        const resultado = await pautadorApi.validarPlanoMeta(paraPlano(draft));
        if (meu !== selo.current) return;
        setValidacao(resultado);
        setFeedbackDoPlano(resultado.ok ? 'Validação concluída nas operações independentes. As demais serão verificadas durante a criação pausada.' : 'A validação retornou pendências. Confira o resultado abaixo.');
      }
    } catch (exc) {
      if (meu === selo.current) {
        setAvisos(avisosDoErro(exc));
        setFeedbackDoPlano('Não foi possível validar na Meta. Veja o motivo abaixo e tente novamente.');
      }
    } finally {
      setOcupado(null);
    }
  };

  const tentativaAutomatica = useRef('');
  useEffect(() => {
    if (etapa !== 'revisao' || params.get('modo') === 'demo' || ocupado || carregando || !podeCompilar || faltas.length || aprovacao) return;
    const fase = !compilacao ? 'compilar' : (!validacao && capacidades.validateOnly ? 'validar' : null);
    if (!fase) return;
    const chave = `${fase}:${JSON.stringify(draft)}`;
    if (tentativaAutomatica.current === chave) return;
    const timer = window.setTimeout(() => {
      tentativaAutomatica.current = chave;
      void (fase === 'compilar' ? compilar(true) : validar(true));
    }, 600);
    return () => window.clearTimeout(timer);
  }, [etapa, draft, ocupado, carregando, podeCompilar, faltas.length, compilacao, validacao, capacidades.validateOnly, aprovacao, operacao]);

  /** Um catálogo da conta. Leitura automática ou atualização explícita.
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

  /** Pixel, dataset e conversões são contexto da conta, não uma decisão do
   * operador. Ao entrar na etapa, a leitura começa sozinha uma única vez por
   * conta. Depois de uma falha, o catálogo mantém o botão apenas como retry. */
  const mensuracaoAutomatica = useRef('');
  useEffect(() => {
    if (pergunta.id !== 'conversao' || params.get('modo') === 'demo' || !draft.accountRef
        || ocupado || catalogoDeMensuracao?.contaRef === draft.accountRef) return;
    const key = `${draftRef}:${draft.accountRef}`;
    if (mensuracaoAutomatica.current === key) return;
    mensuracaoAutomatica.current = key;
    const timer = window.setTimeout(() => { void lerConversoes(); }, 120);
    return () => window.clearTimeout(timer);
  }, [pergunta.id, draftRef, draft.accountRef, ocupado, catalogoDeMensuracao?.contaRef]);

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
    if (motivoDeMidiaPendente) throw new PautadorApiError(motivoDeMidiaPendente, 409);
    if (!await rascunhoPersistido.saveNow() || !aindaEDoMesmoRascunho()) {
      throw new PautadorApiError('Salve o rascunho no servidor antes de aprovar. Se houver conflito, recupere a versão salva.', 409);
    }
    const prova = validacao?.prova_duravel;
    if (!validacao?.ok || !prova?.registrada || !prova.validation_id) {
      throw new PautadorApiError(
        'A validação desta versão não foi gravada como prova durável. Valide de novo '
        + 'antes de aprovar.', 409);
    }
    const resultado = await pautadorApi.aprovarCriacaoMeta({
      plano: contratoDoPlano(draft).contrato === 'V2' ? paraPlanoV2(draft) : paraPlano(draft),
      planoSha256: validacao.plano_sha256,
      validationId: prova.validation_id,
      confirmacaoDigitada,
    });
    // ⚠️ APROVAR ainda não criou nada, então a resposta obsoleta é DESCARTADA.
    if (!aindaEDoMesmoRascunho()) return;
    setAprovacao(resultado.aprovacao);
    // An old dispatched operation must not lock the newly approved plan.
    // Its durable receipt remains reachable by its own operation URL.
    // The server controls cross-approval step reuse, never the browser.
    if (operacaoRef && operacaoRef !== resultado.aprovacao.approval_id) {
      fixarOperacaoNaUrl(resultado.aprovacao.approval_id);
    }
  });

  const criar = () => umaVezSo('criar', async () => {
    if (motivoDeMidiaPendente) throw new PautadorApiError(motivoDeMidiaPendente, 409);
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
      // Keep the durable incident receipt even if the following GET fails.
      // Match the operation before applying it; never use another draft's receipt.
      const incidente = exc instanceof PautadorApiError
        ? (exc.corpo as {recibo?: ReciboCriacaoMeta} | undefined)?.recibo : undefined;
      if (incidente?.approval_id === referencia && Array.isArray(incidente.steps)) {
        aplicarRecibo(referencia, incidente, ++seloDaOperacao.current);
      }
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

  /** A aprovação do servidor congela o contrato completo, inclusive o orçamento V2. */
  const criacaoDisponivel = capacidades.criarPausada && params.get('modo') !== 'demo';

  const totalDeAnuncios = draft.creativeMode === 'flexible' ? new Set(emitidas.map(v => v.adsetKey)).size : emitidas.length;
  const linhasDoPedido: LinhaDoPedido[] = [
    { rotulo: 'Conta', valor: conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : null, fonte: 'a Meta, agora' },
    { rotulo: 'Página', valor: pagina?.nome ?? null, fonte: 'a Meta, agora' },
    { rotulo: 'Campanha', valor: draft.campaignName || null, fonte: 'você, agora' },
    { rotulo: 'Receita', valor: receita ? receita.rotulo : draft.recipeId, fonte: receita ? 'o registro de receitas' : 'a receita padrão' },
    { rotulo: 'Contrato do plano', valor: contrato === 'V1' ? 'V1 · conjunto único' : 'V2 · conjuntos e orçamentos individualizados', fonte: 'a forma deste plano' },
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
          <div className="grid gap-4">
            {pergunta.id !== 'pagina' && <EscolherBusinessMeta demo={params.get('modo') === 'demo'} onAccounts={setContas}
              onChangeBusiness={() => mudar('accountRef', '')} />}
            {pergunta.id !== 'pagina' && <Campo id="meta-conta" rotulo="Conta de anúncios" ajuda="Use uma conta ativa em reais.">
              <select id="meta-conta" className={campo} value={draft.accountRef} disabled={carregando}
                onChange={(e) => mudar('accountRef', e.target.value)}>
                <option value="">Selecione uma conta real</option>
                {draft.accountRef && !contas.some(item => item.referencia_opaca === draft.accountRef) &&
                  <option value={draft.accountRef}>Conta salva · aguardando conferência do acesso</option>}
                {contas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado || 'ID protegido'} · {item.moeda || 'moeda não lida'}
                  </option>
                ))}
              </select>
            </Campo>}
            {pergunta.id === 'pagina' && <Campo id="meta-pagina" rotulo="Página do Facebook" ajuda="A Página assina os anúncios e precisa estar disponível para promoção nesta conta.">
              <select id="meta-pagina" className={campo} value={draft.pageRef}
                disabled={!draft.accountRef || ocupado === 'ativos'}
                onChange={(e) => mudar('pageRef', e.target.value)}>
                <option value="">Selecione uma Página desta conta</option>
                {draft.pageRef && !paginas.some(item => item.referencia_opaca === draft.pageRef) &&
                  <option value={draft.pageRef}>Página salva · aguardando conferência do acesso</option>}
                {paginas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado}
                  </option>
                ))}
              </select>
            </Campo>}
          </div>
          <details className="text-sm"><summary className="cursor-pointer py-2 text-muted-foreground">Detalhes da conexão</summary>
          <BlocoDeEvidencia titulo="O que foi lido da conta" tom="verificado">
            <LinhaDeFato rotulo="Moeda" valor={conta?.moeda ?? null} fonte="a Meta" ausencia="não lida" />
            <LinhaDeFato rotulo="Fuso da conta" valor={conta?.fuso ?? null} fonte="a Meta" ausencia="não lido" />
            <LinhaDeFato rotulo="Imagens disponíveis" valor={draft.accountRef ? imagens.length : null} fonte="a Meta" ausencia="não lidas" />
            <LinhaDeFato rotulo="Vídeos disponíveis" valor={draft.accountRef ? videos.length : null} fonte="a Meta" ausencia="não lidos" />
            {/* ⚠️ Identidade do Instagram: ausência DECLARADA, não silêncio. Sem
                ela o posicionamento no Instagram é recusado pelo backend, e a
                etapa de público mostra a caixa fechada com esta mesma causa. */}
            <LinhaDeFato rotulo="Identidade do Instagram" valor={draft.instagramActorRef || null} fonte="a Meta" ausencia="não lida por esta bancada" />
          </BlocoDeEvidencia></details>
        </>
      );
      case 'campanha': return pergunta.id === 'destino' ? (
        <>
          <Campo id="meta-destino-campanha" rotulo="Endereço da página">
            <Input id="meta-destino-campanha" type="url" placeholder="https://seusite.com/materia"
              value={draft.destinationUrl} onChange={e => mudar('destinationUrl', e.target.value)} />
          </Campo>
          <NomenclaturaAutomatica
            draft={draft} draftRef={draftRef} save={rascunhoPersistido.saveNow} sizes={tamanhosParaNomes}
            conversionNames={conversoesParaNomes}
            demo={params.get('modo') === 'demo'} onChange={next => { setDraft(next); invalidar(); }} />
          <Campo id="meta-nome" rotulo="Como vamos chamar esta campanha?">
            <Input id="meta-nome" placeholder="Ex.: Encceja · Brasil · Setembro" value={draft.campaignName}
              onChange={e => mudar('campaignName', e.target.value)} />
          </Campo>
          <p className="text-sm text-muted-foreground">UTMs automáticas: receita por conjunto e total por campanha.</p>
          <details className="text-sm"><summary className="cursor-pointer py-2">Ver como o acompanhamento funciona</summary>
            <TrackingAutomatico destino={draft.destinationUrl} />
          </details>
        </>
      ) : (
        <>
          <PainelDeReceita receitas={receitas} erroDoCatalogo={catalogoErro}
            escolhida={draft.recipeId} onEscolher={(id) => {
              if (id === draft.recipeId) return;
              mudar('recipeId', id);
              setDraft(atual => ({ ...atual, conjuntos: atual.conjuntos.map(c => ({
                ...c, mensuracao: { ...c.mensuracao, proposito: id === RECEITA_PADRAO ? 'REPORT_ONLY' : 'OPTIMIZE',
                  fonteRef: '', fonteTipo: '', conversaoRef: '', eventoPadrao: '' },
              })) }));
            }} />
          <Campo id="meta-categoria" rotulo="A campanha envolve crédito, emprego, moradia ou política?"
            ajuda="A Meta exige o enquadramento da campanha. Se envolver uma dessas categorias, prepare-a no Gerenciador Meta; este criador ainda não oferece essa configuração.">
            <select id="meta-categoria" className={campo} value={draft.categoryConfirmed ? 'none' : categoriaEspecial ? 'special' : ''}
              onChange={e => { setCategoriaEspecial(e.target.value === 'special'); mudar('categoryConfirmed', e.target.value === 'none'); }}>
              <option value="">Escolha o enquadramento</option>
              <option value="none">Não, nenhuma dessas categorias</option>
              <option value="special">Sim ou preciso verificar</option>
            </select>
          </Campo>
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
            demo={params.get('modo') === 'demo'}
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
          <section aria-label="Anúncios por conjunto" className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div><h3 className="text-xl font-semibold">Escolha o conjunto para montar seus anúncios</h3>
                <p className="mt-1 text-sm text-muted-foreground">Cada conjunto tem sua seleção. A mesma peça pode ser reutilizada sem mover o original.</p></div>
              <p id="meta-limite-lote" className="text-sm tabular-nums text-muted-foreground">{emitidas.length} / {LIMITE_VARIACOES} {draft.creativeMode === 'flexible' ? 'imagens no anúncio flexível' : 'anúncios na campanha'}</p>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2" role="group" aria-label="Escolher conjunto dos anúncios">
              {draft.conjuntos.map((c, i) => {
                const ads = emitidas.filter(v => v.adsetKey === c.key);
                const prontos = ads.filter(v => variacaoCompleta(v, draft)).length;
                const packDoConjunto = selecoesDePack.find(item => item.adset_key === c.key);
                return <button type="button" key={c.key} aria-pressed={conjuntoFocado?.key === c.key}
                  onClick={() => setConjuntoFocadoRef(c.key)}
                  className={cn('min-w-48 max-w-80 shrink-0 rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    conjuntoFocado?.key === c.key ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card hover:border-primary/50')}>
                  <span className="block truncate font-semibold">{c.nome || `Conjunto ${i + 1}`}</span>
                  <span className="mt-1 block text-sm">{ads.length ? `${prontos} de ${ads.length} ${draft.creativeMode === 'flexible' ? 'imagens prontas · 1 anúncio' : 'anúncios prontos'}` : 'Ainda sem anúncios'}</span>
                  {packDoConjunto && <span className="mt-2 flex items-center gap-1 text-xs font-semibold"><Lock className="h-3 w-3" aria-hidden />{packDoConjunto.pack_name} vinculado</span>}
                </button>;
              })}
            </div>
            {conjuntoFocado && <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
              <p className="text-sm">Editando <strong>{conjuntoFocado.nome}</strong></p>
              <Button type="button" disabled={draft.variations.length >= LIMITE_VARIACOES}
                onClick={() => { adicionarVariacao(undefined, conjuntoFocado.key); setOrigemCriativa('conta'); }}>
                <Plus className="h-4 w-4" aria-hidden />{draft.creativeMode === 'flexible' ? 'Adicionar imagem neste conjunto' : 'Adicionar anúncio neste conjunto'}
              </Button>
            </div>}
          </section>
          <GrupoDeEscolha<'conta' | 'assistente' | 'pack'> rotuloAcessivel="Origem dos criativos" colunas="sm:grid-cols-3" valor={origemCriativa}
            onEscolher={valor => {
              if (selecaoPackFocada && valor !== 'pack') {
                setPackAviso('Este conjunto já tem um pack vinculado. Use “Trocar ou retirar” para mudar a origem sem perder a decisão por engano.');
                return;
              }
              setOrigemCriativa(valor); if (valor === 'assistente') setAssistenteAberto(true);
            }}
            opcoes={[
              { id: 'assistente', nome: 'Criar com o assistente', detalhe: 'Briefing, estratégia e produção de imagens.' },
              { id: 'pack', nome: 'Usar pack salvo', detalhe: 'Reaproveite as peças da sua biblioteca.' },
              { id: 'conta', nome: 'Usar imagens da conta', detalhe: 'Escolha a peça e ajuste o texto do anúncio.' },
            ]} />
          {origemCriativa === 'pack' && selecaoPackFocada && !editandoPack && <section role="status" className="rounded-xl border border-success/40 bg-success/10 p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex gap-3"><span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-full bg-success/15 text-success"><Lock className="h-4 w-4" aria-hidden /></span><div>
                <p className="font-semibold">Pack vinculado neste conjunto</p>
                <p className="mt-1 text-sm"><strong>{selecaoPackFocada.pack_name}</strong> · {selecaoPackFocada.master_refs.length} peça(s)</p>
                <p className="mt-1 text-xs text-muted-foreground">Vínculo salvo no banco · versão {selecaoPackFocada.version}. Depois do registro, imagens, formato e banco de copies continuam editáveis.</p>
              </div></div>
              <Button type="button" variant="outline" disabled={packOcupado} onClick={() => setEditandoPack(true)}>Trocar ou retirar</Button>
            </div>
          </section>}
          {origemCriativa === 'pack' && (!selecaoPackFocada || editandoPack) && <section className="space-y-4">
            {selecaoPackFocada && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm"><span>Você está trocando <strong>{selecaoPackFocada.pack_name}</strong> apenas em <strong>{conjuntoFocado?.nome}</strong>.</span><Button type="button" variant="destructive" disabled={packOcupado} onClick={() => void retirarPackFocado()}>Retirar deste conjunto</Button></div>}
            <EscolherPack selecionado={selecaoPackFocada?.pack_id ?? null}
              onEscolher={id => void escolherPackNoConjunto(id)} />
          </section>}
          {origemCriativa === 'pack' && selecaoPackFocada && !editandoPack && <PrepararPackMeta
            key={`${draft.accountRef}:${draftRef}:${selecaoPackFocada.adset_key}:${selecaoPackFocada.pack_id}:${selecaoPackFocada.version}`}
            selection={selecaoPackFocada} draftRef={draftRef} accountRef={draft.accountRef} accountName={conta?.nome || ''}
            setName={conjuntoFocado?.nome || ''} demo={params.get('modo') === 'demo'}
            attached={packMaterializado(draft, selecaoPackFocada)} onAttach={(pack, receipt) => {
              const atual = contextoDePack.current;
              const vigente = atual.selecoesDePack.find(s => s.adset_key === selecaoPackFocada.adset_key);
              if (!vigente || vigente.pack_id !== selecaoPackFocada.pack_id || vigente.version !== selecaoPackFocada.version)
                throw new Error('O vínculo do conjunto mudou durante o envio. As imagens registradas foram preservadas; revise a seleção.');
              const uploadTarget = alvoDoUpload.current?.packId === pack.id
                ? alvoDoUpload.current.variationKey : undefined;
              const next = materializarPack(atual.draft, vigente, pack, draft.accountRef, receipt, uploadTarget);
              if (uploadTarget) alvoDoUpload.current = null;
              setImagens(current => {
                const received = receipt.resultados.map(r => {
                  const item = pack.manifest.items.find(i => i.master_ref === r.master_ref);
                  return {referencia_opaca: r.asset_ref!, nome: item?.nome || pack.nome, tipo: 'image_asset' as const,
                    id_mascarado: null, largura: item?.largura ?? null, altura: item?.altura ?? null, preview_disponivel: true};
                });
                return [...current.filter(i => !received.some(r => r.referencia_opaca === i.referencia_opaca)), ...received];
              });
              setDraft(next); invalidar();
              setPackAviso('Imagens registradas e anúncios montados neste conjunto. Revise os textos e confirme os direitos de uso abaixo.');
            }} />}
          {assistenteAberto && <section hidden={origemCriativa !== 'assistente'} className="space-y-3">
            <p className="text-sm text-muted-foreground">Crie e aprove suas peças aqui. O envio das imagens à conta é uma etapa separada; a geração não publica anúncios.</p>
            <AssistenteNaJornada ref={iframeAssistente} projeto={projetoCriativo} destinationUrl={draft.destinationUrl} campaignObjective={receita?.objetivo} />
            <Button variant="outline" onClick={() => setOrigemCriativa('conta')}>Escolher imagens disponíveis na conta</Button>
          </section>}
          {packAviso && <p role="status" className="text-sm text-muted-foreground">{packAviso}</p>}
          {mastersSelecionados.length > 0 && <div role="status" className="rounded-lg border border-border p-4 text-sm">
            {mastersSelecionados.length} peça(s) selecionada(s) no Estúdio. Falta registrar essas imagens na conta com avaliação de política antes de vinculá-las aos anúncios. Elas ainda não fazem parte do plano compilado.
            <Button variant="ghost" className="mt-2" onClick={() => {
              setMastersSelecionados([]); setPackAviso(''); setOrigemCriativa('conta');
              const nova = new URLSearchParams(params); nova.delete('pack'); setParams(nova);
            }}>Retirar seleção do Estúdio e usar imagens da conta</Button>
          </div>}
          {copySelecionada && <ImportarCopyDoAssistente
            key={`${copySelecionada.runRef}:${copySelecionada.creativeRef}`}
            selecao={copySelecionada} anuncios={variacoesEmitidas(draft).filter(v => v.adsetKey === conjuntoFocado?.key)}
            onCancelar={() => setCopySelecionada(null)}
            onAplicar={(key, copy) => {
              const pai = draft.variations.find(v => v.key === key)?.adsetKey;
              let banco: TextosFlexiveisDraft | undefined;
              if (draft.creativeMode === 'flexible' && pai) {
                const anterior = textosFlexiveisDoConjunto(draft, pai);
                const adicionar = (valores: string[], texto: string) => [...new Set([...valores.filter(t => t.trim()), texto.trim()].filter(Boolean))];
                banco = { primary_text: adicionar(anterior.primary_text, copy.message),
                  headline: adicionar(anterior.headline, copy.headline), description: adicionar(anterior.description, copy.description) };
                if (pendenciasDosTextosFlexiveis(banco).length) {
                  setErroDaPergunta('Não foi possível acrescentar a copy. Revise o banco de textos deste conjunto: o limite é de 5 opções por tipo.');
                  return;
                }
              }
              setDraft(atual => ({ ...atual,
                conjuntos: banco ? atual.conjuntos.map(c => c.key === pai ? { ...c, flexibleTexts: banco } : c) : atual.conjuntos,
                variations: atual.variations.map(v => banco && v.adsetKey === pai ? {
                  ...v, cta: copy.cta, assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
                } : v.key === key ? {
                ...v, message: copy.message, headline: copy.headline,
                description: copy.description, cta: copy.cta,
                assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
              } : v) }));
              invalidar(); setCopySelecionada(null); setCopyAplicada(true); setOrigemCriativa('conta');
            }} />}
          {copyAplicada && <p role="status" className="text-sm text-success">Texto importado do assistente. Revise a imagem e a combinação final antes de conferir o plano.</p>}
          <div hidden={origemCriativa !== 'conta' && !(selecaoPackFocada && packMaterializado(draft, selecaoPackFocada))} className="space-y-5">
          {draft.creativeMode === 'single' && draft.variations.length > 1 && <div role="alert" className="space-y-2">
            <p>Há anúncios guardados fora da seleção anterior. Inclua-os para revisar todos os conjuntos.</p>
            <Button onClick={() => mudarModo('batch')}>Incluir todos os anúncios guardados</Button>
          </div>}
          {avisoDaDuplicacao && <p role="status" className="rounded-lg bg-primary/10 p-3 text-sm">{avisoDaDuplicacao}</p>}
          <FormatoDeCriativos draft={draft} onChange={mudarModo} />
          {draft.creativeMode === 'flexible' && conjuntoFocado && <VarinhaDeCopy
            key={`copy:${draftRef}:${conjuntoFocado.key}`} draft={draft} draftRef={draftRef} adsetKey={conjuntoFocado.key}
            save={rascunhoPersistido.saveNow} demo={params.get('modo') === 'demo'}
            onApply={textos => mudarTextosFlexiveis(conjuntoFocado.key, textos)} />}
          {draft.creativeMode === 'flexible' && conjuntoFocado && <TextosDoAnuncioFlexivel
            key={conjuntoFocado.key} conjunto={conjuntoFocado.nome}
            imagens={emitidas.filter(v => v.adsetKey === conjuntoFocado.key).length}
            value={textosFlexiveisDoConjunto(draft, conjuntoFocado.key)}
            onChange={textos => mudarTextosFlexiveis(conjuntoFocado.key, textos)} />}
          {!emitidas.some(v => v.adsetKey === conjuntoFocado?.key) && <p className="py-8 text-center text-muted-foreground">Este conjunto ainda não tem anúncios. Use “Adicionar anúncio neste conjunto” para começar.</p>}
          {(
            <div className="space-y-5">
              {/* ⚠️ O bloqueio de vídeo é do CONTRATO, não da capacidade: nem
                  `variations[]` (V1) nem `ads[]` (V2) têm campo de vídeo. Mesmo
                  que o servidor liberasse a capacidade, o corpo sairia com a
                  peça vazia. A capacidade continua sendo mostrada porque ela
                  explica a segunda metade do bloqueio. */}
              {draft.variations.some(v => v.midia === 'video') && <PainelDeBloqueio
                titulo="Anúncio em vídeo não pode ser emitido"
                bloqueios={[{
                  codigo: 'META_VIDEO_NOT_IN_CONTRACT', severidade: 'alta',
                  titulo: 'Nenhum dos dois contratos transporta vídeo',
                  detalhe: `${BLOQUEIOS.videoNoCorpo}${
                    capacidades.video ? '' : ` ${capacidades.videoMotivo || ''}`}`,
                }]}
              />}
              {draft.variations.map((variacao, posicao) => ({ variacao, posicao })).filter(({ variacao, posicao }) => variacao.adsetKey === conjuntoFocado?.key && (draft.creativeMode !== 'single' || posicao === 0)).map(({ variacao, posicao }) => {
                const lista = variacao.midia === 'video' ? videos : imagens;
                const escolhida = variacao.midia === 'video' ? variacao.videoRef : variacao.assetRef;
                const ativo = lista.find((item) => item.referencia_opaca === escolhida);
                return (
                  <section key={variacao.key} className="overflow-hidden rounded-lg border border-border bg-muted/20">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                      <div className="min-w-0">
                        <p className="kicker">{draft.creativeMode === 'flexible' ? 'Imagem do anúncio flexível' : 'Anúncio'} {posicao + 1}</p>
                        <p className="text-sm font-medium text-primary">Conjunto: {draft.conjuntos.find(c => c.key === variacao.adsetKey)?.nome || 'Escolha um conjunto válido'}</p>
                        <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
                          {variacaoEfetiva(draft, variacao).headline || 'Sem título'}
                        </p>
                        <p className="sr-only" data-testid="variacao-chave">{variacao.key}</p>
                        <p className="sr-only" data-testid="variacao-conjunto">{variacao.adsetKey}</p>
                      </div>
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <ChipDeEstado
                          glifo={variacaoCompleta(variacao, draft) ? CircleCheck : CircleDot}
                          palavra={variacaoCompleta(variacao, draft) ? 'completo' : 'incompleto'}
                          descricao={variacaoCompleta(variacao, draft)
                            ? 'este anúncio tem peça, textos e chamada para ação'
                            : pendenciasDaVariacao(variacao, draft).join(' ')}
                          tom={variacaoCompleta(variacao, draft) ? 'bom' : 'atencao'}
                        />
                        {(
                          <>
                            <Button type="button" variant="ghost" size="sm"
                              aria-describedby="meta-limite-lote"
                              disabled={draft.variations.length >= LIMITE_VARIACOES}
                              onClick={() => adicionarVariacao(posicao)}>
                              <Copy className="mr-1.5 h-4 w-4" aria-hidden />Duplicar neste conjunto
                            </Button>
                            <Button type="button" variant="outline" size="sm"
                              disabled={draft.variations.length >= LIMITE_VARIACOES}
                              onClick={() => {
                                setDraft(current => duplicarParaTrocarImagem(current, variacao.key));
                                invalidar();
                                setAvisoDaDuplicacao('Cópia adicionada neste conjunto. Os textos foram mantidos; escolha a nova imagem e confirme seus direitos de uso.');
                              }}>
                              <ImageIcon className="mr-1.5 h-4 w-4" aria-hidden />Duplicar e trocar imagem
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
                    {pendenciasDaVariacao(variacao, draft).length > 0 && <details className="border-b border-border px-4 py-3 text-sm">
                      <summary className="cursor-pointer font-medium text-warning">O que falta neste anúncio ({pendenciasDaVariacao(variacao, draft).length})</summary>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-foreground">
                        {pendenciasDaVariacao(variacao, draft).map(falta => <li key={falta}>{falta}</li>)}
                      </ul>
                      <p className="mt-2 text-muted-foreground">Ao reabrir o rascunho, confira novamente as permissões de uso da peça. Salvar a montagem não salva uma autorização de publicação.</p>
                    </details>}
                    <div className="grid gap-5 p-4 lg:grid-cols-[minmax(190px,30%)_1fr]">
                      <div>
                        <PreviaDaPeca accountRef={draft.accountRef} ativo={ativo}
                          uploadBusy={arquivoOcupado === variacao.key}
                          onUpload={draft.accountRef && !variacao.existingPostRef
                            ? file => void importarImagemParaVariacao(variacao, file) : undefined} />
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
                        {variacao.existingPostRef && <div className="space-y-2 text-sm text-muted-foreground md:col-span-2">
                          <p>Este rascunho antigo ainda aponta para uma publicação existente. Converta-o para uma imagem editável antes de trocar mídia ou usar o formato flexível.</p>
                          <Button type="button" variant="secondary" disabled={ocupado !== null}
                            onClick={() => mudarVariacao(posicao, 'existingPostRef', undefined)}>Converter para imagem editável</Button>
                        </div>}
                        <Campo id={`meta-peca-${posicao}`} rotulo={variacao.midia === 'video' ? 'Vídeo da conta' : 'Imagem da conta'}>
                          <SelecionarAtivoMeta id={`meta-peca-${posicao}`} items={lista} value={escolhida}
                            disabled={!draft.accountRef || ocupado === 'ativos' || Boolean(variacao.existingPostRef)}
                            onChange={(ref) => mudarVariacao(
                              posicao, variacao.midia === 'video' ? 'videoRef' : 'assetRef', ref)} />
                        </Campo>
                        <details className="md:col-span-2"><summary className="cursor-pointer text-sm text-muted-foreground">Nomes internos do anúncio e do criativo</summary><div className="mt-3 grid gap-3 md:grid-cols-2">
                        <Campo id={`meta-ad-name-${posicao}`} rotulo="Nome do anúncio">
                          <Input id={`meta-ad-name-${posicao}`} value={variacao.adName}
                            onChange={(e) => mudarVariacao(posicao, 'adName', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-creative-name-${posicao}`} rotulo="Nome do criativo">
                          <Input id={`meta-creative-name-${posicao}`} value={variacao.creativeName}
                            onChange={(e) => mudarVariacao(posicao, 'creativeName', e.target.value)} />
                        </Campo>
                        </div></details>
                        {draft.creativeMode !== 'flexible' ? <><Campo id={`meta-primary-${posicao}`} rotulo="Texto principal" largo>
                          <Textarea id={`meta-primary-${posicao}`} rows={3} value={variacao.message} readOnly={Boolean(variacao.existingPostRef)}
                            onChange={(e) => mudarVariacao(posicao, 'message', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-headline-${posicao}`} rotulo="Título">
                          <Input id={`meta-headline-${posicao}`} value={variacao.headline} readOnly={Boolean(variacao.existingPostRef)}
                            onChange={(e) => mudarVariacao(posicao, 'headline', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-description-${posicao}`} rotulo="Descrição">
                          <Input id={`meta-description-${posicao}`} value={variacao.description} readOnly={Boolean(variacao.existingPostRef)}
                            onChange={(e) => mudarVariacao(posicao, 'description', e.target.value)} />
                        </Campo>
                        </> : <p className="md:col-span-2 text-sm text-muted-foreground">Esta imagem usará as variações de texto do conjunto, editadas acima. Ela pode aparecer com qualquer uma dessas opções.</p>}
                        <Campo id={`meta-cta-${posicao}`} rotulo="Chamada para ação" largo>
                          <select id={`meta-cta-${posicao}`} className={campo} value={variacao.cta} disabled={Boolean(variacao.existingPostRef)}
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
                    <ReutilizarEmConjunto draft={draft} origem={variacao.key} onDuplicar={destino => adicionarVariacao(posicao, destino)} />
                  </section>
                );
              })}

            </div>
          )}
          </div>
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
          {motivoDeMidiaPendente && <div role="alert" className="space-y-3 rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm">
            <p>{motivoDeMidiaPendente}</p>
            <Button variant="secondary" onClick={() => {
              if (packsPendentes[0]) setConjuntoFocadoRef(packsPendentes[0].adset_key);
              irParaPergunta(perguntasMeta(true).find(p => p.id === 'criativos')!);
            }}>Voltar ao pack e concluir envio</Button>
          </div>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
            <div><h3 className="font-display text-xl font-semibold">{draft.campaignName || 'Sua campanha'}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{conta?.nome || 'Conta salva'} · {draft.conjuntos.length} conjuntos · {totalDeAnuncios} anúncios{draft.creativeMode === 'flexible' ? ` flexíveis com ${emitidas.length} imagens` : ' no rascunho'}</p></div>
            <span className="inline-flex items-center gap-2 text-sm font-medium"><Lock className="h-4 w-4" aria-hidden />Começa pausada</span>
          </div>
          <RevisaoHumanaDosAnuncios draft={draft} anuncios={emitidas} bloqueado={Boolean(motivoDeMidiaPendente)}
            onCategoria={value => mudar('categoryConfirmed', value)}
            onAnuncio={(key, value) => {
              setDraft(atual => ({ ...atual, variations: atual.variations.map(ad => ad.key === key ? {
                ...ad, assetRightsConfirmed: value, thirdPartyIdentityCleared: value,
                assetPolicyConfirmedAt: value ? new Date().toISOString() : '',
              } : ad) }));
              invalidar();
            }}
            preview={ad => <PreviaDaPeca accountRef={draft.accountRef} ativo={imagens.find(item => item.referencia_opaca === ad.assetRef)} />} />
          {draft.conjuntos.map(conjunto => <IdentidadeDoAnunciante key={`${draft.accountRef}:${conjunto.key}`} accountRef={draft.accountRef}
            consultar={lerIdentidades}
            conjunto={conjunto} demo={params.get('modo') === 'demo'} disabled={ocupado !== null}
            onChange={ref => mudarConjunto(conjunto.key, { regulatoryIdentityRef: ref || undefined })} />)}
          <details className="border-t border-border pt-4 text-sm">
            <summary className="cursor-pointer py-2 font-medium">Detalhes técnicos, tracking e evidências do plano</summary>
            <div className="mt-4 space-y-4">
          <TrackingAutomatico destino={draft.destinationUrl} />
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

          {/* A forma do plano escolhe o contrato; ambos têm aprovação e criação pausada. */}
          {contrato === 'V2' && (
            <BlocoDeEvidencia titulo="Por que este plano usa o contrato V2" tom="info">
              {motivosDoV2.map((motivo) => (
                <LinhaDeFato key={motivo} rotulo="Recurso do V2" valor={motivo} fonte="a forma deste plano" />
              ))}
              <LinhaDeFato
                rotulo="Consequência"
                valor="Criação pausada após validação, aprovação do plano e liberação desta conta"
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
            </div>
          </details>

          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">Conferimos o plano e sua elegibilidade automaticamente. Nenhum objeto é criado antes da sua aprovação final.</p>
            {(ocupado === 'compilar' || ocupado === 'validar') && <p role="status" className="flex items-center gap-2 text-sm font-medium text-primary"><CircleDot className="h-4 w-4 motion-safe:animate-pulse" aria-hidden />{ocupado === 'compilar' ? 'Conferindo a montagem…' : 'Validando a elegibilidade na Meta…'}</p>}
            {validacao?.ok && !ocupado && <p role="status" className="flex items-center gap-2 text-sm font-medium"><CircleCheck className="h-4 w-4 text-success" aria-hidden />Conferência prévia concluída. Revise e confirme a criação pausada abaixo.</p>}
            {params.get('modo') === 'demo' && <p className="text-sm">A demonstração não consulta nem valida campanhas na Meta.</p>}
            {faltas.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm">{faltas.map(falta => <li key={falta}>{falta}</li>)}</ul>}
            {params.get('modo') !== 'demo' && (avisos.length > 0 || validacao?.ok === false) && (
            <AcaoDominante
              pode={podeCompilar && ocupado === null}
              enviando={ocupado === 'compilar' || ocupado === 'validar'}
              faltas={[]}
              onClick={() => void (compilacao ? validar() : compilar())}
            >
              Tentar conferência novamente
            </AcaoDominante>)}
            {!capacidades.validateOnly && <p className="text-sm text-warning">A validação remota precisa ser habilitada pelo administrador.</p>}
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

          {params.get('modo') === 'demo' && <p role="status" className="text-sm text-muted-foreground">Demonstração: a criação de campanhas reais está desativada nesta tela.</p>}

          {criacaoDisponivel && (
            <div className="space-y-4 rounded-lg border border-border/70 p-4">
              <h3 className="font-display text-lg font-semibold">Criar a campanha pausada</h3>
              <p className="max-w-[70ch] text-sm text-muted-foreground">Confirme a criação dos objetos reais na conta {conta?.nome || 'selecionada'}. Isso não ativa a veiculação.</p>
              <details className="text-sm"><summary className="cursor-pointer py-2 font-medium">Conferir conta, orçamento e prova da validação</summary>
              <BlocoDeEvidencia titulo="O que será criado agora, de verdade" tom="atencao">
                <LinhaDeFato rotulo="Conta" valor={conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : null} fonte="a Meta" ausencia="não escolhida" />
                {orcamentosDoPlano(draft).map(item => <LinhaDeFato key={item.rotulo} rotulo={`Orçamento ${draft.periodoDeOrcamento === 'DAILY' ? 'diário' : 'total'} · ${item.rotulo}`} valor={item.minor > 0 ? formatarBrl(item.minor) : null} fonte="você" ausencia="não informado" />)}
                <LinhaDeFato rotulo="Campanha" valor={draft.campaignName || null} fonte="você" ausencia="sem nome" />
                <LinhaDeFato rotulo="Conjuntos" valor={draft.conjuntos.map(c => c.nome).join(' · ') || null} fonte="você" ausencia="sem nome" />
                <LinhaDeFato rotulo="Criativos e anúncios" valor={`${totalDeAnuncios} criativo${totalDeAnuncios === 1 ? '' : 's'} · ${totalDeAnuncios} anúncio${totalDeAnuncios === 1 ? '' : 's'}${draft.creativeMode === 'flexible' ? ` · ${emitidas.length} imagens` : ''}`} fonte="a montagem atual" />
                <LinhaDeFato rotulo="Estado ao nascer" valor="Pausado em todos os níveis veiculáveis" fonte="a receita provada" />
                <LinhaDeFato rotulo="Identidade do plano" valor={compilacao?.plano.plano_sha256 ?? null} fonte="o backend" ausencia="plano ainda não compilado" />
                <LinhaDeFato rotulo="Validação remota" valor={validacao?.ok ? `Aceita · ${validacao.operacoes_validadas.join(', ')}` : null} fonte="a Meta" ausencia="ainda não validado" />
                <LinhaDeFato rotulo="Prova durável da validação" valor={validacao?.prova_duravel?.registrada ? 'Gravada no servidor' : null} fonte="o backend" ausencia="não gravada" />
                <LinhaDeFato rotulo="Ainda sem validação remota" valor={validacao?.operacoes_dependentes_pendentes.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              </BlocoDeEvidencia>
              </details>

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
                    !motivoDeMidiaPendente && Boolean(validacao?.ok && validacao.prova_duravel?.registrada)
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
                    pode={!motivoDeMidiaPendente && Boolean(aprovacao) && !jaDespachou && ocupado === null}
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
              {params.get('operacao_anterior') && <Link className="inline-flex min-h-11 items-center text-sm text-primary underline" target="_blank" rel="noopener noreferrer"
                to={`/trafego/meta/nova?rascunho=${encodeURIComponent(draftRef)}&etapa=revisao&operacao=${encodeURIComponent(params.get('operacao_anterior')!)}`}>
                Consultar recibo da tentativa anterior (nova aba)
              </Link>}

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
                  {aprovacao.budget_manifest ? aprovacao.budget_manifest.entries.map(entry => <LinhaDeFato key={entry.step} rotulo={`Orçamento aprovado · ${entry.step}`} valor={`${formatarBrl(entry.amount_minor)} · ${entry.period === 'DAILY' ? 'por dia' : 'total do período'}`} fonte="plano congelado no backend" />) : <LinhaDeFato rotulo="Orçamento diário aprovado" valor={aprovacao.orcamento_diario_minor === null ? null : formatarBrl(aprovacao.orcamento_diario_minor)} fonte="o backend" ausencia="não informado" />}
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
              <strong className="text-foreground">Receita atribuída ao conjunto; a campanha soma os conjuntos.</strong>{' '}
              As UTMs serão incluídas automaticamente e tudo nasce em PAUSED.
              Ativar continua sendo outro ato, fora desta tela.
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
      <div className="meta-journey">
        <header>
          <div className="meta-journey-top">
            <Link to="/trafego?rede=meta" className="inline-flex min-h-11 items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" aria-hidden /> Tráfego Meta
            </Link>
            <div className="flex items-center gap-3">
              <span className="hidden text-sm text-muted-foreground sm:inline">Ao criar, tudo começa pausado</span>
              <MetaConfiguracaoLocal />
              <RascunhosMeta currentRef={draftRef} demo={params.get('modo') === 'demo'} beforeResume={async () => {
                if (ocupado !== null || rascunhoPersistido.loading) return false;
                if (rascunhoPersistido.blocked && rascunhoPersistido.version === 0) return true;
                return rascunhoPersistido.saved || await rascunhoPersistido.saveNow();
              }} />
            </div>
          </div>
          <div className="mt-6 flex items-center justify-between gap-4">
            <div>
              <p className="kicker flex items-center gap-2"><Megaphone className="h-4 w-4 text-primary" aria-hidden />Meta Ads · Arbitragem</p>
              <h1 className="mt-2 font-display text-[2rem] font-bold tracking-tight">Nova campanha Meta</h1>
              <div className="aurora-rule mt-3 w-16" />
            </div>
            <span className="shrink-0 text-sm tabular-nums text-muted-foreground">{indice + 1} / {perguntas.length}</span>
          </div>
          <div className="meta-journey-progress" role="progressbar" aria-label="Progresso da configuração"
            aria-valuenow={indice + 1} aria-valuemin={0} aria-valuemax={perguntas.length}>
            <span style={{ transform: `scaleX(${(indice + 1) / perguntas.length})` }} />
          </div>
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer py-2 text-muted-foreground">Ver etapas e editar respostas</summary>
            <nav aria-label="Etapas da criação Meta" className="meta-journey-index">
              {perguntasMeta(true).map(p => <button type="button" key={p.id} aria-current={p.id === pergunta.id ? 'step' : undefined}
                onClick={() => irParaPergunta(p)} className={cn('focus-visible:ring-2 focus-visible:ring-ring',
                  p.id === pergunta.id ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground hover:bg-muted')}>
                {p.nome}
              </button>)}
            </nav>
          </details>
        </header>
        <section aria-label="Salvamento do rascunho" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 text-sm">
          <p role="status" aria-live="polite" className="text-muted-foreground">
            {params.get('modo') === 'demo' ? 'Demonstração · alterações ficam apenas nesta tela'
              : rascunhoPersistido.loading ? 'Recuperando sua montagem…'
              : rascunhoPersistido.saving ? 'Salvando conjuntos e anúncios…'
              : rascunhoPersistido.conflict ? 'Há uma versão mais nova salva em outra aba'
              : rascunhoPersistido.saved ? `Montagem salva no servidor · versão ${rascunhoPersistido.version}`
              : 'Alterações ainda não salvas no servidor'}
          </p>
          {rascunhoPersistido.error && <div className="w-full" role="alert">
            <p className="text-destructive">{rascunhoPersistido.error}</p>
            <Button type="button" variant="outline" className="mt-2" onClick={() => {
              if (window.confirm('Recuperar a versão salva? Alterações locais ainda não salvas serão descartadas.')) void rascunhoPersistido.reload();
            }}>Recuperar versão salva</Button>
            {!rascunhoPersistido.blocked && <Button type="button" variant="outline" className="mt-2 ml-2" onClick={() => { void rascunhoPersistido.saveNow(); }}>Tentar salvar novamente</Button>}
            {rascunhoPersistido.blocked && rascunhoPersistido.version === 0 && <a className="ml-3 inline-flex min-h-11 items-center underline" href="/trafego/meta/nova">Iniciar uma nova campanha</a>}
          </div>}
        </section>
        <main aria-labelledby="meta-question-title" className={cn('meta-journey-question', etapa === 'criativo' && 'meta-journey-question--wide')}>
          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-primary">{pergunta.nome} <span className="font-normal text-muted-foreground">· {indice + 1} de {perguntas.length}</span></p>
          <h2 id="meta-question-title" ref={tituloDaPergunta} tabIndex={-1} className="font-display text-2xl font-semibold leading-tight tracking-tight outline-none sm:text-[2rem]">
            {pergunta.titulo}
          </h2>
          <p className="mt-3 max-w-[65ch] text-base text-muted-foreground">{pergunta.ajuda}</p>
          {feedbackDoPlano && <div ref={feedbackRef} role="status" aria-live="polite" tabIndex={-1}
            className="mt-5 rounded-lg border border-primary/30 bg-card p-4 text-sm text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            {feedbackDoPlano}
          </div>}
          <div key={pergunta.id} className="meta-journey-body" onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && etapa !== 'revisao') { e.preventDefault(); continuar(); }
          }}>
            <div role="alert" aria-label="Erros da operação" aria-live="assertive"><PainelDeBloqueio bloqueios={avisos} titulo="Não foi possível concluir" /></div>
            <fieldset disabled={rascunhoPersistido.blocked} className="min-w-0 border-0 p-0">
              <legend className="sr-only">Configuração da campanha</legend>
              {['criativos', 'revisao'].includes(pergunta.id) && <NomenclaturaAutomatica
                draft={draft} draftRef={draftRef} save={rascunhoPersistido.saveNow} sizes={tamanhosParaNomes}
                conversionNames={conversoesParaNomes}
                demo={params.get('modo') === 'demo'} onChange={next => { setDraft(next); invalidar(); }} />}
              {conteudo}
            </fieldset>
          </div>
          <div className="meta-journey-footer">
            <Button type="button" variant="ghost" disabled={indice === 0}
              onClick={() => irParaPergunta(perguntas[indice - 1])}><ArrowLeft className="h-4 w-4" aria-hidden />Voltar</Button>
            {indice < perguntas.length - 1 && <div className="flex items-center gap-4">
              <span className="hidden text-xs text-muted-foreground sm:inline">⌘ / Ctrl + Enter</span>
              <Button type="button" disabled={rascunhoPersistido.blocked} className="min-h-12 px-7" onClick={continuar}>Continuar<ArrowRight className="h-4 w-4" aria-hidden /></Button>
            </div>}
          </div>
          {erroDaPergunta && <p role="alert" className="mt-3 text-sm text-destructive">{erroDaPergunta}</p>}
          {etapa === 'revisao' && <details className="mt-8 text-sm">
            <summary className="cursor-pointer py-3 font-medium">Respostas e pendências do plano</summary>
            <Pedido linhas={linhasDoPedido} faltas={faltas} proximoAto={proximoAto} lidoEm={null} />
          </details>}
        </main>
      </div>
    </Layout>
  );
};

export default MetaCriacaoPage;
