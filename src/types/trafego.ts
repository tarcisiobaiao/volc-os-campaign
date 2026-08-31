// ============================================
// HUB DE TRÁFEGO — a terceira etapa do ciclo PAUTA → FUNIL → CAMPANHA
//
// O Pautador acha o tema e minera as keywords. O Redator escreve o funil.
// Aqui compra-se o clique que leva alguém até lá.
// ============================================

/** Um CPC com a procedência colada. NUNCA um número solto.
 *
 *  `services_used` do cluster medido inclui `n8n:dataforseo`, e a moeda chega
 *  nula. O `DATAFORSEO-MEDIDO` mediu, com 96 chamadas, que `keyword_info.cpc`
 *  superestima o CPC real em 7,4× **e inverte a ordem dentro do cluster** —
 *  nenhum fator de correção resolve.
 *
 *  Por isso o tipo carrega os quatro campos juntos: apresentar `valor` sem
 *  `procedencia` é o defeito que este módulo inteiro existe para não cometer. */
export interface Cpc {
  valor: number;
  procedencia: string;
  /** Pode ser `null` — o cluster não declara moeda. A tela diz "moeda não
   *  declarada" em vez de assumir BRL: assumir é como um número de sete países
   *  vira um número de um país sem ninguém notar. */
  moeda: string | null;
  medido_na_conta: boolean;
}

export interface KeywordCandidata {
  texto: string;
  volume: number;
  cpc: Cpc | null;
  competicao: string;
  tendencia: number | null;
  tags: string[];
  /** Por que a mineração aprovou esta keyword para anúncio. É o que permite ao
   *  operador discordar da triagem sabendo do quê. */
  motivo: string;
  tambem_em_conteudo: boolean;
}

/** Uma sub-intenção. É um candidato a AD GROUP, não um rótulo.
 *
 *  Medido no cluster do card 73: spread de CPC de ~2× entre grupos, e o grupo
 *  ACESSO tem 89,1% do volume numa keyword só. Um ad group para todos
 *  significaria um lance só — caro demais para um lado e barato demais para o
 *  outro ao mesmo tempo. */
export interface GrupoCandidato {
  tipo: string;
  descricao: string;
  keywords: KeywordCandidata[];
  volume: number;
  /** Média dos termos. */
  cpc_simples: Cpc | null;
  /** Média do TRÁFEGO. Diverge da simples quando um termo de volume enorme puxa
   *  o grupo — e essa divergência é justamente onde mora a concentração. */
  cpc_ponderado: Cpc | null;
  volume_declarado: number | null;
  keywords_declaradas: number | null;
  fora_da_fila: string[];
}

/** A triagem que a mineração já fez, apresentada COMO triagem.
 *  `analisadas` é o denominador honesto: "23 aprovadas" sem ele esconderia que
 *  63 foram descartadas — e o descarte é trabalho feito, não lixo. */
export interface Triagem {
  analisadas: number;
  aprovadas_anuncio: number;
  para_conteudo: number;
  descartadas: number;
  breakdown: Record<string, number>;
  volume_total: number;
  volume_da_fila: number;
}

export interface Fato {
  id: string;
  tipo: string;
  texto: string;
  fonte: string;
}

export interface OrigemDaCampanha {
  opportunity_id: number;
  run_id: number | null;
  project_id: number | null;
  url_final: string;
  url_procedencia: string;
  /** ⚠️ De um RASCUNHO o WordPress devolve `?post_type=r&p=2146`, não o
   *  permalink. Anunciar essa URL manda tráfego para um endereço que vai mudar. */
  status_wp: string | null;
  post_type: string | null;
  dominio: string;
  nicho: string;
  slug: string;
  pais: string;
  idioma: string;
  idioma_declarado: string | null;
  /** Eixo do portão de habilitação (país × vertical) do `policy/spec.py`, não
   *  um rótulo. `vertical_declarada` guarda o que o card dizia, para a
   *  divergência ficar auditável. */
  vertical: string;
  vertical_declarada: string | null;
  resumo_da_pesquisa: string;
  fatos: Fato[];
  tem_texto_da_lp: boolean;
  /** Só viaja com `?com_texto_da_lp=true`. É o artigo inteiro. */
  texto_da_lp?: string;
}

export interface AvisoDoCockpit {
  codigo: string;
  severidade: 'informacao' | 'atencao' | 'bloqueio' | string;
  titulo: string;
  detalhe: string;
}

export interface Descartada {
  texto: string;
  volume: number;
  cpc: Cpc | null;
  motivo: string;
  destino: string;
}

export interface Cockpit {
  opportunity_id: number;
  cluster_id: number | null;
  origem: OrigemDaCampanha;
  triagem: Triagem | null;
  grupos: GrupoCandidato[];
  descartadas: Descartada[];
  procedencia: {
    servicos_declarados: string[];
    engine: string | null;
    moeda_do_cluster: string | null;
    moeda_da_oportunidade: string | null;
    cpc_medio_do_cluster: number | null;
    medido_na_conta: boolean;
    aviso: string | null;
  } | null;
  avisos: AvisoDoCockpit[];
  /** O que este funil já lançou. Vazio quando nenhuma — e é isso que decide se
   *  a tela mostra "lançar" ou "já está no ar". */
  campanhas_lancadas?: CampanhaLancada[];
  /** A conta vem do PROJETO, não do operador. `pautador_funnel_runs` carrega
   *  `project_id` e `projects` guarda os dois ids — o funil já sabia em que
   *  conta a campanha ia entrar. `null` quando o projeto não tem vínculo. */
  conta: {
    project_id: number;
    dominio: string;
    customer_id: string | null;
    login_customer_id: string | null;
    vinculada: boolean;
    motivo: string | null;
    nome?: string | null;
    /** ⚠️ Moeda e fuso MUDAM o payload: o fuso decide a que hora o dia do
     *  orçamento vira, e a moeda é a unidade do lance que o operador digita.
     *  Nenhum dos dois aparecia na tela. */
    moeda?: string | null;
    fuso?: string | null;
    teste?: boolean;
    /** ⚠️ `marcacao.py` recusa `marcacao_gclid=True` quando isto é `true` — o
     *  Google já anexa o gclid e declarar a macro duplica o parâmetro. */
    auto_tagging?: boolean;
    /** Para o que a campanha vai otimizar. NÃO é escolhido aqui: é a ação
     *  primária da CONTA, porque o campo `conversao` do brief não é lido por
     *  ninguém. A tela mostra a meta real em vez da que se pensou escolher. */
    meta_conversao?: {
      acoes: { id: string; nome: string; categoria: string; tipo: string; primaria: boolean }[];
      primaria: { id: string; nome: string; categoria: string; tipo: string } | null;
      por_que: string;
    } | null;
    detalhes_indisponiveis?: string;
  } | null;
}

// ── o quadro ────────────────────────────────────────────────────────────────

// ── reconciliação: "este funil já tem campanha?" ────────────────────────────

/**
 * O veredito sobre um funil.
 *
 * A pergunta deixou de ser "há linha no nosso cadastro?" e passou a ser "há, na
 * conta deste projeto, campanha que aponte para o destino deste funil?". A conta
 * de anúncio é a autoridade sobre existência e estado (ADR-01).
 */
export type EstadoDeReconciliacao =
  /** Vínculo humano confirmado, e a campanha está presente na conta. */
  | 'vinculada'
  /** Sinal suficiente para revisão, insuficiente para afirmar o vínculo. */
  | 'correspondencia_provavel'
  /** Mais de uma candidata presente. Escolher em silêncio seria vincular errado. */
  | 'conflito'
  /** Nenhuma candidata, depois de uma prova que pôde ser feita. */
  | 'sem_campanha'
  /** Só há candidatas no histórico removido. Relançar exige motivo declarado. */
  | 'somente_historico';

export type AcaoDeReconciliacao =
  | 'montar'
  | 'abrir_o_que_existe'
  | 'confirmar_vinculo'
  | 'abrir_revisao'
  | 'relancar_declarado';

/**
 * Por que uma campanha entrou como candidata.
 *
 * `forte` é o que foi OBSERVADO na conta; `medio` é o que foi DECLARADO por
 * nós. Uma declaração pode estar desatualizada — alguém renomeia a campanha no
 * painel do Google e ela deixa de ser verdade sem que nada perceba.
 */
