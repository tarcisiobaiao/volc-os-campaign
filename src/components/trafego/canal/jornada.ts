/**
 * Gramática de jornada por canal — contrato de apresentação, não JSX.
 *
 * ## Por que este módulo existe
 *
 * As sete etapas genéricas (objetivo, estratégia, alcance, criativos, …)
 * mentem sobre o que cada canal exige. Search não pede imagem; Performance Max
 * não tem grupo de anúncios de Search; a Google Ads API não cria campanha
 * Video. Quem decide o que a tela mostra é ESTE registro, cruzado com o
 * manifesto do backend. O JSX só renderiza o que daqui sai.
 *
 * ## Interseção que libera ação
 *
 *     capacidade da API
 *     AND capacidade do backend VOLC
 *     AND permissão do usuário
 *     AND estado da trava
 *
 * Só o resultado dessa interseção pode afirmar que a escrita vai acontecer.
 * Abrir o cockpit real (montar o pedido pela tela) é outra porta: além de API,
 * builder e prova, exige que esta superfície possua o formulário do canal.
 * Demand Gen acrescenta uma capacidade de servidor própria e expõe somente a
 * prova HTTP nesta onda; criação real continua sendo uma interseção mais estreita.
 *
 * Módulo puro. Sem React, sem HTTP, sem Google Ads.
 *
 * Fontes oficiais consultadas em 2026-08-27:
 * - https://developers.google.com/google-ads/api/docs/video/overview
 *   fato: a API só consulta e reporta campanhas Video; não cria nem atualiza.
 * - https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads
 *   fato: RSA exige ≥3 headlines, ≥2 descriptions e ≥1 URL final.
 * - https://developers.google.com/google-ads/api/docs/performance-max/asset-groups
 *   fato: PMax se organiza em asset groups; criação atômica dos vínculos.
 */
import { CANAIS, type Canal, type CapacidadesDoOperador, type EstadoDaTrava, type ManifestoDeCanal } from '@/types/trafego';

export const CONSULTADO_EM = '2026-08-27';

export interface FonteOficial {
  url: string;
  fato: string;
  consultadoEm: typeof CONSULTADO_EM;
}

export const FONTES_OFICIAIS = {
  video: {
    url: 'https://developers.google.com/google-ads/api/docs/video/overview',
    fato:
      'A Google Ads API somente consulta e reporta campanhas Video existentes; não cria nem atualiza.',
    consultadoEm: CONSULTADO_EM,
  },
  rsa: {
    url: 'https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads',
    fato: 'O anúncio responsivo de pesquisa exige pelo menos três headlines, duas descriptions e uma URL final.',
    consultadoEm: CONSULTADO_EM,
  },
  display: {
    url: 'https://developers.google.com/google-ads/api/docs/responsive-display-ads/create-responsive-display-ads',
    fato: 'O Responsive Display Ad tem contrato visual próprio (imagens, headlines, long headline, logos, cores).',
    consultadoEm: CONSULTADO_EM,
  },
  demandGen: {
    url: 'https://developers.google.com/google-ads/api/docs/demand-gen/create-campaign',
    fato: 'Demand Gen não é Display. A documentação recomenda um único Mutate atômico para as entidades relacionadas.',
    consultadoEm: CONSULTADO_EM,
  },
  pmax: {
    url: 'https://developers.google.com/google-ads/api/docs/performance-max/asset-groups',
    fato: 'Performance Max se organiza em asset groups, não em grupos de anúncios de Search.',
    consultadoEm: CONSULTADO_EM,
  },
  shopping: {
    url: 'https://developers.google.com/google-ads/api/docs/shopping-ads/create-campaign',
    fato: 'Shopping depende de Merchant Center e catálogo, não de um editor de criativo genérico.',
    consultadoEm: CONSULTADO_EM,
  },
} as const satisfies Record<string, FonteOficial>;

/** O que este canal É para o operador, nesta versão do Hub. */
export type PapelDoCanal =
  | 'operacional'
  | 'parcial'
  | 'planejado'
  | 'pre_requisito'
  | 'somente_leitura';

