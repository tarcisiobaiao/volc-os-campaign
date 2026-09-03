/**
 * O que a coluna "Em validação" grava, e como o front deve lê-lo.
 *
 * ## Três disciplinas, e elas são o motivo de este arquivo existir
 *
 * 1. **Proveniência tem cor; valor não.** O que separa uma medição de um
 *    julgamento é a única coisa que some em seis meses — e é ela que impede
 *    alguém de tratar opinião de LLM como número medido. Nível de eixo NÃO
 *    ganha cor de bom/ruim: quem decide o que é bom é o operador.
 *
 * 2. **`indice` é texto, nunca ordenação.** Ele é média geométrica sobre eixos
 *    cuja metade veio de julgamento instável. Ordenar por ele daria quatro
 *    casas decimais de precisão a um número que não as tem. O board continua
 *    ordenado por `score`.
 *
 * 3. **Nada aqui esconde card.** `apto: false` tira da FILA, não da tela: o
 *    card continua visível, arrastável e inteiro, com o motivo escrito.
 */

/** De onde veio o nível — a informação que não pode se perder. */
export type Proveniencia = 'medido' | 'julgado' | 'ausente';

/**
 * O portão `(engajamento, dado_unico)` em três estados.
 *
 * MEDIDO: no formulário de nove eixos, `Registrato` — o arquétipo de consulta
 * em base própria — disparava 1 vez em 5. Isolado num prompt só dele, 5 de 5.
 * Não foi variância que a chamada própria comprou, foi recall: 80% de falso
 * negativo consertado no portão dos R$ 138.814.
 *
 * `limitrofe` não é escotilha. A escotilha removida do classificador (o S4)
 * RESGATAVA o tema — subia o nível e o devolvia à fila. Este tira o card da
 * fila exatamente como o portão tira; ele só recusa a fingir certeza.
 */
export type VeredictoPortao = 'portao' | 'limitrofe' | 'sem_portao';

export interface EixoValidado {
  nivel?: string | null;
  proveniencia: Proveniencia;
  motivo_ausencia?: string | null;
}

/** Uma das perguntas que o Google diz que as pessoas fazem sobre a entidade. */
export interface PerguntaLida {
  pergunta: string;
  resposta_literal: string;
  engajamento: string;
  ramos: number;
  condicoes: number;
  decide_depois: boolean;
  /** O ENVELOPE que esta pergunta pede: `artigo` · `artigo_com_ferramenta` ·
   *  `nao_produzir`. Dois formatos e um estado que não é formato.
   *
   *  Vale pelo invariante: `formato === 'artigo'` ⟺ `engajamento === 'sustenta'`.
   *  As duas leem a mesma condição — então mostrar formato é mostrar a mesma
   *  medição, na linguagem da AÇÃO em vez da linguagem do diagnóstico. */
  formato?: string;
  /** Recorte literal da resposta que já NOMEIA os campos do widget. Sai de
   *  `trechos_citados.condicoes_pessoais`, sem segunda chamada de LLM. */
  campos_do_widget?: string;
  /** O veto do roteador: quando o canal oficial resolve, nenhum formato salva. */
  oficial_fecha_sozinho?: boolean;
  estavel?: boolean;
  trechos_citados?: Record<string, string>;
  citacoes_conferem?: Record<string, boolean>;
  tensao?: string;
}

/** A planta da obra: quantas páginas de cada envelope esta entidade rende. */
export interface FormatosDaEntidade {
  por_pergunta?: Record<string, string>;
  n_ferramenta?: number;
  n_artigo?: number;
  n_nao_produzir?: number;
  prescricao?: Array<{ pergunta: string; campos: string; n_campos: number }>;
}

/** O vocabulário do envelope. DOIS formatos e um estado que não é formato.
 *
 *  A arbitragem foi por PRODUÇÃO: só existem dois containers que o operador
 *  publica — texto puro, ou o template injetando um componente interativo.
 *  Checklist, tabela consultável e comparador são o MESMO artefato (2-3 campos
 *  + função + painel de saída); o que os distingue é o rótulo da saída, uma
 *  frase no prompt do redator. Multiplicar enum aqui polui schema pelo mesmo
 *  envelope técnico.
 *
 *  O glifo é o PLANO em um caractere — é ele que forma a planta no card. */