export interface SinalDeReconciliacao {
  regra:
    | 'url_final_da_conta'
    | 'url_no_nome_declarado'
    | 'linhagem_declarada'
    | 'lancamento_declarado';
  /**
   * `forte` é observado na conta e com carimbo próprio. `medio` é declarado
   * por nós — pode estar desatualizado. `historica` é observado **sem** carimbo
   * próprio: sustenta a candidata e não fecha o vínculo sozinha.
   *
   * Hoje `url_final_da_conta` é `historica`, e não `forte`: o espelho não
   * guarda quando a URL foi lida, e o gatilho a preserva entre varreduras.
   * Volta a ser `forte` quando existir `url_final_lida_em`.
   */
  forca: 'forte' | 'medio' | 'historica';
  evidencia: Record<string, unknown>;
}

export interface CandidataDeReconciliacao {
  volc_campaign_id: string;
  externa: { customer_id: string | null; campaign_id: string };
  nome: string;
  estado_externo: string | null;
  canal: string | null;
  /** A conta declara esta campanha removida. História não disputa leilão. */
  historico: boolean;
  vinculo_id: string | null;
  /** Sugestão sem regra visível não é oferecida (SPEC 3.2). */
  sinais: SinalDeReconciliacao[];
}

export interface Reconciliacao {
  opportunity_id: number;
  run_id: number | null;
  estado: EstadoDeReconciliacao;
  candidatas: CandidataDeReconciliacao[];
  /**
   * Que regra não pôde correr, e por quê.
   *
   * É o que impede `sem_campanha` de significar duas coisas incompatíveis:
   * "provei e não há" (libera a montagem) e "não consegui provar" (não deveria).
   */
  sinais_ausentes: Array<{
    regra: string;
    motivo: string;
    /**
     * `true` = **não havia como comparar**. Diferente de "comparei por um
     * caminho mais fraco" e de "esta regra nunca se aplica aqui".
     *
     * Quando há algum `impede_prova`, `sem_campanha` vem com
     * `exige_confirmacao_humana: true`: montar continua liberado (quase todo
     * funil novo começa em rascunho), mas a tela avisa em vez de convidar.
     */
    impede_prova: boolean;
  }>;
  acao_permitida: AcaoDeReconciliacao;
  exige_confirmacao_humana: boolean;
  pode_montar: boolean;
  pode_relancar: boolean;
}

/**
 * O vocabulário fechado que o servidor aplica, servido pela fonte que o aplica.
 *
 * Existe para a tela não manter uma segunda cópia da lista — divergência de
 * vocabulário entre front e back foi medida em cinco lugares (E-21).
 */
export interface VocabularioDoInventario {
  versao: number;
  presenca: string[];
  frescor: string[];
  procedencia: string[];
  canal: string[];
  apelidos_de_canal: Record<string, string>;
  estrategia: string[];
  segundos_para_velho: number;
  plataformas: Plataforma[];
  /** Todos os canais de todas as plataformas, com o que cada um pode. */
  manifestos: ManifestoDeCanal[];
  estados_de_reconciliacao: string[];
}

/**
 * Capacidades gerais do operador e portas experimentais mais estreitas.
 *
 * ⚠️ `is_admin` NÃO implica `google_mutate`. Papel de produto e direito de
 * gastar na conta do cliente são decisões de tamanhos muito diferentes, e a
 * separação é o que impede "promover alguém a administrador" de significar
 * "essa pessoa pode gastar".
 *
 * A implicação inversa vale: quem pode mutar é necessariamente admin. O
 * servidor recusa a combinação incoerente antes de responder.
 */
export interface CapacidadesDoOperador {
  /** Papel de PRODUTO: administra usuários, contas, projeto. */
  is_admin: boolean;
  /**
   * Pode navegar a jornada inteira com fixture declarada.
   *
   * Fecha sozinho quando a escrita na conta abre — um laboratório que
   * continuasse ligado sobre um sistema com consequência seria a pior
   * combinação possível.
   */
  lab_mode: boolean;
  /** Pode ver o que já foi lido da conta. */
  google_read: boolean;
  /**
   * Pode mandar o Google CONFERIR um pedido sem criar nada.
   *
   * Não espera a trava de escrita: `validate_only` é leitura para todos os
   * efeitos — a API confere o payload e o descarta.
   */
  google_validate_only: boolean;
  /** Porta mais estreita que a prova geral: o servidor pode conferir Search e
   *  Display e ainda assim manter Demand Gen invisível. Ausência desta
   *  capacidade nunca é reinterpretada como `google_validate_only=true`. */
  google_demand_gen_validate_only?: boolean;
  /** Pode criar ou alterar campanha de verdade. */
  google_mutate: boolean;
  /**
   * Por que a mutação está fechada, em uma frase para o OPERADOR. `null`
   * quando está aberta.
   *
   * Nunca cita variável de ambiente, função nem arquivo: quem lê a tela não
   * tem acesso ao servidor, e instrução impossível de executar faz a pessoa
   * concluir que o sistema está quebrado.
   */
  porque_sem_mutacao: string | null;
}

/**
 * O veredito do lado da CAMPANHA — o inverso de `EstadoDeReconciliacao`.
 *
 * ⚠️ Os dois vocabulários não se traduzem. `conflito` do funil significa "duas
 * campanhas me disputam"; visto da campanha, isso é uma ressalva sobre o funil
 * candidato, não o estado dela. Reusar o tipo do funil aqui faria a tela dizer
 * que a Maquininha está em conflito quando quem está é o funil.
 */
export type EstadoDeCorrespondencia =
  /** Já existe decisão humana registrada. Nada a revisar, só a desfazer. */
  | 'associada'
  /** Nenhum funil casou. Estado normal de campanha descoberta pela varredura. */
  | 'sem_correspondencia'
  /** Um funil casou. É pergunta, e continua pergunta até alguém responder. */
  | 'correspondencia_unica'
  /** Mais de um funil casou. A escolha é do operador. */
  | 'mais_de_uma_correspondencia'
  /** Não houve como comparar. Distinto de `sem_correspondencia`. */
  | 'nao_apurada';

/** Um funil que casa com esta campanha, e tudo o que sustenta o casamento. */
export interface Correspondencia {
  opportunity_id: number;
  run_id: number | null;
  project_id: number | null;
  /** As URLs deste funil, normalizadas — o que o operador compara com o olho. */
  destinos: string[];
  sinais: SinalDeReconciliacao[];
  /**
   * O veredito do FUNIL, dito como ressalva. `conflito` aqui significa que
   * outra campanha presente também aponta para este funil.
   */
  estado_do_funil: EstadoDeReconciliacao;
  /** Quantas OUTRAS campanhas presentes disputam este mesmo funil. */
  outras_campanhas_presentes: number;
  /** A força do sinal mais forte. Precedência explícita, nunca alfabética. */
  forca_maxima: SinalDeReconciliacao['forca'];
}

export interface RevisaoDeCorrespondencia {
  volc_campaign_id: string;
  estado: EstadoDeCorrespondencia;
  /**
   * A URL que o anúncio desta campanha aponta, normalizada — o que o operador
   * compara com `Correspondencia.destinos`. Vive aqui e não em
   * `CampanhaNoInventario` porque a listagem não compara URL, e acrescentar
   * campo a uma projeção usada por 84 linhas para servir a uma tela seria
   * pagar em toda parte o custo de um lugar só.
   */
  url_da_campanha: string | null;
  correspondencias: Correspondencia[];
  sinais_ausentes: Reconciliacao['sinais_ausentes'];
  /** O vínculo vivo, quando já existe. Permite oferecer desfazer. */
  vinculo: {
    vinculo_id: string;
    opportunity_id: number | null;
    run_id: number | null;
  } | null;
  /** Nunca automático (ADR-09). */
  exige_confirmacao_humana: boolean;
}

export interface CandidatoNoQuadro {
  opportunity_id: number;
  run_id: number;
  titulo: string;
  dominio: string;
  lp_url: string | null;
  paginas_publicadas: number;
  tem_cluster: boolean;
  keywords_para_anuncio: number;
  volume_total: number | null;
  servicos_declarados: string[];
  /**
   * ⚠️ **Não é mais a autoridade.** Quantas candidatas PRESENTES a reconciliação
   * encontrou — mantido para quem ainda lê o campo.
   *
   * `null` quando a prova não pôde ser feita. Nulo não é zero: zero afirmaria
   * "não há campanha", que é exatamente o que não foi apurado.
   *
   * Quem decide se o quadro oferece "montar campanha" é `reconciliacao`.
   */
  campanhas_lancadas?: number | null;
  /**
   * O veredito completo, com candidatas, sinais e ação permitida.
   *
   * `null` quando a prova falhou. Nesse caso a tela avisa em vez de convidar —
   * "não consegui provar" nunca pode passar por "provei e não há".
   */
  reconciliacao?: Reconciliacao | null;
  /** O projeto do funil. É por ele que se descobre a conta de anúncio. */
  project_id?: number | null;
  /** As URLs reais das páginas publicadas, e não só quantas são. */
  urls_publicadas?: string[];
}