export const PALAVRA_DO_PAPEL: Record<PapelDoCanal, string> = {
  operacional: 'operacional',
  parcial: 'parcial',
  planejado: 'planejado',
  pre_requisito: 'depende de Merchant Center',
  somente_leitura: 'somente leitura pela API',
};

export type TipoDeCta = 'cockpit' | 'desbloqueio' | 'observar' | 'nenhum';

export interface EtapaDaJornada {
  chave: string;
  titulo: string;
  pergunta: string;
  obrigatoria: boolean;
  /** Fora da leitura dominante — requisitos avançados. */
  avancada?: boolean;
  detalhes?: readonly string[];
}

export interface CtaDoCanal {
  tipo: TipoDeCta;
  rotulo: string;
  /** Rota real já existente. Nunca um endpoint inventado. */
  destino?: '/trafego?aba=preparar' | '/trafego?aba=campanhas&canal=VIDEO';
  porque?: string;
}

export type EixoDaIntersecao = 'api' | 'backend' | 'permissao' | 'trava';

/**
 * Os quatro eixos, lado a lado. `null` em permissão ou trava é ignorância,
 * não recusa — colapsar os dois faz um ADMIN cuja leitura falhou ler que
 * lhe falta papel.
 */
export interface IntersecaoDeAcao {
  api: boolean;
  /** O backend possui builder + porta validate_only. */
  backend: boolean;
  /** Permissão para mutação real, preservada separadamente da prova. */
  permissao: boolean | null;
  trava: boolean | null;
  /** Capacidade de prova aplicável ao canal. Demand Gen não herda a geral. */
  prova: boolean | null;
  provaLiberada: boolean;
  /** Os quatro eixos verdadeiros. Só então a tela afirma que a escrita sai. */
  escritaLiberada: boolean;
  /** Existe um formulário real nesta superfície, além do builder no backend. */
  cockpitLiberado: boolean;
  porqueNao: string | null;
  eixo: EixoDaIntersecao | null;
}

export interface AlternativaDeCanal {
  canal: Canal;
  rotulo: string;
  porque: string;
}

export interface ApresentacaoDoCanal {
  canal: Canal;
  rotulo: string;
  papel: PapelDoCanal;
  frase: string;
  etapas: readonly EtapaDaJornada[];
  /**
   * Canal planejado/recusado não ganha etapa clicável. A gramática continua
   * visível atrás de disclosure, para o operador ver o que o canal exigiria.
   */
  etapasComoFormulario: boolean;
  cta: CtaDoCanal;
  alternativas: readonly AlternativaDeCanal[];
  provas: readonly string[];
  limites: readonly string[];
  recusa: string | null;
  intersecao: IntersecaoDeAcao;
  fontes: readonly FonteOficial[];
}

export interface ContextoDaJornada {
  capacidades: CapacidadesDoOperador | null;
  trava: EstadoDaTrava | null;
}

interface GramaticaDoCanal {
  rotulo: string;
  papelBase: PapelDoCanal;
  frase: string;
  /** A API oficial permite criar/atualizar este advertising_channel_type? */
  apiCria: boolean;
  etapas: readonly EtapaDaJornada[];
  fontes: readonly FonteOficial[];
  alternativas?: readonly AlternativaDeCanal[];
  /**
   * Recusa que a API impõe mesmo que o manifesto um dia diga sabe_criar.
   * Video é o caso: existência de VideoAdInfo ≠ autorização para criar.
   */
  recusaDaApi?: string;
}