export const FORMATO_PAGINA: Record<string, {
  glifo: string; curto: string; titulo: string; corpo: string;
}> = {
  artigo: {
    glifo: '▪',
    curto: 'sustenta',
    titulo: 'SUSTENTA LEITURA',
    corpo: 'A resposta ramifica ou deixa decisão de pé — há o que ler. É leitura da PERGUNTA, não instrução de página: quem decide a arquitetura do funil é o arquiteto, na etapa 4.',
  },
  artigo_com_ferramenta: {
    glifo: '▤',
    curto: 'ferramenta',
    titulo: 'PEDE FERRAMENTA',
    corpo: 'A resposta é um resultado sobre os dados dela, e o canal oficial não resolve. Pede entrada manipulável — calculadora, simulador ou filtro. Indicação de formato, não de estrutura.',
  },
  nao_produzir: {
    glifo: '·',
    curto: 'fora',
    titulo: 'NÃO SUSTENTA',
    corpo: 'Ou o balcão oficial resolve a pergunta inteira, ou a resposta é a mesma para todo mundo. Esta pergunta não segura leitura sozinha.',
  },
};

export interface PortaoValidacao {
  veredito?: VeredictoPortao | null;
  /** Fração das perguntas do PAA cuja resposta se esgota em segundos.
   *  É ele que decide o portão: 1,0 mata, >= 0,5 pede humano. */
  share_dado_unico?: number | null;
  distribuicao?: Record<string, number> | null;
  n_perguntas?: number | null;
  /** O share de CADA passada, cru. Substituiu o rótulo por passada.
   *
   *  Medido: com 4 perguntas do PAA o share anda de 0,25 em 0,25, e os limiares
   *  (0,5 e 1,0) caem dentro dessa banda — metade dos movimentos de UMA pergunta
   *  trocava o veredito sem que nada tivesse sido medido diferente. A medição
   *  era estável (0,75 · 1,00 · 1,00 é uma pergunta de variação); o rótulo é que
   *  pulava. Então a tela mostra estes números e a dispersão deles. */
  shares_por_passada?: number[];
  share_min?: number | null;
  share_max?: number | null;
  /** Das N passadas, em quantas PERGUNTAS o nível foi o mesmo. É a
   *  confiabilidade real do instrumento em produção — o veredito da entidade
   *  pode bater por compensação e esconder que ele derrapou. */
  concordancia_por_pergunta?: number | null;
  perguntas_instaveis?: string[];
  /** Das citações que o modelo deu, quantas estão MESMO na resposta que ele
   *  escreveu. Mede e não barra: a trava só liga acima de 90%. */
  citacoes_conferidas?: number | null;
  n_citacoes?: number;
  /** Perguntas com `stake` afirmado e não sustentado. Não rebaixa nada —
   *  força revisão humana, que fecha a brecha sem matar tema por string. */
  stake_sem_prova?: number;
  /** A SERP não devolveu bloco de perguntas. Há hipótese de que isso indique
   *  intenção navegacional; ela NÃO foi medida e não decide nada. */
  sinal_paa_ausente?: boolean;
  nota_paa_ausente?: string;
  /** A planta da obra. REPORTA e não decide: não zera índice, não rebaixa
   *  nível, não entra em `posicionar()`. */
  formatos?: FormatosDaEntidade | null;
  n_disparos?: number;
  n_passadas?: number;
  consulta_dominante?: string;
  /** A resposta escrita ANTES do rótulo. É a evidência do veredito. */
  resposta_literal?: string;
  /** "nenhuma" (executa ou desiste) ou as saídas nomeadas. Decide o portão. */
  decisao_que_sobra?: string;
  porque?: string;
  /** O que a passada discordante disse — a razão de ir para revisão humana. */
  divergencia?: string;
  fonte?: string;
}