export interface QuadroDeTrafego {
  prontos: CandidatoNoQuadro[];
  totais: {
    funis_publicados: number;
    com_cluster: number;
    keywords_disponiveis: number;
  };
  /** Declarado na resposta, não só na tela: não existe camada de métrica no
   *  engine (`metrics.` = 0 ocorrências). Quem consome isto não deve procurar
   *  performance aqui nem inventá-la a partir de outro campo. */
  sem_metrica: boolean;
  por_que: string;
}

// ── a prova ─────────────────────────────────────────────────────────────────

export interface AchadoLocal {
  campo: string;
  valor: string;
  motivo: string;
  severidade: string;
}

/** ⚠️ Estes nomes espelham `ErroGads`/`Politica` de `volc_ads/gads/errors.py`,
 *  e por um tempo não espelhavam: o tipo pedia `familia`, `is_exemptible` e
 *  `chaves` (plural), campos que a dataclass não tem. O `getattr` do backend
 *  devolvia vazio sem levantar nada, e o que sobrava na tela era a mensagem
 *  genérica do Google — "A policy was violated. See PolicyViolationDetails" —
 *  justamente a frase que manda olhar o detalhe que estava sendo descartado. */
export interface ErroDaApi {
  codigo: string;
  /** `valor_codigo` do erro, ex.: `POLICY_ERROR`. */
  valor: string;
  caminho: string;
  indice: number | null;
  mensagem: string;
  /** O texto EXATO que violou. É o campo mais útil da resposta inteira. */
  gatilho: string;
  politica: {
    formato: string | null;
    /** `true` = comporta `exempt_policy_violation_keys`. É a diferença entre
     *  "ajuste e siga" e "esta keyword não entra". */
    isentavel: boolean | null;
    remedio: string | null;
    nome_externo: string;
    descricao_externa: string;
    chave: { policy_name: string; violating_text: string } | null;
    topicos: { topico: string; tipo: string; ignoravel: boolean | null;
               evidencias: string[] }[];
  } | null;
}

/** O resultado da prova. Os três estados NÃO são intercambiáveis:
 *
 *  `recusa_local`    reprovou aqui, de graça, antes de qualquer chamada
 *  `falha_validacao` o payload chegou à API e ela recusou (nada foi criado)
 *  `selo`            passou nos dois — é o pré-requisito estrutural de subir */
export interface Preparo {
  customer_id: string;
  login_customer_id: string;
  nome_campanha: string;
  n_operacoes: number;
  selo: { impressao: string; n_operacoes: number; carimbo: string } | null;
  /** ⚠️ `resumo` é o campo que CARREGA O MOTIVO, e por muito tempo ele não
   *  estava aqui. `recusa_local` chega do backend como TEXTO — `subir.py`
   *  monta a string —, então `achados` vem sempre vazio e a tela dizia
   *  "0 achado(s)". Medido no card 65 em 19/08/2026: a recusa real era
   *  "Exige certificacao_servicos_oficiais (política 15332527)" e o operador
   *  via um zero, sem uma linha do que consertar. */
  recusa_local: { ok: boolean; resumo?: string; achados: AchadoLocal[] } | null;
  falha_validacao: {
    classe: string | null;
    resumo: string;
    request_id: string | null;
    /** Os textos que violaram, agregados. É o que responde "o que eu tiro?". */
    textos_violadores?: string[];
    /** As chaves que `exempt_policy_violation_keys` aceitaria — só as que a
     *  API marcou `is_exemptible`. Pedir isenção de violação não isentável é
     *  requisição rejeitada, não anúncio publicado. */
    chaves_isentaveis?: string[];
    de_politica?: boolean;
    erros: ErroDaApi[];
  } | null;
  aprovado: boolean;
  /** O que a autocorreção de política fez — uma linha por decisão. Vem também
   *  quando a prova PASSOU: é aí que a mudança silenciosa engana, porque o
   *  operador aprovaria a campanha sem saber que uma keyword saiu. */
  autocorrecao?: string[];
  /** Os AVISOS da validação local — conflito entre negativa e keyword,
   *  duplicata removida, keyword mantida só no primeiro grupo.
   *
   *  ⚠️ Vêm inclusive quando a prova PASSA, pela mesma razão da `autocorrecao`:
   *  `recusa_local` só é preenchido quando algo BARRA, então no caminho feliz —
   *  o caminho em que o operador aprova e gasta — eles não teriam por onde
   *  chegar. Ver `Preparo.avisos_locais` em `volc_ads/subir.py`. */
  avisos_locais?: string[];
}

export interface RespostaDaProva {
  preparo: Preparo;
  avisos: AvisoDoCockpit[];
  /** O que este funil já lançou. Vazio quando nenhuma — e é isso que decide se
   *  a tela mostra "lançar" ou "já está no ar". */
  campanhas_lancadas?: CampanhaLancada[];
  grupos: { tipo: string; keywords: number }[];
  /** A autorização estreita do primeiro canário. A impressão cobre o pedido
   * inteiro; qualquer alteração posterior obriga uma nova prova. */
  autorizacao: AutorizacaoDoCanario;
}

export interface PoliticaDoCanario {
  customer_id: string;
  customer_id_formatado: string;
  customer_label: string;
  login_customer_id: string;
  canal: 'SEARCH';
  cria_pausada: true;
  inclui_ativacao: false;
  orcamento_diario_maximo_brl: string;
  cpc_maximo_brl: string;
}

export interface AutorizacaoDoCanario {
  /** Hash do payload Google efetivo, pós-autocorreção. Nulo quando a prova não
   * produziu selo e, portanto, não existe nada aprovável. */
  plano_impressao: string | null;
  /** Hash da intenção declarada, usado somente na marca remota. */
  chave_intencao: string;
  /** Congela os nomes do protobuf entre a prova e a criação. */
  carimbo_nome: string;
  alvo_canario: boolean;
  elegivel: boolean;
  motivo_elegibilidade: string;
  politica: PoliticaDoCanario;
  budget_diario: number;
  cpc_inicial: number;
  ativacao_incluida: false;
}

/** O que o ledger v10 registrou sobre ESTA tentativa de lançamento.
 *
 *  ⚠️ Os quatro desfechos NÃO se colapsam, e a tela não pode colapsá-los:
 *
 *  · `sucesso`      — a plataforma respondeu e o id externo está carimbado;
 *  · `erro`         — a plataforma respondeu que NÃO criou; reenviar é legítimo;
 *  · `sem_resposta` — ninguém respondeu; NÃO se sabe se criou; reenviar é
 *                     exatamente o que cria a segunda campanha no mesmo leilão;
 *  · `em_voo`       — o recibo ficou aberto (o fechamento não gravou). Também é
 *                     ignorância, e a saída é reconciliar na conta.
 *
 *  `registrado: false` é um quinto estado: o ledger não estava disponível, então
 *  não há recibo nenhum. Ausência de registro nunca deve ser lida como sucesso. */
export interface LedgerDoLancamento {
  registrado: boolean;
  desfecho?: 'sucesso' | 'erro' | 'sem_resposta' | 'em_voo';
  recibo_id?: string | null;
  item_id?: string | null;
  /** O id da campanha na conta. Só existe depois do mutate — é a única fonte. */
  id_externo?: string | null;
  item_estado?: string | null;
  /** Por que não fechou, quando não fechou. Ausente no caminho feliz. */
  motivo?: string;
}

/** Uma operação que a API confirmou ter criado. */
export interface RecursoCriado {
  posicao: number;
  tipo: string;
  resource_name: string;
}

export interface ReciboDeLancamento {
  estado: string;
  carimbo: string;
  customer_id: string;
  login_customer_id: string;
  nome_campanha: string;
  n_operacoes: number;
  impressao: string;
  motivo: string;
  criados: RecursoCriado[];
  request_id: string | null;
  falha: unknown;
  explicacao: string;
  aprovacao?: {
    plano_impressao: string;
    chave_intencao: string;
    aprovado_por_sub: string;
    aprovado_por_email: string;
    confirmou_criacao_pausada: boolean;
    ativacao_incluida: false;
    marca_remota: string;
  };
  ledger?: LedgerDoLancamento;
  /** Preservado por compatibilidade: a gravação legada em `campaigns`. */
  aviso_registro?: string;
}