const ETAPAS_SEARCH: readonly EtapaDaJornada[] = [
  {
    chave: 'objetivo',
    titulo: 'Objetivo e conta',
    pergunta: 'que resultado se espera, em que conta de anúncio?',
    obrigatoria: true,
  },
  {
    chave: 'destino',
    titulo: 'Destino e medição',
    pergunta: 'para que página vai o clique, e como a conversão é medida?',
    obrigatoria: true,
    detalhes: ['URL final', 'conversão observada na conta'],
  },
  {
    chave: 'alcance-rede',
    titulo: 'Geografia, idioma e redes',
    pergunta: 'onde o anúncio pode aparecer, em que língua, em quais redes?',
    obrigatoria: true,
  },
  {
    chave: 'compra',
    titulo: 'Orçamento e lance',
    pergunta: 'quanto por dia, e como a campanha nasce comprando?',
    obrigatoria: true,
    detalhes: ['verba diária', 'estratégia de lance'],
  },
  {
    chave: 'grupos',
    titulo: 'Grupos de anúncios',
    pergunta: 'quantos grupos, e o que cada um cobre?',
    obrigatoria: true,
  },
  {
    chave: 'keywords',
    titulo: 'Keywords, correspondências e negativas',
    pergunta: 'que buscas acionam o anúncio — e quais não?',
    obrigatoria: true,
  },
  {
    chave: 'anuncio',
    titulo: 'Anúncio e recursos',
    pergunta:
      'o anúncio responsivo de pesquisa: headlines, descriptions e URL final. Imagem e vídeo não são requisito deste canal.',
    obrigatoria: true,
    detalhes: [
      'pelo menos 3 headlines',
      'pelo menos 2 descriptions',
      'URL final',
      'path1 e path2 quando couberem',
      'pinning somente quando deliberado',
    ],
  },
  {
    chave: 'recursos',
    titulo: 'Recursos opcionais',
    pergunta: 'sitelinks, callouts e snippets — só o que este construtor monta.',
    obrigatoria: false,
    avancada: true,
    detalhes: [
      'sitelinks',
      'callouts',
      'structured snippets',
      'chamadas, formulários ou imagens somente se elegíveis e suportados',
    ],
  },
  {
    chave: 'conferencia',
    titulo: 'Conferência',
    pergunta: 'duplicidade, política, rastreamento e contrato — o que impede de subir?',
    obrigatoria: true,
  },
  {
    chave: 'validacao',
    titulo: 'Validação',
    pergunta: 'o Google confere o pedido inteiro e devolve o veredito, sem criar nada',
    obrigatoria: true,
  },
  {
    chave: 'criacao',
    titulo: 'Criação pausada',
    pergunta: 'a campanha nasce pausada. Ligá-la é outra decisão, depois.',
    obrigatoria: true,
  },
  {
    chave: 'ativacao',
    titulo: 'Ativação',
    pergunta: 'ligar a campanha é uma decisão separada da criação',
    obrigatoria: true,
  },
];

const ETAPAS_DISPLAY: readonly EtapaDaJornada[] = [
  {
    chave: 'objetivo',
    titulo: 'Objetivo e conta',
    pergunta: 'que resultado se espera, em que conta?',
    obrigatoria: true,
  },
  {
    chave: 'compra',
    titulo: 'Orçamento e lance',
    pergunta: 'quanto por dia, e com qual estratégia este canal aceita?',
    obrigatoria: true,
  },
  {
    chave: 'alcance',
    titulo: 'Público, posicionamentos e exclusões',
    pergunta: 'quem vê, onde aparece, e o que fica de fora?',
    obrigatoria: true,
  },
  {
    chave: 'anuncio',
    titulo: 'Anúncio responsivo de display',
    pergunta: 'o contrato visual do Responsive Display Ad — não o do Search e não o de Demand Gen.',
    obrigatoria: true,
    detalhes: [
      'imagens de marketing',
      'imagens quadradas',
      'headlines',
      'long headline',
      'descriptions',
      'business name',
      'URL final',
      'logos quando aplicáveis',
      'cores da marca e flexibilidade de cor quando suportadas',
      'formato nativo, não nativo ou todos quando permitido',
    ],
  },
  {
    chave: 'aprimoramentos',
    titulo: 'Vídeo gerado e aprimoramentos',
    pergunta: 'controles de vídeo gerado e asset enhancements, quando o manifesto declarar suporte.',
    obrigatoria: false,
    avancada: true,
  },
  {
    chave: 'conferencia',
    titulo: 'Conferência, validação e criação pausada',
    pergunta: 'as provas obrigatórias, o veredito do Google, e a campanha nascendo pausada',
    obrigatoria: true,
  },
];