export interface ValidacaoResumo {
  /** Entra na fila? `false` NÃO esconde o card — só tira do ranking. */
  apto?: boolean;
  motivo?: 'canal_nao_medido' | 'portao_engajamento' | 'portao_limitrofe' | string | null;
  /** As duas coordenadas do quadrante — `familia("demanda_humana")` e
   *  `familia("economia")` do motor. Sem elas o ponto só pode ir ao centro da
   *  célula, e aí o gráfico não acrescenta nada ao rótulo `perfil`. */
  demanda_humana?: number | null;
  economia?: number | null;
  posicao?: number | null;
  /** Texto ao lado do caso. NUNCA chave de ordenação. */
  indice?: number | null;
  cobertura?: number | null;
  perfil?: string | null;
  portoes_disparados?: string[];
  alertas?: string[];
  eixos?: Record<string, EixoValidado>;
  portao?: PortaoValidacao | null;
  /** A leitura da entidade: N perguntas do PAA, cada uma com sua forma. */
  ficha?: {
    share_dado_unico?: number;
    distribuicao?: Record<string, number>;
    pergunta_mais_rica?: string;
    n_perguntas?: number;
    perguntas?: PerguntaLida[];
    comparacao?: { estavel?: boolean; shares?: number[] };
  } | null;
  /** A tensão que a entidade aciona, quando `psique` lê com confiança. */
  tensao?: { tensao: string; pergunta: string; confianca: string } | null;
  /** Existe leilão para este cluster? `cpc: null` é regime de mercado
   *  (demanda real, zero anunciante), não dado faltando. */
  leilao?: { existe?: boolean | null; share_com_leilao?: number } | null;
  /** A evidência tem buraco? Os quatro sensores devolveram nível E a maioria
   *  do cluster pedido voltou. Ver `alvoDeOuro`. */
  sensores?: {
    api_medidos: number; api_total: number;
    termos_pedidos: number; termos_medidos: number;
    fracao_do_cluster: number; limpos: boolean;
  } | null;
  cabeca_demanda?: string | null;
  cabeca_editorial?: string | null;
  validado_em?: string | null;
}

/** `espaco.ESCOPO_PAUTADOR` — os NOVE eixos que esta etapa responde.
 *
 *  `spread` não está aqui, e é decisão: ele é razão de COMPRA e vive no engine
 *  de Ads. Não é linha fantasma nem eixo ausente — não é da conta desta tela,
 *  e a cobertura divide por nove, então card completo dá 100%. */
export const ESCOPO_PAUTADOR = [
  'volume', 'reposicao', 'vacuo', 'formato_consumo',
  'ignorancia', 'engajamento', 'opacidade', 'densidade', 'producao',
] as const;

/** Ordem fixa dos eixos: posição na faixa = eixo, sempre. */
export const EIXOS_EM_ORDEM = ESCOPO_PAUTADOR;

export const ROTULO_EIXO: Record<string, string> = {
  volume: 'volume', reposicao: 'reposição', vacuo: 'vácuo',
  formato_consumo: 'formato de consumo', ignorancia: 'ignorância',
  engajamento: 'engajamento', opacidade: 'opacidade', densidade: 'densidade',
  producao: 'produção', spread: 'spread',
};

/** Quem mede o quê. A fronteira não é negociável e o front a repete. */
export const QUEM_MEDE: Record<string, string> = {
  volume: 'DataForSEO', reposicao: 'DataForSEO', vacuo: 'DataForSEO',
  formato_consumo: 'DataForSEO (composição de domínio da SERP)',
  ignorancia: 'julgamento de LLM', engajamento: 'julgamento de LLM',
  opacidade: 'julgamento de LLM', densidade: 'julgamento de LLM',
  producao: 'julgamento de LLM',
  spread: 'engine de Ads — não é medido aqui',
};