/** O corpo que `/subir` devolve num 504 quando a resposta do Google se perdeu.
 *
 *  ⚠️ `reenvio_permitido` é `false` e vem do SERVIDOR de propósito: quem decide
 *  se uma nova tentativa é segura é o ledger, que sabe se há recibo em aberto —
 *  não o navegador, que só sabe que uma requisição demorou. */
export interface SubidaIndeterminada {
  estado: 'indeterminado';
  mensagem: string;
  recibo_id: string | null;
  item_id: string | null;
  reenvio_permitido: false;
}

/** O corpo que `/subir` devolve num 502 quando o Google RESPONDEU recusando.
 *
 *  ⚠️ É o oposto de `SubidaIndeterminada`, e a diferença é a coisa toda. Houve
 *  resposta, e o mutate é atômico: nada foi criado na conta. Por isso
 *  `reenvio_permitido` é `true` aqui — corrigir o plano e provar de novo é
 *  seguro, e o item continua reentrável no ledger.
 *
 *  Até 31/08/2026 este corpo não existia: a rota não lia `recibo.estado`, e uma
 *  recusa respondida chegava à tela como 200 dizendo que a campanha existia. */
export interface RecusaDeclarada {
  estado: 'recusado';
  mensagem: string;
  erro_codigo: string | null;
  request_id: string | null;
  recibo_id: string | null;
  item_id: string | null;
  reenvio_permitido: boolean;
}

export interface EstadoDaTrava {
  escrita_permitida: boolean;
  destravado_no_codigo: boolean;
  env_presente: boolean;
  motivo: string;
  explicacao: string;
  canario?: PoliticaDoCanario;
}

// ── o que se envia ──────────────────────────────────────────────────────────

export interface GrupoEscolhido {
  tipo: string;
  keywords: string[];
  /** `null` herda o lance do brief. Preencher só com CPC medido na CONTA —
   *  nunca com o minerado. */
  cpc_inicial?: number | null;
  negativas?: string[];
}

// ── o contrato tipado de keyword ────────────────────────────────────────────

/** Os três match types da API. `BROAD` numa NEGATIVA é o mais largo dos três:
 *  bloqueia toda consulta que contenha os tokens em qualquer ordem. */
export type MatchType = 'EXACT' | 'PHRASE' | 'BROAD';

/** Onde o critério é anexado. Não existe nível de CONTA aqui de propósito: a
 *  negativa de conta atravessa campanhas que este cockpit não criou. */
export type NivelCriterio = 'CAMPAIGN' | 'AD_GROUP';

/** De onde o critério veio — o que separa o medido do imaginado. */
export type OrigemCriterio = 'MANUAL' | 'PAUTADOR' | 'SITE' | 'SEARCH_TERM' | 'LEGADO';

/** `MEDIDO` saiu de um relatório da conta, com janela e números. `HIPOTESE`
 *  saiu de um modelo ou de uma heurística. A tela tem obrigação de mostrar a
 *  diferença — misturar as duas é como um número inventado vira decisão. */
export interface EvidenciaDeCriterio {
  tipo: 'MEDIDO' | 'HIPOTESE';
  fonte: string;
  /** ISO-8601 (AAAA-MM-DD). Obrigatórios quando `tipo === 'MEDIDO'`. */
  janela_inicio?: string | null;
  janela_fim?: string | null;
  metricas?: Record<string, number | string> | null;
}

/**
 * Uma keyword — positiva ou negativa — com tudo o que a define.
 *
 * Substitui o par `string[]` + `match_type` global. Ausência é `null`, nunca
 * valor inventado: um critério sem motivo declarado tem `motivo: null`, não
 * `''` — é assim que se preserva a diferença entre "ninguém escreveu" e
 * "escreveu vazio".
 */
export interface CriterioDeKeyword {
  texto: string;
  match_type: MatchType;
  negativa: boolean;
  nivel: NivelCriterio;
  /** `null` num critério de ad group significa TODOS os grupos. */
  grupo?: string | null;
  origem: OrigemCriterio;
  motivo?: string | null;
  evidencia?: EvidenciaDeCriterio | null;
  observado_em?: string | null;
  aprovado_por?: string | null;
}

// ⚠️ O tipo `CopyDoAnuncio`, com `texto`/`descricao1`/`valores`, foi REMOVIDO.
//
// Ele descrevia os nomes inventados no router, e a cascata de `volc_ads/copy`
// produz `title`/`description1`/`values`. Enquanto os dois existiram, mandar a
// copy gerada para `/provar` entregava sitelink e snippet VAZIOS sem erro
// nenhum — `.get("texto", "")` devolve `""` e o Brief aceita string vazia.
// Um tipo só, com o vocabulário de quem produz: ver `CopyGerada`.

interface PedidoDeProvaBase {
  opportunity_id: number;
  customer_id: string;
  login_customer_id: string;
  run_id?: number | null;
  keywords_fora?: string[];
  /** O que o estágio 3 escreveu, no vocabulário do engine. O backend aceita os
   *  dois nomes por compatibilidade, mas a tela manda um só. */
  copy?: CopyGerada | null;
  budget_diario: number;
  negativas_campanha?: string[];
  negativas_adgroup?: string[];
  /** O contrato TIPADO. Vazio = a tela ainda fala o contrato antigo, e o
   *  backend converte no adaptador da fronteira (`_criterios_do_corpo`). */
  criterios?: CriterioDeKeyword[];
  vertical?: string | null;
  certificacoes?: string[];
  url_final?: string | null;
  prefixo_nome?: string;
  /** Devolvido pela prova; não é preenchido manualmente pelo operador. */
  carimbo_nome?: string | null;
  /** ⚠️ MORTO. Nenhum leitor no engine. Substituído por `meta_conversao_id`,
   *  cujo destino é `campaign.selective_optimization`. Mantido só para não
   *  quebrar chamada antiga. */
  conversao?: string;
  ai_max?: boolean;
}

export type CanalLegadoDeProva = Exclude<CanalComManifesto, 'DEMAND_GEN'>;

export interface PedidoDeProvaSearch extends PedidoDeProvaBase {
  grupos: GrupoEscolhido[];
  cpc_inicial: number;
  /** O match type PADRÃO do pedido. Quem manda `criterios` escolhe um por
   *  keyword; este campo só preenche a lacuna de quem ainda manda `string[]`. */
  match_type: string;
  // ── como a campanha nasce (ver docs/SPEC-FRONT-CAMPANHAS.md) ──────────────
  /**
   * ⚠️ `CanalComManifesto`, e não `Canal`. O inventário pode DEVOLVER Vídeo e
   * Shopping — a conta tem campanhas deles —, mas o Hub não os opera, e um
   * pedido de criação com esses valores seria recusado tarde.
   *
   * Nem todo canal com manifesto sabe criar: a autoridade em runtime é
   * `ManifestoDeCanal.sabe_criar`, e o backend recusa com a lista do que existe.
   */
  canal?: CanalLegadoDeProva;
  estrategia_lance?: EstrategiaDeLance;
  /** Em quantas conversões trocar de estratégia. `0` desliga. O lançamento
   *  REGISTRA a regra; quem executa é o motor de gestão. */
  graduacao_em_conversoes?: number;
  meta_conversao_id?: string | null;
  demand_gen?: never;
  assets_demand_gen?: never;
}

export interface PedidoDeProvaDemandGen extends PedidoDeProvaBase {
  /** Demand Gen não herda a fronteira Search nem seus defaults. */
  canal: 'DEMAND_GEN';
  estrategia_lance: 'MAXIMIZE_CONVERSIONS';
  /** Contrato exclusivo de Demand Gen. Cada lista vazia interna é uma
   *  confirmação explícita de que a superfície não carrega itens nesta prova. */
  demand_gen: ConfiguracaoDemandGen;
  /** Arquivos aprováveis pelo Estúdio. Os bytes chegam ao backend, que mede e
   *  valida pela ponte canônica; o frontend não recalcula geometria. */
  assets_demand_gen: AssetDemandGen[];
  cpc_inicial?: never;
  match_type?: never;
  grupos?: never;
  graduacao_em_conversoes?: never;
}

export type PedidoDeProva = PedidoDeProvaSearch | PedidoDeProvaDemandGen;

/** Onde a mídia é comprada. Uma terceira entra quando houver conta,
 *  credencial e leitura — não quando alguém a mencionar. */
