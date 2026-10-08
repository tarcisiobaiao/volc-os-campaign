/**
 * O que o operador digita em cada canal — o formulário, ANTES de virar contrato.
 *
 * ## Por que um tipo de formulário separado do tipo do contrato
 *
 * O contrato é estrito: número é número, ausência é ausência, e `"3"` não vira
 * `3` (GADS-CRIACAO-CANAIS-v1 §2, regra 3). Um campo de tela, ao contrário, é
 * texto enquanto o operador digita — `"4,5"`, `""`, `"4,"`. Guardar o formulário
 * já no formato do contrato obrigaria a decidir na tecla o que só se decide na
 * montagem, e era assim que um campo vazio virava `0` no pedido.
 *
 * Então: o formulário guarda texto e escolhas (`boolean | null` quando a
 * decisão é obrigatória e ninguém a tomou), e `montagem.ts` converte — num
 * lugar só, testado.
 *
 * ⚠️ Tudo aqui é serializável e vai para o `sessionStorage` da aba pelo
 * `useRascunho`. Nenhum id de conta, nenhum segredo e nenhum byte de imagem.
 */
import {
  ROTULOS_PADRAO_DISPLAY,
} from '@/types/trafegoCanais';
import type {
  AutomacaoPMax, CategoriaDeConversao, DiaDaSemana, Dispositivo, EstrategiaDemandGen,
  EstrategiaDisplay, ExpansaoLookalike, Fixacao, FormatoDemandGen, FormatoRda,
  LocalDeImpressao, NivelDeFrequencia, OrigemDeConversao, PlataformaDeVideoCrawl,
  PresencaGeoDisplay, RotuloDeConteudo, TipoGeoNegativo, TipoGeoPositivo, UnidadeDeFrequencia,
} from '@/types/trafegoCanais';

/** Uma faixa de agenda como a tela a edita (HH:MM). */
export interface LinhaDeFaixa {
  dia: DiaDaSemana;
  inicio: string;
  fim: string;
  /** Só Search: ajuste de lance (1,2 = +20%). Vazio = sem ajuste. */
  ajuste: string;
}

export interface LinhaDeDispositivo { dispositivo: Dispositivo; fator: string }

export interface LinhaDeCategoria {
  categoria: CategoriaDeConversao;
  origem: OrigemDeConversao;
  /** Search chama de `lance`; PMax de `biddable`. É a mesma decisão. */
  lance: boolean;
}

// ── Search ────────────────────────────────────────────────────────────────

export interface FormLanceSearch {
  /** tCPA (MAXIMIZE_CONVERSIONS), opcional. */
  tcpa: string;
  /** tROAS em PORCENTAGEM (400 = 4,0), opcional. */
  troasPct: string;
  /** Teto de CPC: opcional em TARGET_SPEND, obrigatório em TARGET_IMPRESSION_SHARE. */
  tetoCpc: string;
  local: LocalDeImpressao | '';
  /** Parcela de impressões em PORCENTAGEM (60 = 0,6). */
  fracaoPct: string;
}

export type ModoDaMetaSearch = 'conta' | 'personalizada' | 'acoes';

export interface FormSearch {
  lance: FormLanceSearch;
  /** Rede: decisão OBRIGATÓRIA com configuração. `null` = ninguém decidiu. */
  parceiros: boolean | null;
  expansaoDisplay: boolean | null;
  // AI Max — `false` = sem objeto (o comportamento de antes).
  aiMax: boolean;
  aiCorrespondencia: boolean | null;
  aiPersonalizacao: boolean | null;
  aiExpansaoUrl: boolean | null;
  aiGruposSemCorrespondencia: string;
  aiExclusoesDeUrl: string;
  aiListasIncluidas: string;
  aiListasExcluidas: string;
  aiTermosExcluidos: string;
  aiRestricoes: string;
  // RSA
  path1: string;
  path2: string;
  fixacoes: Fixacao[];
  // agenda, dispositivo, geo, datas
  programacao: LinhaDeFaixa[];
  dispositivos: LinhaDeDispositivo[];
  geo: boolean;
  geoPositivo: TipoGeoPositivo;
  geoNegativo: TipoGeoNegativo;
  geoLocais: string;
  geoLocaisExcluidos: string;
  geoIdiomas: string;
  inicio: string;
  fim: string;
  // meta de conversão
  metaModo: ModoDaMetaSearch;
  metaPersonalizada: string;
  metaAcoes: string;
  metaCategorias: LinhaDeCategoria[];
}