const ETAPAS_DEMAND_GEN: readonly EtapaDaJornada[] = [
  {
    chave: 'campanha',
    titulo: 'Campanha pausada e bidding',
    pergunta:
      'orçamento diário positivo e Maximize Conversions sem meta numérica. A moeda não está no brief, então o mínimo oficial fica para o validate-only julgar.',
    obrigatoria: true,
  },
  {
    chave: 'grupo',
    titulo: 'Ad group pausado e targeting imutável',
    pergunta:
      'upgraded_targeting precisa ser True ou False antes da montagem; ele decide se geografia e idioma vivem no grupo ou na campanha.',
    obrigatoria: true,
  },
  {
    chave: 'audiencia',
    titulo: 'Audiência',
    pergunta: 'Audience resource names positivos já existentes na mesma conta; vazio confirmado é permitido.',
    obrigatoria: true,
  },
  {
    chave: 'intencao',
    titulo: 'Intenção',
    pergunta:
      'não é audiência por outro nome. A lista viaja separada e, nesta onda, qualquer item falha fechado até haver operação oficial confirmada.',
    obrigatoria: true,
  },
  {
    chave: 'exclusoes',
    titulo: 'Exclusões de audiência',
    pergunta:
      'não compartilha campo com audiência positiva nem intenção. A lista viaja separada e itens ainda não são suportados nesta onda.',
    obrigatoria: true,
  },
  {
    chave: 'canais',
    titulo: 'Controles de canal',
    pergunta: 'escolha explicitamente um ramo do oneof; o default remoto não decide pelo operador.',
    obrigatoria: true,
    detalhes: [
      'ALL_CHANNELS — todas as superfícies',
      'ALL_OWNED_AND_OPERATED_CHANNELS — YouTube, Discover, Gmail e Maps; sem Display de terceiros',
      'SELECTED_CHANNELS — ao menos uma flag verdadeira entre YouTube In-stream, In-feed, Shorts, Discover, Gmail, Display e Maps',
    ],
  },
  {
    chave: 'tipo',
    titulo: 'Anúncio multi-asset pausado',
    pergunta:
      'esta onda escolhe um único tipo confirmado: DemandGenMultiAssetAdInfo. Carrossel, vídeo responsivo e produto falham fechado.',
    obrigatoria: true,
    detalhes: [
      '1–5 headlines',
      '1–5 descriptions',
      'business name obrigatório',
      'ao menos uma imagem horizontal ou quadrada',
      '1–5 logos quadrados',
      'até 20 imagens de marketing somadas entre horizontal, quadrada, 4:5 e 9:16',
    ],
  },
  {
    chave: 'assets',
    titulo: 'Assets aprovados pelo Estúdio',
    pergunta:
      'bytes, geometria e procedência passam pela ponte criativa canônica; o frontend não recalcula elegibilidade.',
    obrigatoria: true,
  },
  {
    chave: 'copy',
    titulo: 'Copy e destino',
    pergunta: 'textos e URL final deste anúncio',
    obrigatoria: true,
  },
  {
    chave: 'atomico',
    titulo: 'Montagem atômica e prova',
    pergunta:
      'budget → campanha PAUSED → ad group PAUSED → critérios → assets → anúncio PAUSED entram num único payload. A porta executa somente validate-only e descarta; /subir continua recusando Demand Gen.',
    obrigatoria: true,
  },
];