export type Plataforma = 'GOOGLE_ADS' | 'META_ADS';

/**
 * O vocabulário canônico de canal do Google (ADR-18).
 *
 * ⚠️ **`PMAX` saiu daqui.** Ele é apelido de tela e nunca valor de contrato: a
 * string não existe no enum do Google nem no engine, e um pedido com ela
 * falharia no `getattr` — tarde, e com mensagem ruim. Persistir, filtrar ou
 * devolver `PMAX` era um valor que só existia entre nós.
 *
 * O apelido continua sendo ACEITO na entrada, e traduzido numa fronteira só:
 * ver {@link canalCanonico}. Um link antigo com `?canal=PMAX` precisa abrir.
 */
export type Canal =
  | 'SEARCH'
  | 'DISPLAY'
  | 'DEMAND_GEN'
  | 'PERFORMANCE_MAX'
  | 'VIDEO'
  | 'SHOPPING';

export const CANAIS: readonly Canal[] = [
  'SEARCH',
  'DISPLAY',
  'DEMAND_GEN',
  'PERFORMANCE_MAX',
  'VIDEO',
  'SHOPPING',
];

/**
 * Os canais que o Hub sabe **operar** — os que têm manifesto.
 *
 * ⚠️ **São menos que `Canal`, e a assimetria é deliberada.** O inventário
 * espelha honestamente o que a conta responde, e a conta pode ter campanha de
 * Vídeo ou Shopping; escondê-las seria mentir sobre o que está gastando.
 * Ter manifesto é outra coisa: é o Hub declarar hierarquia, painéis e
 * capacidades.
 *
 * A tela deriva CTA de {@link ManifestoDeCanal}, nunca desta lista — ela existe
 * para quem precisa saber, antes de pedir o manifesto, se vale pedir.
 */
export type CanalComManifesto = Extract<
  Canal,
  'SEARCH' | 'DISPLAY' | 'DEMAND_GEN' | 'PERFORMANCE_MAX'
>;

export const CANAIS_COM_MANIFESTO: readonly CanalComManifesto[] = [
  'SEARCH',
  'DISPLAY',
  'DEMAND_GEN',
  'PERFORMANCE_MAX',
];

/**
 * Apelidos de entrada legados. **Não são valores de contrato.**
 *
 * `PMAX` é o que a tela e as URLs antigas escreviam. `DISCOVERY` é o nome
 * anterior de Demand Gen, e a conta ainda pode responder com ele.
 */
export const APELIDOS_DE_CANAL: Readonly<Record<string, Canal>> = {
  PMAX: 'PERFORMANCE_MAX',
  DISCOVERY: 'DEMAND_GEN',
};

/**
 * A fronteira única onde um apelido vira nome canônico.
 *
 * `null` para o que não existe no vocabulário — nunca uma string solta. Deixar
 * passar faria o filtro não casar com nada e a tela dizer "nenhuma campanha"
 * sobre um universo que tem campanha.
 */
export function canalCanonico(bruto: string | null | undefined): Canal | null {
  const alvo = String(bruto ?? '').trim().toUpperCase();
  if (!alvo) return null;
  const traduzido = APELIDOS_DE_CANAL[alvo] ?? (alvo as Canal);
  return CANAIS.includes(traduzido) ? traduzido : null;
}

/**
 * O que um canal pode fazer. São degraus, não sinônimos.
 *
 * Nenhum canal declara `escrever` hoje: nenhuma regra de bidding, graduação ou
 * automação está aprovada (ADR-11).
 */
export type CapacidadeDeAcao = 'ler' | 'propor' | 'escrever';

/**
 * O que o Hub sabe fazer neste canal — declarado, e não suposto.
 *
 * A tela deriva cada ação daqui. Quatro canais na lista não são quatro botões
 * de "criar": existe um único construtor de campanha, e oferecer os outros por
 * simetria visual faz o operador descobrir a ausência depois de montar o pedido
 * inteiro.
 *
 * `indisponibilidades` é a diferença entre um botão cinza sem explicação e uma
 * recusa que ensina.
 */
export interface ManifestoDeCanal {
  plataforma: Plataforma;
  canal: string;
  rotulo: string;
  /** Os degraus da árvore, do topo para baixo. No Meta o segundo é `conjunto`. */
  hierarquia: string[];
  paineis: string[];
  /** Vazio = não há construtor, e não há formulário para desenhar. */
  campos_do_pedido: string[];
  capacidades: CapacidadeDeAcao[];
  provas_obrigatorias: string[];
  indisponibilidades: string[];
  /** Há builder e porta `validate_only`; isto não autoriza criação real. */
  sabe_provar?: boolean;
  /** Há builder, prova e admissão no executor de mutação real. */
  sabe_criar: boolean;
}

export type EstrategiaDeCanaisDemandGen =
  | 'ALL_CHANNELS'
  | 'ALL_OWNED_AND_OPERATED_CHANNELS'
  | 'SELECTED_CHANNELS';

export type CanalSelecionavelDemandGen =
  | 'youtube_in_stream'
  | 'youtube_in_feed'
  | 'youtube_shorts'
  | 'discover'
  | 'gmail'
  | 'display'
  | 'maps';

export interface ControlesDeCanaisDemandGen {
  estrategia: EstrategiaDeCanaisDemandGen;
  /** Só existe no ramo SELECTED_CHANNELS do oneof. `null` é ausência e `[]`
   *  é uma seleção confirmada porém inválida; ambos são recusados no backend. */
  selected_channels: CanalSelecionavelDemandGen[] | null;
}

export interface ConfiguracaoDemandGen {
  /** Imutável na API. `null` não escolhe o default remoto. */
  upgraded_targeting: boolean | null;
  controles_de_canal: ControlesDeCanaisDemandGen | null;
  /** Resource names positivos de Audience já existentes na mesma conta. */
  audiencias: string[] | null;
  /** Intenção é uma superfície própria; a primeira onda recusa itens. */
  intencoes: string[] | null;
  /** Exclusão é uma superfície própria; a primeira onda recusa itens. */
  exclusoes_de_audiencia: string[] | null;
}

export interface ProcedenciaAssetDemandGen {
  motor: string;
  versao_do_motor: string;
  insumo: string;
  quando: string;
  pedido: string;
  custo_usd: number | null;
}

export interface AssetDemandGen {
  tipo:
    | 'imagem_marketing'
    | 'imagem_marketing_quadrada'
    | 'imagem_marketing_retrato'
    | 'imagem_marketing_retrato_alto'
    | 'logo_quadrado';
  nome: string;
  dados_base64: string;
  conteudo_hash: `sha256:${string}`;
  origem: 'gerado' | 'humano' | 'estoque' | 'derivado';
  procedencia: ProcedenciaAssetDemandGen;
}

export type EstrategiaDeLance = 'MANUAL_CPC' | 'MAXIMIZE_CONVERSIONS';

/** O que decorre de escolher uma estratégia — não é opinião da tela, é a
 *  mecânica do leilão. Broad sem Smart Bidding não tem sinal que filtre a
 *  consulta, então nascer em CPC manual implica phrase. */
export const DECORRE_DA_ESTRATEGIA: Record<
  EstrategiaDeLance,
  { match_type: string; explica: string }
> = {
  MANUAL_CPC: {
    match_type: 'PHRASE',
    explica: 'phrase — broad sem lance automático não tem sinal que filtre a consulta',
  },
  MAXIMIZE_CONVERSIONS: {
    match_type: 'PHRASE',
    explica: 'phrase no início; broad só depois que o modelo tiver histórico',
  },
};

// ── o escopo da casa ────────────────────────────────────────────────────────
//
// Medido em 18/08/2026: a credencial alcança 39 contas anunciáveis distintas
// sob 9 MCCs, e três são da VOLC. O resto é de cliente. O portão que recusa as
// outras vive no servidor (`app/trafego/escopo.py`) — estes tipos só carregam
// o que a tela precisa mostrar, e a tela nunca é a única guarda.

/** Uma conta anunciável da casa. `moeda` e `fuso` viajam porque MUDAM o payload
 *  da campanha — vincular projeto BRL a conta USD é erro que só aparece no
 *  orçamento, e em sete países isso passa despercebido. */
export interface ContaDaCasa {
  customer_id: string;
  nome: string;
  moeda: string;
  fuso: string;
  /** Sempre `false` nesta lista: manager administra contas, não recebe campanha. */
  manager: boolean;
  /** ⚠️ Conta de teste NÃO é filtrada: é justamente a que serve ao primeiro
   *  disparo. Ela viaja marcada, para a escolha ser consciente. */
  teste: boolean;
  oculta: boolean;
  /** Distância até o manager: 0 é o próprio MCC, 1 é filha direta. */
  nivel: number;
}