export const FORM_SEARCH_VAZIO: FormSearch = {
  lance: { tcpa: '', troasPct: '', tetoCpc: '', local: '', fracaoPct: '' },
  parceiros: null,
  expansaoDisplay: null,
  aiMax: false,
  aiCorrespondencia: null,
  aiPersonalizacao: null,
  aiExpansaoUrl: null,
  aiGruposSemCorrespondencia: '',
  aiExclusoesDeUrl: '',
  aiListasIncluidas: '',
  aiListasExcluidas: '',
  aiTermosExcluidos: '',
  aiRestricoes: '',
  path1: '',
  path2: '',
  fixacoes: [],
  programacao: [],
  dispositivos: [],
  geo: false,
  geoPositivo: 'PRESENCE',
  geoNegativo: 'PRESENCE',
  geoLocais: '',
  geoLocaisExcluidos: '',
  geoIdiomas: '',
  inicio: '',
  fim: '',
  metaModo: 'conta',
  metaPersonalizada: '',
  metaAcoes: '',
  metaCategorias: [],
};

// ── Display ───────────────────────────────────────────────────────────────

export interface FormDisplay {
  estrategia: EstrategiaDisplay;
  tcpa: string;
  troasPct: string;
  tetoCpc: string;
  cpm: string;
  /** Só MANUAL_CPC: é o lance do grupo e vai em `cpc_inicial`. */
  cpcManual: string;
  segListasDeUsuarios: string;
  segPublicosPersonalizados: string;
  segPublicosCombinados: string;
  segInteresses: string;
  segTopicos: string;
  segPlacements: string;
  segPalavrasChave: string;
  segObservacao: boolean;
  segOtimizada: boolean;
  excPlacements: string;
  excApps: string;
  excCategoriasDeApp: string;
  excTodosOsApps: boolean;
  excRotulos: RotuloDeConteudo[];
  excTopicos: string;
  excListasExistentes: string;
  listaNovaNome: string;
  listaNovaPlacements: string;
  listaNovaApps: string;
  listaNovaCategorias: string;
  frequencia: { impressoes: string; unidade: UnidadeDeFrequencia; nivel: NivelDeFrequencia }[];
  agenda: LinhaDeFaixa[];
  dispositivosExcluidos: Dispositivo[];
  presenca: PresencaGeoDisplay;
  rdaCta: string;
  rdaCorPrincipal: string;
  rdaCorDestaque: string;
  rdaCoresFlexiveis: boolean;
  rdaFormato: FormatoRda;
  rdaMelhorias: boolean;
  rdaVideoAutomatico: boolean;
}

/** ⚠️ Os defaults de exclusão JÁ MARCADOS: objeto presente é a doutrina de
 *  nascimento (todos os apps + os seis rótulos). Desmarcar é decisão. */