const ETAPAS_PMAX: readonly EtapaDaJornada[] = [
  {
    chave: 'objetivos',
    titulo: 'Objetivos e conversion goals',
    pergunta: 'o que esta campanha deve otimizar',
    obrigatoria: true,
  },
  {
    chave: 'compra',
    titulo: 'Orçamento e bidding',
    pergunta: 'verba e estratégia de lance do Performance Max',
    obrigatoria: true,
  },
  {
    chave: 'alcance',
    titulo: 'Geografia e idioma',
    pergunta: 'onde e em que língua a campanha entrega',
    obrigatoria: true,
  },
  {
    chave: 'marca',
    titulo: 'Brand guidelines',
    pergunta: 'como a marca pode aparecer nos anúncios montados pelo sistema',
    obrigatoria: false,
    avancada: true,
  },
  {
    chave: 'url',
    titulo: 'URL final e expansão',
    pergunta: 'destino e se a expansão de URL está permitida',
    obrigatoria: true,
  },
  {
    chave: 'asset-group',
    titulo: 'Asset groups',
    pergunta:
      'Performance Max se organiza em grupos de assets, não em grupos de anúncios de Search. Cada campanha precisa de pelo menos um.',
    obrigatoria: true,
  },
  {
    chave: 'textos',
    titulo: 'Headlines, long headlines e descriptions',
    pergunta: 'os textos mínimos do asset group',
    obrigatoria: true,
  },
  {
    chave: 'visuais',
    titulo: 'Imagens, logos e vídeos',
    pergunta: 'os visuais mínimos. Sem eles o botão de criação não liga.',
    obrigatoria: true,
  },
  {
    chave: 'sinais',
    titulo: 'Audience signals e search themes',
    pergunta: 'sinais de audiência e temas de busca, quando disponíveis',
    obrigatoria: false,
    avancada: true,
  },
  {
    chave: 'listing',
    titulo: 'Listing groups',
    pergunta: 'quando o objetivo é varejo, os grupos de produto do catálogo',
    obrigatoria: false,
    avancada: true,
  },
  {
    chave: 'minimos',
    titulo: 'Conferência dos mínimos e criação atômica',
    pergunta:
      'os vínculos do asset group nascem juntos. Sem o construtor no VOLC e sem os mínimos, não há botão de criação.',
    obrigatoria: true,
  },
];

const ETAPAS_SHOPPING: readonly EtapaDaJornada[] = [
  {
    chave: 'merchant',
    titulo: 'Merchant Center',
    pergunta: 'qual conta de Merchant Center está vinculada e elegível. Sem ela não há campanha para montar.',
    obrigatoria: true,
  },
  {
    chave: 'mercado',
    titulo: 'País e mercado',
    pergunta: 'o mercado em que o catálogo vende',
    obrigatoria: true,
  },
  {
    chave: 'catalogo',
    titulo: 'Feed e diagnóstico do catálogo',
    pergunta: 'o que o Merchant Center declara sobre os produtos',
    obrigatoria: true,
  },
  {
    chave: 'compra',
    titulo: 'Orçamento, lance e prioridade',
    pergunta: 'verba, bidding e prioridade quando o Standard Shopping exigir',
    obrigatoria: true,
  },
  {
    chave: 'produtos',
    titulo: 'Product groups',
    pergunta: 'inventário incluído e excluído, por listing group',
    obrigatoria: true,
  },
  {
    chave: 'rastreamento',
    titulo: 'Tracking e conferência',
    pergunta: 'medição e o que ainda falta no catálogo',
    obrigatoria: true,
  },
];

const ETAPAS_VIDEO: readonly EtapaDaJornada[] = [
  {
    chave: 'observar',
    titulo: 'Observar e analisar',
    pergunta:
      'campanhas Video que já existem na conta podem ser lidas e reportadas. A API não cria nem atualiza este canal.',
    obrigatoria: true,
  },
];