export interface EscopoDeContas {
  mcc: string;
  nome: string;
  contas: ContaDaCasa[];
  ids_acessiveis: number;
  /** Quantos ids a credencial alcança e o sistema recusa. Contado, não
   *  expandido — expandir traria nome de conta de cliente para uma tela onde
   *  ela não pode ser escolhida. */
  ids_fora_do_escopo: number;
  por_que: string;
}

export interface ProjetoComConta {
  id: number;
  dominio: string;
  nome: string;
  google_ads_customer_id: string | null;
  google_ads_manager_id: string | null;
  /** ⚠️ Derivado dos DOIS IDS no servidor, nunca de `google_ads_status` — essa
   *  coluna é do webgo e lá significa "ingestão de gasto ligada". Medido em
   *  18/08/2026, o projeto 1 está 'connected' com os dois ids nulos. */
  vinculada: boolean;
  google_ads_status: string;
}

// ── o estágio 3: a copy ─────────────────────────────────────────────────────
//
// ⚠️ Os nomes são os do ENGINE (`title`, `description1`, `values`), não os do
// router. A cascata de `volc_ads/copy` produz este vocabulário, que é o do
// `PROMPT.md` e o do contrato. Traduzir aqui para português faria a tradução
// morar na tela — e foi exatamente uma divergência dessas que ia entregar
// sitelink vazio a `/provar` sem erro nenhum.

export interface SitelinkGerado {
  title: string;
  description1?: string;
  description2?: string;
}

export interface CopyGerada {
  headlines: string[];
  descriptions: string[];
  long_headlines?: string[];
  business_name?: string;
  sitelinks: SitelinkGerado[];
  callouts: string[];
  snippet?: { header: string; values: string[] } | null;
  /** O que o modelo DECLAROU ancorar em qual fato. O contrato confere contra
   *  isto — é como "C7.fato_inexistente" existe. */
  ancoragem?: Record<string, unknown>;
  auditoria?: Record<string, unknown>;
}

/** Tokens, latência e custo medidos de verdade.
 *
 *  ⚠️ `custo_usd` pode ser `null`, e aí `motivo_sem_custo` diz por quê.
 *  `copy/cliente.py` não inventa preço: um zero ali seria um custo medido que
 *  não foi medido. `sem_custo` conta quantas chamadas ficaram sem preço —
 *  sem ela, US$ 0,0031 sobre 8 chamadas pareceria o custo das oito. */
export interface MedicaoDaCopy {
  chamadas: number;
  falhas: number;
  por_papel: Record<string, number>;
  ilegiveis: number;
  tokens_entrada: number | null;
  tokens_saida: number | null;
  latencia_s: number;
  custo_usd: number | null;
  sem_custo: number;
  motivo_sem_custo: string;
}

/** Uma pendência que a cascata não resolveu.
 *
 *  ⚠️ `classe` separa duas coisas que a tela NÃO pode misturar:
 *
 *  `ancoragem_mentiu`  o modelo errou a própria contabilidade — declarou 30
 *                      caracteres num título de 20. O ANÚNCIO ESTÁ CERTO.
 *  `forma_reescrever`  o anúncio está errado — descrição de 91 caracteres num
 *                      teto de 90, que o Google recusa na prova.
 *
 *  Medido no card 74: 10 pendências, 6 da primeira classe e 4 da segunda. A
 *  tela mostrava as 6 primeiras e escondia exatamente as 4 que barravam. */
export interface PendenciaDaCopy {
  classe: 'ancoragem_mentiu' | 'forma_reescrever' | string;
  codigo: string;
  alvo: string | null;
  detalhe: string;
  texto: string;
}

export interface EscritaDaCopy {
  /** `false` = a cascata esgotou os tetos com achados pendentes. A copy ainda
   *  vem, e os `pendentes` dizem qual asset ficou torto. */
  aceita: boolean;
  copy: CopyGerada;
  pendentes: PendenciaDaCopy[];
  /** O diário da cascata, rodada a rodada. É o que transforma "reprovou" em
   *  "regenerou headline[3] por C7 e o segundo tentativa passou". */
  diario: string[];
  geracoes_conjunto: number;
  geracoes_asset: number;
  fatos_usados: number;
  /** ⚠️ Fatos que o funil trouxe e o `PROMPT.md` não conhece. Medido em
   *  18/08/2026 no card 73: 4 dos 6 têm `tipo: 'afirmacao'`, que não está no
   *  inventário da seção 2. A copy foi escrita SEM eles. */
  fatos_descartados: string[];
  medicao: MedicaoDaCopy;
  segundos: number;
}

/** A copy PERSISTIDA — o que o banco guarda entre uma visita e outra.
 *
 *  ⚠️ Uma geração custa ~174 s de LLM pago (medido no card 73). Antes desta
 *  tabela o resultado vivia só na memória do browser: sair da página descartava,
 *  sem linha, sem log, sem sinal de que tinha rodado. O operador voltava, via o
 *  botão de novo, e os tokens já estavam gastos. */
export interface CopyPersistida extends Omit<EscritaDaCopy, 'copy'> {
  existe: true;
  status: 'running' | 'done' | 'error' | string;
  /** ⚠️ `status === 'running'` NÃO prova que algo está rodando: a tarefa vive
   *  no processo do backend e um reinício a mata, deixando a linha `running`
   *  para sempre. O servidor compara a idade da linha com o teto da rota e
   *  marca aqui — a tela mostra "perdida", não um cronômetro eterno. */
  perdida: boolean;
  opportunity_id: number;
  run_id: number | null;
  /** Os termos para os quais ESTE texto foi escrito. Comparar com a seleção
   *  atual é o que impede mostrar copy ancorada em keyword desmarcada — que
   *  parece perfeitamente válida e só falha no leilão. */
  keywords: string[];
  /** ⚠️ A vertical DECLARADA quando esta copy foi escrita — e é ela que a tela
   *  repõe ao abrir. Antes de existir esta coluna, a escolha vivia num
   *  `useState` e morria no F5: no card 65 o operador marcou `informativo`, deu
   *  refresh, a tela voltou ao inferido `governo_documentos` e a prova reprovou
   *  exigindo certificação. `null` = nunca declarada, e aí vale o inferido. */
  vertical: string | null;
  certificacoes: string[];
  copy: CopyGerada | null;
  erro: string | null;
  criado_em: string | null;
  atualizado_em: string | null;
}

export type RespostaDaCopy = CopyPersistida | { existe: false };

export interface PedidoDeCopy {
  opportunity_id: number;
  run_id?: number | null;
  keywords: string[];
  certificacoes?: string[];
  match_type?: string;
  url_final?: string | null;
  /** A vertical escolhida no portão. A copy precisa ser escrita contra a MESMA
   *  vertical que a prova vai usar, senão o texto sai sob regras de uma e é
   *  julgado pelas de outra. */
  vertical?: string | null;
  /** O modelo. `null` usa o do ambiente. Existe para COMPARAR — não há modelo
   *  medido para copy nesta operação, e eleger um sem medir seria inventar
   *  benchmark. */
  modelo?: string | null;
}

/** Os modelos que a chave desta operação alcança hoje, medido em 19/08/2026
 *  pela API do Google (`models?key=…`). Não há vencedor declarado: a lista
 *  existe para rodar o mesmo card em cada um e comparar. */
export const MODELOS_DE_COPY = [
  { id: '', rotulo: 'do ambiente', nota: 'o que o backend já usa' },
  { id: 'gemini-3.5-flash', rotulo: 'Gemini 3.5 Flash', nota: 'o atual' },
  { id: 'gemini-3.6-flash', rotulo: 'Gemini 3.6 Flash', nota: '' },
  { id: 'gemini-3.7-flash', rotulo: 'Gemini 3.7 Flash', nota: 'o mais novo' },
] as const;


// ── política: o portão de habilitação e o veredito ──────────────────────────
//
// Os dois lados do mesmo assunto. O PORTÃO é o que o nosso engine exige ANTES
// de deixar subir (país × vertical). O VEREDITO é o que o Google decidiu DEPOIS
// de olhar o anúncio — e vale para campanha pausada, o que torna subir pausado
// o teste mais barato de todos.