export const FORM_DISPLAY_VAZIO: FormDisplay = {
  estrategia: 'MAXIMIZE_CONVERSIONS',
  tcpa: '',
  troasPct: '',
  tetoCpc: '',
  cpm: '',
  cpcManual: '',
  segListasDeUsuarios: '',
  segPublicosPersonalizados: '',
  segPublicosCombinados: '',
  segInteresses: '',
  segTopicos: '',
  segPlacements: '',
  segPalavrasChave: '',
  segObservacao: false,
  segOtimizada: false,
  excPlacements: '',
  excApps: '',
  excCategoriasDeApp: '',
  excTodosOsApps: true,
  excRotulos: [...ROTULOS_PADRAO_DISPLAY],
  excTopicos: '',
  excListasExistentes: '',
  listaNovaNome: '',
  listaNovaPlacements: '',
  listaNovaApps: '',
  listaNovaCategorias: '',
  frequencia: [],
  agenda: [],
  dispositivosExcluidos: [],
  presenca: 'PRESENCE',
  rdaCta: '',
  rdaCorPrincipal: '',
  rdaCorDestaque: '',
  rdaCoresFlexiveis: true,
  rdaFormato: 'ALL_FORMATS',
  rdaMelhorias: false,
  rdaVideoAutomatico: false,
};

// ── Demand Gen ────────────────────────────────────────────────────────────

export interface FormLookalike {
  nome: string;
  sementes: string;
  expansao: ExpansaoLookalike;
  paises: string;
}

export interface FormDemandGen {
  formato: FormatoDemandGen;
  estrategia: EstrategiaDemandGen;
  tcpa: string;
  troasPct: string;
  tcpc: string;
  /** CTA do multi-asset. No vídeo o CTA é `videoCta`. */
  cta: string;
  videoIds: string;
  videoCta: string;
  breadcrumb1: string;
  breadcrumb2: string;
  /** Títulos longos: só o vídeo responsivo os aceita (1..5). */
  titulosLongos: string;
  publico: boolean;
  publicoNome: string;
  userLists: string;
  exclusoesUserList: string;
  lookalikes: FormLookalike[];
  idades: string[];
  generos: string[];
  rendas: string[];
  parentais: string[];
  inclIdade: boolean;
  inclGenero: boolean;
  inclRenda: boolean;
  inclParental: boolean;
  /** `null` = não emitido (o default do contrato). */
  segOtimizada: boolean | null;
  /** tipo → ligada. Só os tipos do formato viajam. */
  automacoes: Record<string, boolean>;
  agenda: LinhaDeFaixa[];
}

export const FORM_DEMAND_GEN_VAZIO: FormDemandGen = {
  formato: 'MULTI_ASSET',
  estrategia: 'MAXIMIZE_CONVERSIONS',
  tcpa: '',
  troasPct: '',
  tcpc: '',
  cta: '',
  videoIds: '',
  videoCta: '',
  breadcrumb1: '',
  breadcrumb2: '',
  titulosLongos: '',
  publico: false,
  publicoNome: '',
  userLists: '',
  exclusoesUserList: '',
  lookalikes: [],
  idades: [],
  generos: [],
  rendas: [],
  parentais: [],
  inclIdade: true,
  inclGenero: true,
  inclRenda: true,
  inclParental: true,
  segOtimizada: null,
  automacoes: {},
  agenda: [],
};

// ── Performance Max ───────────────────────────────────────────────────────

export interface FormOpcoesDeUrl {
  /** Uma linha por par, `chave=valor`. */
  sufixo: string;
  tracking: string;
  parametros: string;
}

export const OPCOES_DE_URL_VAZIAS: FormOpcoesDeUrl = { sufixo: '', tracking: '', parametros: '' };

/** Um asset group ADICIONAL. As imagens (bytes) vivem fora do rascunho,
 *  na página, chaveadas pelo `id`. */
export interface FormGrupoPMax {
  id: string;
  nome: string;
  url: string;
  titulos: string;
  titulosLongos: string;
  descricoes: string;
  /** `[]` é "sem dica" e é escolha; sem confirmar, o grupo não está pronto. */
  sinaisConfirmados: boolean;
  audiencias: string;
  temas: string;
  videos: string;
  path1: string;
  path2: string;
  url_opcoes: FormOpcoesDeUrl;
}