export const MOTIVO_AUSENCIA: Record<string, string> = {
  fora_de_escopo_pautador: 'decidido no engine de Ads, não aqui',
  buraco_de_base: 'a API não devolveu o termo, sem erro declarado. Não é volume zero.',
  serp_sem_organicos: 'a SERP não devolveu resultados orgânicos',
  serie_curta: 'menos de dois ciclos anuais: não dá para separar sazonal de tendência',
  sem_serie: 'sem série histórica para o termo',
  pais_sem_location_code: 'país fora dos mercados mapeados',
  sem_credencial_dataforseo: 'credencial do DataForSEO ausente',
  llm_declarou_desconhecido: 'o classificador não teve base para declarar',
  llm_nao_declarou: 'o classificador não declarou este eixo',
  // Duas ausências diferentes que estavam sendo mostradas como uma só. O Google
  // não ter devolvido perguntas é falta de OBJETO; a ficha vir quebrada é falta
  // de LEITURA. Achatar as duas escondia que a entidade nunca foi lida.
  paa_ausente: 'a SERP não devolveu bloco de perguntas — a entidade não foi lida, e não foi reprovada',
  ficha_invalida: 'a ficha voltou incompleta e foi recusada inteira',
};

/** As frases de veredito. Elas acompanham o número — não o substituem.
 *
 *  O título em caixa alta saiu. Ele afirmava uma fronteira que a aritmética não
 *  sustenta: com 4 perguntas do PAA o share anda de 0,25 em 0,25 e os limiares
 *  caem dentro dessa banda. Quem lidera a caixa agora é `3 de 4 se esgotam` com
 *  as leituras marcadas; estas frases explicam o que isso significa. */
export const VEREDITO_PORTAO: Record<VeredictoPortao, {
  simbolo: string; titulo: string; corpo: string; rodape: string;
}> = {
  portao: {
    simbolo: '⛔',
    titulo: 'não construa',
    corpo: 'Todas as perguntas se esgotaram em segundos, em todas as leituras. O leitor sai antes do anúncio ficar visível e a viewability do domínio cai.',
    rodape: 'evidência forte (9 temas, R$ 138.814) e ainda não replicada fora deles',
  },
  limitrofe: {
    simbolo: '◑',
    titulo: 'você decide',
    corpo: 'As leituras não convergiram para nenhum dos extremos. O número acima é o que se mediu; a fronteira entre "esgota" e "sustenta" cai dentro da variação de uma pergunta, e por isso o motor não decide aqui.',
    rodape: 'a decisão é sua, e é a que o motor não toma',
  },
  sem_portao: {
    simbolo: '✓',
    titulo: 'há o que escrever',
    corpo: 'Nem na leitura mais pessimista metade das perguntas se esgotou.',
    rodape: '',
  },
};

export const PERFIL_HUMANO: Record<string, { titulo: string; corpo: string }> = {
  alvo: { titulo: 'LÊ E PAGA', corpo: 'Demanda humana alta e mercado que paga.' },
  audiencia_pobre: {
    titulo: 'LEITURA RICA, MERCADO POBRE',
    corpo: 'A pessoa lê, mas o mercado não paga por essa atenção.',
  },
  mercado_rico_sem_leitura: {
    titulo: 'MERCADO RICO, LEITURA POBRE',
    corpo: 'Paga bem e não pagina. Só vale com formato que segure atenção.',
  },
  descartar: { titulo: 'DESCARTAR', corpo: 'Um portão disparou.' },
  indefinido: {
    titulo: 'INDEFINIDO',
    corpo: 'Faltam eixos de uma das famílias para cruzar leitura × mercado.',
  },
};

/* ── o motor, espelhado no front ────────────────────────────────────────────
 * Estes números vivem em `motor_pautas/espaco.py` e são copiados aqui porque a
 * tela precisa DESENHAR o peso, não só exibir o nível. Se `PRIORES` mudar lá,
 * muda aqui — e é por isso que a fonte está nomeada em cada bloco.
 */

/** `espaco.PRIORES` — priores declarados, não coeficientes ajustados.
 *  `ignorancia` pesa 2,6x `producao`: é o único eixo com correlação medida
 *  contra desfecho (+0,194). O TRILHO da barra é este número. */
export const PESO: Record<string, number> = {
  ignorancia: 0.90, opacidade: 0.85, engajamento: 0.75, densidade: 0.70,
  spread: 0.70, volume: 0.65, reposicao: 0.60, vacuo: 0.55,
  formato_consumo: 0.35, producao: 0.35,
};