/** Uma campanha que ESTE funil já produziu.
 *
 *  ⚠️ Sem isto o cockpit oferecia "lançar campanha" mesmo depois de lançar —
 *  ele não tinha como saber, porque o `/subir` não gravava nada. O operador
 *  relançava sem perceber e a conta ganhava duas campanhas para o mesmo termo,
 *  contra a doutrina P7 (um termo, uma campanha). */
export interface CampanhaLancada {
  campaign_id: string;
  campaign_name: string;
  status: string;
  google_ads_status: string;
  customer_id: string;
  budget_amount: number | null;
  created_at: string | null;
}

export interface VerticalDePolitica {
  id: string;
  titulo: string;
  descricao: string;
  /** O que a vertical exige neste país. `null` = sem portão. */
  exige: string | null;
  /** `bloqueio` barra o lançamento; `limitacao` deixa subir com restrição. */
  severidade: 'bloqueio' | 'limitacao' | null;
  url?: string;
  paises_exigem: string[];
}

export interface TopicoDePolitica {
  topico: string;
  tipo: string;
  /** Separa "peça isenção" de "reescreva o anúncio". */
  isentavel: boolean;
}

export interface AnuncioJulgado {
  ad_id: string;
  ad_group: string;
  status: string;
  /** APPROVED | APPROVED_LIMITED | DISAPPROVED | AREA_OF_INTEREST_ONLY */
  aprovacao: string;
  /** REVIEWED | REVIEW_IN_PROGRESS | UNDER_REVIEW | ELIGIBLE_MAY_SERVE */
  revisao: string;
  topicos: TopicoDePolitica[];
}

export interface VereditoDePolitica {
  campanha: { id: string; nome: string; status: string };
  anuncios: AnuncioJulgado[];
  /** Todos ainda em revisão — a tela não pode chamar isso de aprovado. */
  em_revisao: boolean;
  sem_anuncios: boolean;
}

/**
 * Uma campanha ligada que não gastou — o que o alerta mostra.
 *
 * ⚠️ Todo campo aqui é FATO DA CONTA. Não há nada derivado de estimativa de
 * terceiro: comparar o lance com o CPC do DataForSEO daria uma frase forte
 * ("R$ 0,12 contra mediana de R$ 10,54") e um alerta que mente no dia em que a
 * estimativa inflar. `tetoDeCliques` é a única conta, e é orçamento ÷ lance —
 * divisão de dois números da própria conta.
 */
export interface AlteracaoDeCampanha {
  quando: string;
  campo: string;
  de: string;
  para: string;
  /** `GOOGLE_ADS_WEB_CLIENT` (painel) ou `GOOGLE_ADS_API` (nosso motor). */
  /** `null` quando a mudança veio de fora do VOLC e não há recibo de quem. */
  origem: string | null;
  /** `null` pelo mesmo motivo de `origem`: sem recibo, não há a quem atribuir. */
  quem: string | null;
  resumo: string;
}

export interface AlertaDeEntrega {
  /**
   * De quando é esta afirmação. Regra A: um alerta é uma medida como qualquer
   * outra, e "esta campanha não gastou" só significa algo com a data ao lado.
   * `null` quando a campanha ainda não tem leitura no snapshot.
   */
  leitura?: Leitura | null;
  /** O estado de presença observado — o alerta some quando ela é removida. */
  presenca?: EstadoDePresenca;
  /** Identidade interna, para o foco do sino casar com a linha do inventário. */
  volc_campaign_id?: string;
  /** A conta vem colada ao alerta: usar a primeira conta do quadro associa o
   * link errado assim que duas contas tiverem uma condição ativa. */
  customer_id: string;
  customer_name: string;
  campaign_id: string;
  campaign_name: string;
  status: string;
  veiculacao: string;
  /** `null` quando não deu para saber — e aí não há alerta. */
  horas_ligada: number | null;
  impressoes: number;
  cliques: number;
  custo: number;
  lance: number | null;
  orcamento: number | null;
  teto_de_cliques: number | null;
  /** O texto do Google, como ele escreveu. Vazio = nenhuma observação. */
  razoes: string[];
  /**
   * ⚠️ `null` desde a Fase 1B. Este campo é o texto do Google, e só uma
   * consulta à conta o traz — que é exatamente o custo que saiu do caminho de
   * render. Dizer "não sei" é honesto; inventar uma aprovação a partir do
   * espelho seria afirmar sobre a política do Google sem tê-la lido.
   */
  aprovacao_do_anuncio: string | null;
  /** `sem_impressao` (nem entrou no leilão) ou `sem_clique` (entrou e ninguém clicou). */
  sintoma: 'sem_impressao' | 'sem_clique';
  revisar: string[];
  alteracoes: AlteracaoDeCampanha[];
}

export interface QuadroDeAlertas {
  alertas: AlertaDeEntrega[];
  verificadas: number;
  contas?: { customer_id: string; nome: string; ligadas?: number; erro?: string }[];
  horas_ate_alertar: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// INVENTÁRIO OPERACIONAL — Fase 1B
//
// O contrato de `GET /api/trafego/inventario`. Ele responde uma pergunta só:
// "o que existe nas minhas contas, em que estado está, e quão recente é essa
// informação?"
//
// Três decisões atravessam tudo aqui:
//
// 1. NENHUM NÚMERO SEM FRESCOR. Toda medida vem acompanhada de quando foi
//    lida. Um custo sem data é indistinguível de um custo de ontem, e o
//    operador decide gasto olhando para ele.
//
// 2. AUSÊNCIA É `null`, NUNCA ZERO. Falha ao ler impressões produz `null`,
//    que a interface mostra como "—". Zero é um fato: significa que a
//    campanha não apareceu. Trocar um pelo outro inventa um resultado.
//
// 3. FALHA DE UMA CONTA NÃO CONTAMINA AS OUTRAS. A resposta é `parcial` e
//    lista o que faltou, com o último dado bom preservado.
// ═══════════════════════════════════════════════════════════════════════════

/** Versão do contrato. Muda quando um consumidor precisa ser avisado. */
/**
 * Versão do contrato de leitura comum.
 *
 * **v2 (U0, 26/08/2026).** Três mudanças que um cliente v1 não sobrevive em
 * silêncio: o padrão passa a excluir histórico removido; `totais` troca
 * `campanhas` por `operacionais`/`historicas`/`geral`; e o cursor passa a
 * carregar o degrau de ordenação — um cursor v1 colado numa chamada v2 é
 * RECUSADO com mensagem, nunca reinterpretado.
 */
export const VERSAO_INVENTARIO = 2 as const;

/**
 * O que a interface sabe sobre a existência de uma campanha.
 *
 * Vocabulário fechado e deliberadamente factual: cada termo nomeia o que foi
 * OBSERVADO, não uma inferência sobre o que aconteceu. Por isso não existe
 * "sumiu da conta" — some é conclusão, e a conclusão pode estar errada quando
 * a causa real foi uma leitura que falhou.
 */
export type EstadoDePresenca =
  /**
   * A conta respondeu, a leitura foi boa, e a campanha estava lá.
   *
   * ⚠️ ESTE VALOR FOI ACRESCENTADO DEPOIS DE O CONTRATO SER CONGELADO, porque a
   * integração provou uma contradição objetiva: os seis estados originais
   * nomeiam apenas EXCEÇÕES, e nenhum deles nomeia o caso normal. Como
   * `CampanhaNoInventario.presenca` é não-nulo, toda campanha saudável ficava
   * sem valor legal — o backend teria de mentir escolhendo uma exceção, ou o
   * campo teria de virar opcional, e aí "sem presença" e "presente" ficariam
   * indistinguíveis.
   *
   * As duas frentes chegaram nisso de forma independente (banco e frontend), e
   * `backend/app/trafego/inventario.py:91` já emitia a constante. Preferi
   * nomear o caso normal a deixar o tipo desmentir o código.
   */
  | 'presente'
  /** A conta respondeu e a campanha está lá, marcada como removida. */
  | 'removida'
  /** A conta respondeu, a leitura foi boa, e a campanha não estava na resposta. */
  | 'nao_encontrada'
  /** A linha existe no nosso banco sem `customer_id` utilizável. */
  | 'conta_nao_identificada'
  /** A conta existe, mas não pertence ao MCC da casa. */
  | 'fora_de_escopo'
  /** A leitura da conta falhou; não dá para afirmar presença nem ausência. */
  | 'sincronizacao_falhou'
  /** Linha histórica sem conta, anterior ao inventário. Visível, não ausente. */
  | 'legado_nao_reconciliado';

/**
 * Quão recente é o que está na tela.
 *
 * `nunca_lido` e `vazio_confirmado` são fatos DIFERENTES e a interface não
 * pode achatá-los: "não perguntei" e "perguntei e não há nada" levam a ações
 * opostas.
 */
export type Frescor =
  | 'recente'
  | 'velho'
  | 'parcial'
  | 'falhou'
  | 'nunca_lido'
  | 'vazio_confirmado';

/** Como a campanha veio parar no nosso banco. */
export type Procedencia =
  /** Nasceu pelo VOLC O.S., com recibo. */
  | 'volc_os'
  /** Encontrada na conta durante uma leitura; não foi criada aqui. */
  | 'descoberta'
  /** Veio do sistema legado, sem recibo de origem. */
  | 'legado'
  /** Não sabemos, e dizer isso é melhor que escolher um palpite. */
  | 'desconhecida';

/** Um instante medido, sempre acompanhado do que ele descreve. */
export interface Leitura {
  /** ISO 8601 em UTC. Nunca ausente quando há número. */
  lido_em: string;
  /** Idade em segundos no momento da resposta — poupa a conta no cliente. */
  idade_s: number;
}

/**
 * Uma medida de entrega.
 *
 * `null` significa "não foi possível medir". Zero significa zero medido. A
 * interface renderiza os dois de formas diferentes ("—" e "0"), e o backend
 * jamais converte um no outro.
 */
export interface Entrega {
  impressoes: number | null;
  cliques: number | null;
  /** Micros da moeda da conta, para não perder centavo em ponto flutuante. */
  custo_micros: number | null;
  moeda: string | null;
  /** De quando é esta medida. Sem isto, o número não sai do backend. */
  leitura: Leitura | null;
}

/** Identidade externa. `customer_id` vazio é inválido e nunca chega aqui. */
export interface IdentidadeExterna {
  customer_id: string;
  campaign_id: string;
}

/** Vínculo com o funil, auditável e reversível. */
export interface VinculoDeFunil {
  opportunity_id: number | null;
  project_id: number | null;
  /** Quem confirmou. Vínculo sem confirmação humana não existe. */
  confirmado_por: string | null;
  confirmado_em: string | null;
}

/** Uma campanha, como o inventário a conhece. */
export interface CampanhaNoInventario {
  /** 1:1 com uma campanha externa, imutável. */
  volc_campaign_id: string;
  /** Agrupa instâncias da mesma intenção ao longo do tempo. */
  campaign_lineage_id: string | null;
  externa: IdentidadeExterna;