export interface FormPMax {
  path1: string;
  path2: string;
  url_opcoes: FormOpcoesDeUrl;
  /** IDs públicos do YouTube (11 caracteres), um por linha. */
  videos: string;
  grupos: FormGrupoPMax[];
  automacoes: AutomacaoPMax[];
  videoCrawl: { url: string; plataforma: PlataformaDeVideoCrawl; habilitada: boolean }[];
  direitosDeclarados: boolean;
  exclusoesDeUrl: { nome: string; argumento: string; operando: 'URL' | 'PAGE_TITLE' | 'PAGE_CONTENT'; operador: 'CONTAINS' | 'EQUALS' }[];
  termosExcluidos: string;
  restricoes: string;
  corPrincipal: string;
  corDestaque: string;
  fonte: string;
  negativasTipadas: { texto: string; match: 'BROAD' | 'PHRASE' | 'EXACT' }[];
  listasDeNegativas: string;
  marcasExcluidas: { entity_id: string; nome: string }[];
  listasDeMarcas: string;
  metas: LinhaDeCategoria[];
  clienteNovo: boolean;
  cnGoal: string;
  cnModo: 'TARGET_ALL' | 'TARGET_SPECIFIC';
  cnValor: string;
  cnMultiplicador: string;
}

export const FORM_PMAX_VAZIO: FormPMax = {
  path1: '',
  path2: '',
  url_opcoes: OPCOES_DE_URL_VAZIAS,
  videos: '',
  grupos: [],
  automacoes: [],
  videoCrawl: [],
  direitosDeclarados: false,
  exclusoesDeUrl: [],
  termosExcluidos: '',
  restricoes: '',
  corPrincipal: '',
  corDestaque: '',
  fonte: '',
  negativasTipadas: [],
  listasDeNegativas: '',
  marcasExcluidas: [],
  listasDeMarcas: '',
  metas: [],
  clienteNovo: false,
  cnGoal: '',
  cnModo: 'TARGET_ALL',
  cnValor: '',
  cnMultiplicador: '',
};

let sequencia = 0;
/** Id local de um grupo adicional — só para chavear as imagens na página. */
export function novoIdDeGrupo(): string {
  sequencia += 1;
  return `g${Date.now().toString(36)}${sequencia}`;
}

export function novoGrupoPMax(): FormGrupoPMax {
  return {
    id: novoIdDeGrupo(), nome: '', url: '', titulos: '', titulosLongos: '', descricoes: '',
    sinaisConfirmados: false, audiencias: '', temas: '', videos: '', path1: '', path2: '',
    url_opcoes: { ...OPCOES_DE_URL_VAZIAS },
  };
}

/** Mescla um formulário gravado por uma versão anterior sobre o vazio — um
 *  campo novo não pode derrubar a tela de quem tinha rascunho aberto. */
export function mesclarFormulario<T extends object>(vazio: T, gravado: unknown): T {
  if (!gravado || typeof gravado !== 'object' || Array.isArray(gravado)) return vazio;
  const saida = { ...vazio } as Record<string, unknown>;
  for (const [k, v] of Object.entries(gravado as Record<string, unknown>)) {
    if (!(k in saida)) continue;
    const base = saida[k];
    // Um mapa aberto (`automacoes: {}`) não tem chaves para conferir: vem inteiro.
    const mapaAberto = base && typeof base === 'object' && !Array.isArray(base)
      && Object.keys(base).length === 0;
    if (mapaAberto && v && typeof v === 'object' && !Array.isArray(v)) {
      saida[k] = v;
    } else if (base && typeof base === 'object' && !Array.isArray(base) && v && typeof v === 'object' && !Array.isArray(v)) {
      saida[k] = mesclarFormulario(base as object, v);
    } else if (v !== undefined) {
      saida[k] = v;
    }
  }
  return saida as T;
}

/** Re-exportado para quem monta formulário sem importar dois módulos. */
export type { FormatoDemandGen, EstrategiaDisplay, EstrategiaDemandGen };