/** `espaco.FAMILIAS` — as três famílias, e o quadrante cruza as duas primeiras. */
export const FAMILIA: Record<string, 'demanda_humana' | 'economia' | 'posicao'> = {
  ignorancia: 'demanda_humana', engajamento: 'demanda_humana',
  opacidade: 'demanda_humana', reposicao: 'demanda_humana',
  volume: 'economia', spread: 'economia', densidade: 'economia',
  formato_consumo: 'economia',
  vacuo: 'posicao', producao: 'posicao',
};

export const ROTULO_FAMILIA: Record<string, string> = {
  demanda_humana: 'demanda humana', economia: 'economia', posicao: 'posição',
};

/** O valor de cada nível, de `espaco.py`. O PREENCHIMENTO da barra é este
 *  número — nunca reescalado pelo peso. Um eixo no topo da própria escala
 *  aparece CHEIO por menor que seja o trilho: `texto_busca` vale 1,00 e pesa
 *  0,35, então é trilho curto e cheio. Confundir os dois é o erro que a barra
 *  existe para evitar. */
export const VALOR_DO_NIVEL: Record<string, Record<string, number>> = {
  ignorancia: { nao_sei_se_existe: 1.0, nao_sei_se_sirvo: 0.75,
    nao_sei_por_que_falhou: 0.65, so_falta_um_dado: 0.30, sei_o_que_fazer: 0.30,
    nao_preciso_de_nada: 0.02 },
  // Dois estados, não cinco: a escala antiga concentrou 62,5% num lote e 76,2%
  // noutro, trocando de nível dominante só com a amostra. Os quatro nomes
  // antigos ficam mapeados para LER card já gravado sem quebrar a barra.
  engajamento: { sustenta: 1.0, dado_unico: 0.05,
    diagnostico: 1.0, condicional: 1.0, sequencial: 1.0, comparativo: 1.0 },
  opacidade: { regra_mudou: 1.0, fragmentada: 0.85, ilegivel: 0.60, clara: 0.10 },
  reposicao: { continua: 1.0, anual: 0.70, mesma_gente: 0.55, unica: 0.20 },
  volume: { massivo: 1.0, alto: 0.80, medio: 0.55, baixo: 0.30, residual: 0.10 },
  spread: { excelente: 1.0, bom: 0.75, neutro: 0.50, ruim: 0.25 },
  densidade: { densa: 1.0, media: 0.60, rala: 0.25, nenhuma: 0.05 },
  formato_consumo: { texto_busca: 1.0, misto: 0.65, video_social: 0.30,
    voz_ou_humano: 0.15 },
  vacuo: { virgem: 1.0, raso: 0.70, disputado: 0.35, saturado: 0.10 },
  producao: { escreve_uma_vez: 1.0, revisao_anual: 0.75, revisao_mensal: 0.45,
    acompanhamento: 0.20 },
};

/** `espaco.perfil()` corta as duas famílias em 0,60. É a linha do quadrante. */
export const CORTE_QUADRANTE = 0.60;

/* ── ALVO DE OURO ───────────────────────────────────────────────────────────
 * Uma CLASSE, não uma ordem. Vários cards podem ser ouro e nenhum é "o
 * primeiro" — o índice continua sem ordenar nada.
 *
 * A conjunção é de condições defensáveis sozinhas, e as duas últimas são o que
 * separa ouro de sorte: um alvo apoiado em 4 medidos e 5 julgados não é a mesma
 * coisa que um apoiado em 8 medidos.
 */
export const COBERTURA_OURO = 1.0;

export interface Ouro {
  e: boolean;
  /** Por que sim, ou o que faltou — nunca "não qualificou" sem dizer o quê. */
  motivo: string;
}