  nome: string;
  /** Estado do lado do Google, sem tradução: ENABLED, PAUSED, REMOVED. */
  estado_externo: string | null;
  /** Se está efetivamente entregando, quando a conta informa. */
  veiculacao: string | null;
  canal: Canal | null;
  estrategia: EstrategiaDeLance | null;
  /** Micros. `null` quando a conta não informou. */
  lance_micros: number | null;
  verba_diaria_micros: number | null;
  /**
   * Teto de cliques por dia = verba ÷ lance. Só quando os DOIS existem e o
   * lance é manual — com lance automático o número seria ficção.
   */
  teto_de_cliques: number | null;

  entrega: Entrega;
  vinculo: VinculoDeFunil | null;
  procedencia: Procedencia;
  presenca: EstadoDePresenca;

  /** Rota do cockpit existente, só quando o mapeamento é seguro. */
  cockpit_href: string | null;
}

/** Um grupo do inventário: uma conta e o que ela respondeu. */
export interface ContaNoInventario {
  customer_id: string;
  nome: string | null;
  /** Resultado da última tentativa de leitura. */
  frescor: Frescor;
  /** Quando esta leitura aconteceu. `null` se nunca houve. */
  leitura: Leitura | null;
  /** A última leitura BOA, que pode ser mais antiga que a última tentativa. */
  ultima_leitura_boa: Leitura | null;
  /** Motivo, já em linguagem de operação, quando algo deu errado. */
  motivo: string | null;
  /** Quantas campanhas o grupo tem depois dos filtros. */
  quantidade: number;
  campanhas: CampanhaNoInventario[];
}

/** O que não deu para ler nesta resposta. Nunca vira lista vazia por omissão. */
export interface Faltou {
  customer_id: string | null;
  escopo: string;
  motivo: string;
}

/** Filtros combináveis. Todos opcionais; ausência = não filtra. */
export interface FiltrosDoInventario {
  /**
   * Texto livre: casa com o nome da campanha OU com o id externo dela.
   *
   * Resolvido NO SERVIDOR, sobre o universo — nunca na página carregada.
   * Buscar só no que já veio seria pior que não buscar: a tela diria "nenhum
   * resultado" sobre um universo que tem o resultado, e o operador concluiria
   * que a campanha não existe. Com 84 campanhas em 3 contas e a primeira
   * página consumida por uma delas, essa mentira seria o caso comum.
   */
  busca?: string;
  conta?: string[];
  projeto?: number[];
  canal?: Canal[];
  estado_externo?: string[];
  presenca?: EstadoDePresenca[];
  frescor?: Frescor[];
  procedencia?: Procedencia[];
  /** `true` = só o que pede atenção. */
  atencao?: boolean;
  /** `false` = só sem vínculo de funil. */
  vinculado?: boolean;
  /**
   * Inclui o histórico removido na listagem. **O padrão do servidor é
   * `false`.**
   *
   * Das 84 campanhas das contas da casa, 79 estão `REMOVED` — 94% de história.
   * O histórico continua no banco e continua consultável; ele deixou de ser o
   * que a tela mostra quando ninguém pediu nada.
   *
   * Filtrar explicitamente por `estado_externo: ['REMOVED']` ou
   * `presenca: ['removida']` também liga o histórico: pedir exatamente o que o
   * padrão esconde e receber lista vazia seria mentira.
   */
  incluir_historico?: boolean;
}

/**
 * A página canônica de UMA campanha — `GET /api/trafego/campanhas/{id}`.
 *
 * ⚠️ **Só a identidade INTERNA endereça.** O id externo do Google não é único
 * no VOLC O.S.: ele é único dentro de uma conta, e a identidade externa é uma
 * trinca (plataforma, conta, id). Uma rota que aceitasse o id externo teria de
 * adivinhar as outras duas pontas — e adivinhar errado leva o operador à
 * campanha de outro cliente com a URL certa na barra de endereço.
 */
export interface CampanhaCanonica {
  versao: typeof VERSAO_INVENTARIO;
  /** A mesma projeção que a listagem devolve. Não é uma segunda forma. */
  campanha: CampanhaNoInventario;
  identidade: {
    volc_campaign_id: string;
    campaign_lineage_id: string | null;
    plataforma: Plataforma;
    /** `null` quando ainda não se sabe em que conta ela vive. */
    conta_externa: string | null;
    id_externo: string;
  };
  conta: {
    customer_id: string | null;
    /** O frescor da CONTA — é ele que carimba os números da campanha. */
    frescor: Frescor;
    tentativa_resultado: string | null;
  };
  /**
   * O que o Hub sabe fazer neste canal. A tela deriva daqui o que oferecer.
   *
   * `null` quando o canal não tem manifesto — Vídeo e Shopping aparecem no
   * inventário e o Hub não os opera. Nulo diz isso; um manifesto vazio diria
   * "não pode nada", que é outra afirmação.
   */
  manifesto: ManifestoDeCanal | null;
}

/** Envelope da resposta. */
export interface Inventario {
  versao: typeof VERSAO_INVENTARIO;
  /** Frescor do conjunto: o pior entre as contas. */
  frescor: Frescor;
  leitura: Leitura | null;
  /** `true` quando ao menos uma conta não pôde ser lida. */
  parcial: boolean;
  faltou: Faltou[];
  contas: ContaNoInventario[];
  /** Cursor opaco. `null` = acabou. Nunca offset: a lista muda entre páginas. */
  proximo_cursor: string | null;
  totais: {
    contas: number;
    /**
     * Campanhas que existem na operação: tudo que NÃO é histórico removido.
     * É este o número do rótulo da aba Campanhas.
     */
    operacionais: number;
    /** Campanhas que a conta declara removidas, sob os mesmos filtros. */
    historicas: number;
    /**
     * `operacionais + historicas`, sob os mesmos filtros do operador.
     *
     * ⚠️ Não é o universo do banco. Com `busca: 'FGTS'`, `geral` é quantas
     * campanhas de FGTS existem contando história — não 84.
     */
    geral: number;
    /** Campanhas em alguma condição que pede atenção. */
    atencao: number;
  };
}