const GRAMATICA: Record<Canal, GramaticaDoCanal> = {
  SEARCH: {
    rotulo: 'Search',
    papelBase: 'operacional',
    frase: 'Campanha de pesquisa com anúncio responsivo. O cockpit real monta o pedido a partir de um funil publicado.',
    apiCria: true,
    etapas: ETAPAS_SEARCH,
    fontes: [FONTES_OFICIAIS.rsa],
  },
  DISPLAY: {
    rotulo: 'Display',
    papelBase: 'parcial',
    frase: 'Campanha de display com Responsive Display Ad. O construtor do VOLC monta a primeira fatia; o que ela não monta vem no manifesto.',
    apiCria: true,
    etapas: ETAPAS_DISPLAY,
    fontes: [FONTES_OFICIAIS.display],
  },
  DEMAND_GEN: {
    rotulo: 'Demand Gen',
    papelBase: 'parcial',
    frase:
      'Demand Gen não é Display com outro nome. O VOLC monta o anúncio multi-asset e pode prová-lo por validate-only quando a capacidade experimental estiver ligada; criação real permanece recusada.',
    apiCria: true,
    etapas: ETAPAS_DEMAND_GEN,
    fontes: [FONTES_OFICIAIS.demandGen],
  },
  PERFORMANCE_MAX: {
    rotulo: 'Performance Max',
    papelBase: 'planejado',
    frase: 'Performance Max se organiza em asset groups. Sem construtor no VOLC e sem os mínimos de assets, não há criação.',
    apiCria: true,
    etapas: ETAPAS_PMAX,
    fontes: [FONTES_OFICIAIS.pmax],
  },
  SHOPPING: {
    rotulo: 'Shopping',
    papelBase: 'pre_requisito',
    frase:
      'Shopping depende do Merchant Center e do catálogo. Sem vínculo elegível o estado é pré-requisito ausente, não erro de campanha.',
    apiCria: true,
    etapas: ETAPAS_SHOPPING,
    fontes: [FONTES_OFICIAIS.shopping],
  },
  VIDEO: {
    rotulo: 'Vídeo',
    papelBase: 'somente_leitura',
    frase:
      'A Google Ads API somente consulta e reporta campanhas Video existentes. Não há criação nem atualização por esta API.',
    apiCria: false,
    etapas: ETAPAS_VIDEO,
    fontes: [FONTES_OFICIAIS.video],
    recusaDaApi:
      'A Google Ads API não cria nem atualiza campanhas Video. Observar as que já existem, ou criar vídeo programático por Demand Gen ou Performance Max quando o VOLC tiver construtor.',
    alternativas: [
      {
        canal: 'DEMAND_GEN',
        rotulo: 'Demand Gen',
        porque: 'rota programática de vídeo nas propriedades Google, inclusive YouTube, quando o VOLC tiver construtor',
      },
      {
        canal: 'PERFORMANCE_MAX',
        rotulo: 'Performance Max',
        porque: 'asset groups podem incluir vídeo quando o construtor e os mínimos existirem',
      },
    ],
  },
};

const PROVA_LEGIVEL: Record<string, string> = {
  politica: 'a política do Google aprova este anúncio?',
  duplicidade: 'já existe campanha nossa para este mesmo termo nesta conta?',
  selo: 'o Google confere o pedido inteiro e devolve o veredito, sem criar nada',
  validate_only: 'o Google confere o pedido inteiro e devolve o veredito, sem criar nada',
};

export function provaLegivel(p: string): string {
  return PROVA_LEGIVEL[p] ?? `${p} — uma prova que esta versão da tela ainda não sabe explicar`;
}