export function alvoDeOuro(v?: ValidacaoResumo | null): Ouro {
  if (!v) return { e: false, motivo: 'não medido' };
  const s = v.sensores;
  const cobertura = v.cobertura ?? 0;
  const portao = v.portao?.veredito;

  const faltou: string[] = [];
  if (v.perfil !== 'alvo') faltou.push(`perfil ${v.perfil ?? '—'}`);
  if (portao && portao !== 'sem_portao') faltou.push(`portão ${portao}`);
  if ((v.portoes_disparados ?? []).length) faltou.push(`portão ${v.portoes_disparados![0]}`);
  if (cobertura < COBERTURA_OURO) faltou.push(`cobertura ${Math.round(cobertura * 100)}%`);
  // OS QUATRO SENSORES LIMPOS. Nada além disso.
  //
  // Eu tinha empilhado "e ao menos 2/3 do cluster voltou" por cima, e isso
  // barrou `Cartão para Negativado`: perfil alvo, 4 de 4 sensores, cobertura
  // 100%, sem portão, reprovado por 43% de cluster. A fração mede quanto do
  // fraseado o Labs carrega, não buraco nos quatro eixos. Era limiar meu, não
  // evidência, e limiar que barra o caso certo é limiar errado.
  //
  // A fração continua visível no tooltip como confiança, sem poder de veto.
  if (!s || s.api_medidos < s.api_total) {
    faltou.push(s ? `sensores ${s.api_medidos} de ${s.api_total}` : 'sensores desconhecidos');
  }

  if (!faltou.length) {
    return {
      e: true,
      motivo: `lê e paga, sem portão, cobertura 100%, ${s!.api_medidos} sensores limpos sobre ${Math.round(s!.fracao_do_cluster * 100)}% do cluster`,
    };
  }
  const base = v.perfil === 'alvo' ? 'alvo, mas ' : '';
  return { e: false, motivo: base + faltou.join(' · ') };
}

/** O relatório que a rota de validação devolve. O custo dos DOIS modos vem
 *  junto de propósito: sem ele alguém arrasta vinte cards um a um e paga a
 *  base vinte vezes sem saber. */
export interface ValidacaoRelatorio {
  lote_id?: string;
  modo?: 'lote' | 'individual';
  cards: number;
  custo_usd: number;
  custo_por_card_usd?: number;
  custo_individual_estimado_usd?: number;
  economia_do_lote_usd?: number;
  keywords_pedidas?: number;
  keywords_devolvidas?: number;
  faltantes?: string[];
  erros?: string[];
  duracao_ms?: number;
  resultados?: Array<{ opportunity_id: number; termo: string } & ValidacaoResumo>;
}

/** Um eixo visto no meio da medição — o progresso lido do banco. */
export interface EixoEmProgresso {
  eixo: string;
  nivel: string | null;
  proveniencia: string;
  motivo_ausencia: string | null;
  medido_em: string;
}

/** A ordem em que os eixos CAEM, que é a ordem dos passos do orquestrador.
 *  A tela mostra isso porque é o que de fato acontece, não uma animação. */
export const ETAPAS_DA_MEDICAO: { rotulo: string; eixos: string[] }[] = [
  { rotulo: 'histórico do cluster', eixos: ['volume', 'reposicao'] },
  { rotulo: 'SERP e audiência', eixos: ['vacuo', 'formato_consumo'] },
  { rotulo: 'leitura da pessoa', eixos: ['ignorancia', 'engajamento', 'opacidade', 'densidade', 'producao'] },
];

// ── elegibilidade paga ──────────────────────────────────────────────────────
//
// A SEGUNDA resposta. `ValidacaoResumo`, acima, responde "vale produzir
// conteúdo sobre este tema?". Isto responde "quais termos podem entrar num
// leilão?", e as duas não se decidem. Um tema pode ser apto a virar pauta com
// todas as suas keywords retidas — é o caso comum de um tema institucional.
//
// Espelha `backend/app/agents/mining/paid_eligibility.py`. Viaja dentro de
// `factory_output[].keywords_campanha.conjunto_pago`, sem endpoint novo e sem
// migration: `MineResponse.factory_output` já é `List[Dict[str, Any]]`.

/** O estado de um número, para que a tela nunca escreva 0 onde falta dado. */
export type EstadoDoDado =
  | 'measured'
  | 'confirmed_zero'
  | 'absent'
  | 'unknown'
  | 'not_applicable'
  | 'failed'
  | 'inferred';

/** Um número de leilão com o estado que autoriza lê-lo. `valor` é `null`
 *  sempre que o estado não comporta número — nunca 0 por omissão. */
export interface SinalPago {
  valor: number | null;
  estado: EstadoDoDado;
  fonte: string;
  frescor: string | null;
  motivo: string | null;
  proveniencia: string;
}

export type DecisaoPaga = 'INCLUDE' | 'EXPERIMENT' | 'HOLD' | 'REJECT' | 'HUMAN_REVIEW';

/** `situacao` responde "entrou no conjunto?", que é pergunta diferente de
 *  `decisao` ("é elegível?"). Um termo pode ser elegível e ficar de fora por
 *  quantidade — `ELEGIVEL_NAO_SELECIONADO`. */
export type SituacaoPaga = 'SELECIONADO' | 'ELEGIVEL_NAO_SELECIONADO' | DecisaoPaga;

export interface KeywordPaga {
  termo: string;
  termo_normalizado: string;
  original?: string | null;
  subintencao?: string | null;
  estagio?: string;
  arquetipos: string[];
  match_type: string;
  volume: SinalPago;
  cpc: SinalPago;
  congruencia: string;
  amplitude: string;
  riscos: Record<string, boolean>;
  viabilidade: string;
  confianca: string;
  decisao: DecisaoPaga;
  situacao: SituacaoPaga;
  motivos: string[];
  bloqueadores: string[];
  alertas: string[];
  selecionada: boolean;
}

export interface ConjuntoPago {
  candidates: KeywordPaga[];
  selected_keywords: KeywordPaga[];
  excluded_keywords: KeywordPaga[];
  human_review_keywords: KeywordPaga[];
  /** Sempre vazio: negativa exige search-term evidence e revisão de
   *  overblocking, e as duas moram fora deste motor. */
  negative_keywords: unknown[];
  owner_ceiling: number | null;
  selection_policy_version: string;
  evidence_snapshot: Record<string, unknown>;
  selected_set_sha256: string;
  approved_set_sha256: string | null;
  aprovado_por: string | null;
  /** ⚠️ Significa que o CONJUNTO pode ser preparado com governança. NÃO
   *  significa conta apta, destino aprovado, mensuração pronta nem campanha
   *  autorizada — `portoes_externos_pendentes` diz isso em voz alta. */
  ready_for_campaign_plan: boolean;
  portoes_externos_pendentes: Record<string, string>;
  blockers: string[];
  alertas: string[];
}

/** Um item de `factory_output`, na parte que a tela lê. */
export interface FunilDeProducao {
  project_name?: string | null;
  keywords_campanha?: {
    lista_google_ads?: string;
    conjunto_pago?: ConjuntoPago;
    stats?: { total_keywords?: number; total_volume?: number; avg_cpc?: string; avg_cpc_estado?: string; avg_cpc_n?: number };
  };
}

/** O rótulo humano de cada decisão. O texto é o que a pessoa lê antes de
 *  aprovar, então ele diz o que a decisão faz, não como ela se chama. */
export const ROTULO_DECISAO_PAGA: Record<SituacaoPaga, { titulo: string; tom: string }> = {
  SELECIONADO: { titulo: 'no conjunto', tom: 'text-success' },
  ELEGIVEL_NAO_SELECIONADO: { titulo: 'elegível, fora por quantidade', tom: 'text-muted-foreground' },
  INCLUDE: { titulo: 'elegível', tom: 'text-success' },
  EXPERIMENT: { titulo: 'experimento', tom: 'text-warning' },
  HOLD: { titulo: 'retida', tom: 'text-muted-foreground' },
  REJECT: { titulo: 'recusada', tom: 'text-destructive' },
  HUMAN_REVIEW: { titulo: 'revisão humana', tom: 'text-warning' },
};

/** Um número que talvez não exista. `—` quando não existe — nunca `0`. */
export function leSinal(s?: SinalPago | null, casas = 0): string {
  if (!s || s.valor === null || s.valor === undefined) return '—';
  return casas > 0 ? s.valor.toFixed(casas) : s.valor.toLocaleString('pt-BR');
}