function cruzar(gramatica: GramaticaDoCanal, manifesto: ManifestoDeCanal | null, ctx: ContextoDaJornada): IntersecaoDeAcao {
  const api = gramatica.apiCria;
  // Compatibilidade fail-closed com respostas anteriores ao campo: um canal
  // que já sabia criar também sabia provar; um canal sem criação não ganha
  // prova por inferência. Demand Gen novo declara `sabe_provar=true`.
  const backend = manifesto != null && (manifesto.sabe_provar ?? manifesto.sabe_criar);
  const prova = ctx.capacidades == null
    ? null
    : gramatica.rotulo === 'Demand Gen'
      ? ctx.capacidades.google_demand_gen_validate_only
      : ctx.capacidades.google_validate_only;
  const permissao = ctx.capacidades == null ? null : ctx.capacidades.google_mutate;
  // A rota `/trava` é consultada em repouso. Nesse instante,
  // `escrita_permitida` é sempre false porque o primeiro fator só existe
  // dentro do `with destravar()` da mutação final. A autorização durável que
  // responde "este processo pode tentar publicar?" é `env_presente`.
  // O servidor ainda exige os dois fatores no POST de escrita.
  const trava = ctx.trava == null ? null : ctx.trava.env_presente;

  // Search/Display preservam a montagem local já existente quando a projeção
  // de capacidades não chegou. Demand Gen é diferente: a flag estreita é uma
  // condição do servidor, então ausência/false fecham a superfície.
  const exigeCapacidadeEstreita = gramatica.rotulo === 'Demand Gen';
  const provaLiberada = api && backend && (!exigeCapacidadeEstreita || prova === true);
  // O cockpit existente (`NovaCampanhaPage`) ainda monta Search. Ter builder e
  // porta HTTP de prova não autoriza apontar o operador para esse formulário:
  // ele pediria keywords e terminaria produzindo outro canal. Só os canais já
  // admitidos no caminho real possuem hoje o formulário correspondente.
  const cockpitLiberado = provaLiberada && manifesto?.sabe_criar === true;
  const escritaLiberada = api && backend && manifesto?.sabe_criar === true
    && permissao === true && trava === true;

  if (!api) {
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada,
      cockpitLiberado,
      porqueNao: gramatica.recusaDaApi ?? 'esta API não cria este canal',
      eixo: 'api',
    };
  }
  if (!backend) {
    const recusa =
      manifesto == null
        ? 'o Hub não opera este canal: não há manifesto, não há construtor'
        : (manifesto.indisponibilidades[0] ??
          'o VOLC ainda não tem construtor para este canal');
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada,
      cockpitLiberado,
      porqueNao: recusa,
      eixo: 'backend',
    };
  }
  if (exigeCapacidadeEstreita && prova !== true) {
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada,
      cockpitLiberado,
      porqueNao:
        prova === false
          ? 'a capacidade experimental de prova Demand Gen está desligada neste servidor'
          : 'ainda não sei se este servidor oferece a prova Demand Gen; ausência não abre a porta',
      eixo: 'permissao',
    };
  }
  if (provaLiberada && manifesto?.sabe_criar !== true) {
    // Demand Gen para aqui: a porta `/provar` existe, mas permissão de mutate,
    // trava e canário não participam desta oferta e não devem pintar a prova
    // como bloqueada. A bancada também não finge possuir um formulário visual
    // que ainda não coleta os assets aprovados pelo Estúdio.
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada: false,
      cockpitLiberado: false,
      porqueNao: null,
      eixo: null,
    };
  }
  if (permissao === false) {
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada,
      cockpitLiberado,
      porqueNao:
        ctx.capacidades?.porque_sem_mutacao ??
        'você não tem permissão para escrever na conta de anúncio',
      eixo: 'permissao',
    };
  }
  if (trava === false) {
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada,
      cockpitLiberado,
      porqueNao: ctx.trava?.explicacao || ctx.trava?.motivo || 'a trava de escrita está fechada',
      eixo: 'trava',
    };
  }
  if (permissao == null || trava == null) {
    return {
      api,
      backend,
      permissao,
      trava,
      prova,
      provaLiberada,
      escritaLiberada: false,
      cockpitLiberado,
      porqueNao:
        permissao == null
          ? 'ainda não sei se você pode escrever na conta — a leitura das permissões não chegou'
          : 'ainda não sei se a trava de escrita está aberta',
      eixo: permissao == null ? 'permissao' : 'trava',
    };
  }
  return {
    api,
    backend,
    permissao,
    trava,
    prova,
    provaLiberada,
    escritaLiberada,
    cockpitLiberado,
    porqueNao: null,
    eixo: null,
  };
}

function papelEfetivo(gramatica: GramaticaDoCanal, manifesto: ManifestoDeCanal | null, intersecao: IntersecaoDeAcao): PapelDoCanal {
  if (gramatica.papelBase === 'somente_leitura') return 'somente_leitura';
  if (gramatica.papelBase === 'pre_requisito' && !intersecao.backend) return 'pre_requisito';
  if (intersecao.cockpitLiberado) {
    return manifesto != null && manifesto.indisponibilidades.length > 0 ? 'parcial' : 'operacional';
  }
  if (manifesto != null && !(manifesto.sabe_provar ?? manifesto.sabe_criar)) return 'planejado';
  if (manifesto == null) {
    return gramatica.papelBase === 'pre_requisito' ? 'pre_requisito' : 'planejado';
  }
  return gramatica.papelBase;
}

function ctaDe(
  papel: PapelDoCanal,
  intersecao: IntersecaoDeAcao,
  gramatica: GramaticaDoCanal,
  manifesto: ManifestoDeCanal | null,
): CtaDoCanal {
  if (papel === 'somente_leitura') {
    return {
      tipo: 'observar',
      rotulo: 'Observar e analisar',
      destino: '/trafego?aba=campanhas&canal=VIDEO',
      porque: gramatica.recusaDaApi,
    };
  }
  if (intersecao.provaLiberada && !intersecao.cockpitLiberado) {
    return {
      tipo: 'desbloqueio',
      rotulo: 'Prova HTTP habilitada',
      porque:
        'O builder e POST /provar estão disponíveis para um consumidor tipado de assets aprovados. Esta bancada ainda não coleta esses bytes e não redireciona para o cockpit de Search.',
    };
  }
  if (intersecao.cockpitLiberado) {
    return {
      tipo: 'cockpit',
      rotulo: manifesto?.sabe_criar ? 'Começar campanha' : 'Montar e provar',
      destino: '/trafego?aba=preparar',
      porque: manifesto?.sabe_criar && intersecao.escritaLiberada
        ? undefined
        : manifesto?.sabe_criar
          ? 'o cockpit monta e prova o pedido; a escrita só sai se permissão e trava estiverem abertas'
          : 'esta porta monta e prova por validate-only; não cria nem ativa campanha',
    };
  }
  return {
    tipo: 'desbloqueio',
    rotulo: 'Próximo desbloqueio',
    porque: intersecao.porqueNao ?? 'este canal ainda não tem construtor no VOLC',
  };
}

/**
 * A apresentação de UM canal. O JSX não ramifica por `canal === 'SEARCH'`.
 */
export function apresentarCanal(
  canal: Canal,
  manifesto: ManifestoDeCanal | null,
  ctx: ContextoDaJornada = { capacidades: null, trava: null },
): ApresentacaoDoCanal {
  const gramatica = GRAMATICA[canal];
  const intersecao = cruzar(gramatica, manifesto, ctx);
  const papel = papelEfetivo(gramatica, manifesto, intersecao);
  const recusa = gramatica.recusaDaApi ?? (intersecao.cockpitLiberado ? null : intersecao.porqueNao);

  return {
    canal,
    rotulo: manifesto?.rotulo ?? gramatica.rotulo,
    papel,
    frase: gramatica.frase,
    etapas: gramatica.etapas,
    etapasComoFormulario: intersecao.cockpitLiberado,
    cta: ctaDe(papel, intersecao, gramatica, manifesto),
    alternativas: gramatica.alternativas ?? [],
    provas: (manifesto?.provas_obrigatorias ?? []).map(provaLegivel),
    limites: manifesto && (manifesto.sabe_provar ?? manifesto.sabe_criar)
      ? manifesto.indisponibilidades
      : [],
    recusa,
    intersecao,
    fontes: gramatica.fontes,
  };
}

/**
 * Os seis canais da bancada, sempre nesta ordem.
 *
 * Manifesto ausente não some o canal: vira o papel que a gramática declara
 * (Vídeo = somente leitura, Shopping = pré-requisito). Inventar construtor
 * a partir desta lista é o que este módulo recusa.
 */
export function apresentarBancada(
  manifestos: readonly ManifestoDeCanal[],
  ctx: ContextoDaJornada = { capacidades: null, trava: null },
): ApresentacaoDoCanal[] {
  const porCanal = new Map<string, ManifestoDeCanal>();
  for (const m of manifestos) {
    if (m.plataforma !== 'GOOGLE_ADS') continue;
    porCanal.set(m.canal, m);
  }
  return CANAIS.map((canal) => apresentarCanal(canal, porCanal.get(canal) ?? null, ctx));
}

/** A etapa de Search que o operador lê como criativo. Nunca se chama "Criativos". */
export function etapaDeAnuncio(apresentacao: ApresentacaoDoCanal): EtapaDaJornada | undefined {
  return apresentacao.etapas.find((e) => e.chave === 'anuncio');
}

export function canalTemEtapaObrigatoriaDeImagem(apresentacao: ApresentacaoDoCanal): boolean {
  if (apresentacao.canal === 'SEARCH' || apresentacao.canal === 'VIDEO' || apresentacao.canal === 'SHOPPING') {
    return false;
  }
  return apresentacao.etapas.some(
    (e) => e.obrigatoria && /imagem|imagens|vídeo|video/i.test(`${e.titulo} ${e.pergunta} ${(e.detalhes ?? []).join(' ')}`),
  );
}
