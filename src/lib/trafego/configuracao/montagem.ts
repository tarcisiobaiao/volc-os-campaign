/**
 * Formulário → pedido. O ÚNICO lugar onde o texto da tela vira contrato.
 *
 * ## As três regras desta conversão
 *
 * 1. **Vazio é ausência, nunca zero.** Campo numérico em branco não entra no
 *    objeto; texto que não é número também não — e a falta aparece na parada
 *    (`faltasDosCanais`), em vez de um `0` que ninguém digitou chegar ao Google.
 * 2. **Decisão obrigatória não tem default.** `null` (ninguém escolheu) não
 *    vira `false`: a chave fica de fora, o esquema acusa "campo obrigatório" no
 *    campo, e o servidor recusaria igual. Rede e as três automações do AI Max
 *    são assim.
 * 3. **Cada número vai para o campo que ele É.** O defeito que esta camada
 *    fecha: na Mesa de Lance, sob Maximizar conversões, o campo se chamava
 *    "CPA alvo" e era enviado como `cpc_inicial` — o operador declarava um tCPA
 *    e o Google recebia um lance de grupo que a estratégia ignora. Agora tCPA é
 *    `configuracao_search.lance.target_cpa`, e `cpc_inicial` só viaja em
 *    CPC manual, quando ele é de fato o lance.
 */
import { chave } from '@/lib/trafego/criterios';
import type {
  AssetDemandGen, CopyGerada, CriterioDeKeyword, ParadaDaBancada, PedidoDeProvaDemandGen,
  PedidoDeProvaDisplay, PedidoDeProvaPMax, PedidoDeProvaSearch, RevisaoDoConjuntoPago,
  ConfiguracaoDemandGen,
} from '@/types/trafego';
import {
  AUTOMACOES_DEMAND_GEN_POR_FORMATO,
} from '@/types/trafegoCanais';
import type {
  ConfiguracaoDemandGenV25, ConfiguracaoDisplay, ConfiguracaoPMaxV25, ConfiguracaoSearch,
  EstrategiaDemandGen, EstrategiaSearch, JanelaDeVeiculacao, LanceSearch, MatchPorKeyword,
  OpcoesDeUrl, SinalDeAudiencia,
} from '@/types/trafegoCanais';
import type {
  FormDemandGen, FormDisplay, FormLanceSearch, FormOpcoesDeUrl, FormPMax, FormSearch,
  LinhaDeFaixa,
} from './formularios';

// ═══════════════════════════════════════════════════════════════════════════
// Leitura de texto
// ═══════════════════════════════════════════════════════════════════════════

/** Um número digitado (vírgula aceita), ou `null`. Nunca `Number(x) || 0`. */
export function numeroDoTexto(bruto: string | null | undefined): number | null {
  const limpo = String(bruto ?? '').trim().replace(/\s/g, '').replace(',', '.');
  if (limpo === '') return null;
  const n = Number(limpo);
  return Number.isFinite(n) ? n : null;
}

/** Texto preenchido que NÃO é número — a falta que impede o pedido. */
export function numeroInvalido(bruto: string | null | undefined): boolean {
  return String(bruto ?? '').trim() !== '' && numeroDoTexto(bruto) == null;
}

/** Porcentagem digitada → razão (`400` → `4`, `60` → `0.6`). */
export function razaoDaPorcentagem(bruto: string): number | null {
  const n = numeroDoTexto(bruto);
  return n == null ? null : Number((n / 100).toFixed(6));
}

/** Uma linha por item; vazias somem. */
export function linhas(texto: string | null | undefined): string[] {
  return String(texto ?? '').split('\n').map((s) => s.trim()).filter(Boolean);
}

/** Inteiros separados por linha, vírgula ou espaço. Texto não numérico vira
 *  `NaN` DE PROPÓSITO: o esquema o recusa no campo, em vez de sumir. */
export function inteiros(texto: string): number[] {
  return String(texto ?? '').split(/[\s,;]+/).filter(Boolean).map((t) => (/^\d+$/.test(t) ? Number(t) : Number.NaN));
}

/** `chave=valor`, uma por linha → `[chave, valor]`. */
export function pares(texto: string): [string, string][] {
  return linhas(texto).map((l) => {
    const i = l.indexOf('=');
    return i < 0 ? [l, ''] : [l.slice(0, i).trim(), l.slice(i + 1).trim()];
  });
}

function seTiver<T>(lista: T[]): T[] | undefined {
  return lista.length > 0 ? lista : undefined;
}

/** Remove chaves `undefined` — o JSON já as descartaria, mas o teste e a
 *  impressão aprovável leem o objeto, e ele tem que ser o que vai. */
function limpo<T extends object>(o: T): T {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as T;
}

export interface BaseDoPedido {
  opportunity_id: number;
  run_id: number | null;
  customer_id: string;
  login_customer_id: string;
  budget_diario: number;
  vertical?: string | null;
  certificacoes: string[];
  url_final?: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// Search
// ═══════════════════════════════════════════════════════════════════════════

/** BROAD só com lance por CONVERSÃO (contrato §3; o `Brief` recusa sob CPC). */
export function lancePorConversao(e: string): boolean {
  return e === 'MAXIMIZE_CONVERSIONS' || e === 'MAXIMIZE_CONVERSION_VALUE';
}

/** O match type PADRÃO do pedido. Sob qualquer estratégia o nascimento é
 *  PHRASE; BROAD por keyword entra por `match_por_keyword`. */
export function matchPadraoDaEstrategia(_e: string): 'PHRASE' {
  return 'PHRASE';
}

export function lanceSearch(form: FormLanceSearch, estrategia: EstrategiaSearch): LanceSearch {
  const l: LanceSearch = { estrategia };
  const tcpa = numeroDoTexto(form.tcpa);
  const roas = razaoDaPorcentagem(form.troasPct);
  const teto = numeroDoTexto(form.tetoCpc);
  const fracao = razaoDaPorcentagem(form.fracaoPct);
  switch (estrategia) {
    case 'MAXIMIZE_CONVERSIONS':
      if (tcpa != null) l.target_cpa = tcpa;
      break;
    case 'MAXIMIZE_CONVERSION_VALUE':
      if (roas != null) l.target_roas = roas;
      break;
    case 'TARGET_SPEND':
      if (teto != null) l.teto_cpc = teto;
      break;
    case 'TARGET_IMPRESSION_SHARE':
      if (form.local) l.local_impressao = form.local;
      if (fracao != null) l.fracao_impressao = fracao;
      if (teto != null) l.teto_cpc = teto;
      break;
    default:
      break;
  }
  return l;
}

function faixasHHMM(agenda: LinhaDeFaixa[], comAjuste: boolean) {
  return agenda.map((f) => {
    const ajuste = comAjuste ? numeroDoTexto(f.ajuste) : null;
    return limpo({ dia: f.dia, inicio: f.inicio, fim: f.fim, ajuste: ajuste ?? undefined });
  });
}

export function configuracaoSearch(form: FormSearch, estrategia: EstrategiaSearch): ConfiguracaoSearch {
  const c: ConfiguracaoSearch = { lance: lanceSearch(form.lance, estrategia) };

  if (form.parceiros != null && form.expansaoDisplay != null) {
    c.rede = { google_search: true, parceiros: form.parceiros, display_expansion: form.expansaoDisplay };
  }

  if (form.aiMax) {
    c.ai_max = limpo({
      correspondencia_de_termos: form.aiCorrespondencia ?? undefined,
      personalizacao_de_texto: form.aiPersonalizacao ?? undefined,
      expansao_de_url_final: form.aiExpansaoUrl ?? undefined,
      grupos_sem_correspondencia: seTiver(linhas(form.aiGruposSemCorrespondencia)),
      exclusoes_de_url: seTiver(linhas(form.aiExclusoesDeUrl)),
      listas_de_marca_incluidas: seTiver(linhas(form.aiListasIncluidas)),
      listas_de_marca_excluidas: seTiver(linhas(form.aiListasExcluidas)),
      termos_excluidos: seTiver(linhas(form.aiTermosExcluidos)),
      restricoes_de_mensagem: seTiver(linhas(form.aiRestricoes)),
    }) as ConfiguracaoSearch['ai_max'];
  }

  const fixacoes = form.fixacoes.filter((f) => f.texto.trim());
  if (form.path1.trim() || form.path2.trim() || fixacoes.length) {
    c.anuncio = limpo({
      path1: form.path1.trim() || undefined,
      path2: form.path2.trim() || undefined,
      fixacoes: seTiver(fixacoes.map((f) => ({ texto: f.texto, posicao: f.posicao }))),
    });
  }

  if (form.programacao.length) c.programacao = faixasHHMM(form.programacao, true);
  if (form.dispositivos.length) {
    c.dispositivos = form.dispositivos.map((d) => ({
      dispositivo: d.dispositivo, fator: numeroDoTexto(d.fator) as number,
    }));
  }

  if (form.geo) {
    c.geo = limpo({
      tipo_positivo: form.geoPositivo,
      tipo_negativo: form.geoNegativo,
      locais: seTiver(inteiros(form.geoLocais)),
      locais_excluidos: seTiver(inteiros(form.geoLocaisExcluidos)),
      idiomas: seTiver(linhas(form.geoIdiomas.replace(/[,;]/g, '\n'))),
    });
  }

  if (form.inicio.trim()) c.inicio = form.inicio.trim();
  if (form.fim.trim()) c.fim = form.fim.trim();

  if (form.metaModo === 'personalizada') {
    c.meta_de_conversao = { meta_personalizada: form.metaPersonalizada.trim() };
  } else if (form.metaModo === 'acoes') {
    c.meta_de_conversao = limpo({
      acoes_de_conversao: seTiver(linhas(form.metaAcoes)),
      categorias: seTiver(form.metaCategorias.map((m) => ({
        categoria: m.categoria, origem: m.origem, lance: m.lance,
      }))),
    });
  }
  return c;
}

/**
 * A correspondência por keyword que vai no pedido (contrato §4).
 *
 * Só keyword do conjunto APROVADO, e só quando a escolha DIFERE do que foi
 * aprovado: `{}` é ausência, e trocar e destrocar não pode deixar uma
 * "troca" fantasma na impressão do plano. Chave = `chave()`, a mesma dos dois
 * lados. Uma escolha guardada para keyword que saiu do conjunto não viaja: o
 * servidor a recusaria com `MATCH_FORA_DO_CONJUNTO`, e ela é resto de rascunho,
 * não decisão sobre este conjunto.
 */
export function matchPorKeywordDoPedido(
  escolhas: Record<string, string>, conjunto: RevisaoDoConjuntoPago | null,
): MatchPorKeyword {
  const saida: MatchPorKeyword = {};
  if (!conjunto) return saida;
  for (const k of conjunto.selecionadas) {
    const ch = chave(k.termo);
    const escolhido = escolhas[ch];
    if ((escolhido === 'EXACT' || escolhido === 'PHRASE' || escolhido === 'BROAD')
        && escolhido !== k.match_type) {
      saida[ch] = escolhido;
    }
  }
  return saida;
}

export interface EntradaDoPedidoSearch {
  base: BaseDoPedido;
  copy: CopyGerada | null;
  negativas: CriterioDeKeyword[];
  keywordsFora: string[];
  estrategia: EstrategiaSearch;
  /** O lance por clique digitado. Só viaja em MANUAL_CPC. */
  cpcManual: number | null;
  graduacao: number;
  metaConversaoId: string | null;
  form: FormSearch;
  matchEscolhido: Record<string, string>;
  conjunto: RevisaoDoConjuntoPago | null;
}

export function montarPedidoSearch(e: EntradaDoPedidoSearch): PedidoDeProvaSearch {
  const manual = e.estrategia === 'MANUAL_CPC';
  const configuracao = configuracaoSearch(e.form, e.estrategia);
  const match = matchPorKeywordDoPedido(e.matchEscolhido, e.conjunto);
  return limpo({
    opportunity_id: e.base.opportunity_id,
    run_id: e.base.run_id,
    customer_id: e.base.customer_id,
    login_customer_id: e.base.login_customer_id,
    // ⚠️ Vazio de propósito: as positivas vêm do conjunto aprovado, no servidor.
    grupos: [],
    copy: e.copy,
    budget_diario: e.base.budget_diario,
    // ⚠️ SÓ EM CPC MANUAL. Fora dele, o número digitado é tCPA/teto/tROAS e
    // mora em `configuracao_search.lance` — nunca aqui.
    cpc_inicial: manual && e.cpcManual != null ? e.cpcManual : undefined,
    rede: configuracao.rede
      ? {
        google_search: true,
        search_partners: configuracao.rede.parceiros,
        display_expansion: configuracao.rede.display_expansion,
      }
      : undefined,
    match_type: matchPadraoDaEstrategia(e.estrategia),
    criterios: e.negativas,
    keywords_fora: e.keywordsFora,
    canal: 'SEARCH' as const,
    // As DUAS iguais: com a configuração declarada o motor recusa divergência.
    estrategia_lance: e.estrategia,
    graduacao_em_conversoes: manual ? e.graduacao : 0,
    meta_conversao_id: e.metaConversaoId,
    vertical: e.base.vertical,
    certificacoes: e.base.certificacoes,
    url_final: e.base.url_final,
    configuracao_search: configuracao,
    match_por_keyword: Object.keys(match).length ? match : undefined,
  }) as PedidoDeProvaSearch;
}

// ═══════════════════════════════════════════════════════════════════════════
// Display
// ═══════════════════════════════════════════════════════════════════════════

function janelaDeHHMM(f: LinhaDeFaixa): JanelaDeVeiculacao {
  const [hi, mi] = f.inicio.split(':').map((x) => Number(x));
  const [hf, mf] = f.fim.split(':').map((x) => Number(x));
  return limpo({
    dia: f.dia,
    inicio_hora: hi,
    fim_hora: hf,
    inicio_minuto: mi ? (mi as JanelaDeVeiculacao['inicio_minuto']) : undefined,
    fim_minuto: mf ? (mf as JanelaDeVeiculacao['fim_minuto']) : undefined,
  });
}

/**
 * ⚠️ Objeto presente = DOUTRINA DE NASCIMENTO (contrato §3): mesmo vazio, ele
 * liga as exclusões padrão. A Bancada sempre o manda, com as exclusões que o
 * formulário mostra já marcadas — o que o operador vê é o que vai.
 */
export function configuracaoDisplay(form: FormDisplay, videosYoutube: string): ConfiguracaoDisplay {
  const teto = numeroDoTexto(form.tetoCpc);
  const cpm = numeroDoTexto(form.cpm);
  const lance = limpo({
    estrategia: form.estrategia,
    teto_cpc: form.estrategia === 'TARGET_SPEND' && teto != null ? teto : undefined,
    cpm_visivel: form.estrategia === 'MANUAL_CPM' && cpm != null ? cpm : undefined,
  });
  const listaNova = form.listaNovaNome.trim() || form.listaNovaPlacements.trim()
    || form.listaNovaApps.trim() || form.listaNovaCategorias.trim()
    ? limpo({
      nome: form.listaNovaNome.trim(),
      placements: seTiver(linhas(form.listaNovaPlacements)),
      apps: seTiver(linhas(form.listaNovaApps)),
      categorias_de_app: seTiver(linhas(form.listaNovaCategorias)),
    })
    : undefined;
  return limpo({
    lance,
    segmentacao: limpo({
      listas_de_usuarios: seTiver(linhas(form.segListasDeUsuarios)),
      publicos_personalizados: seTiver(linhas(form.segPublicosPersonalizados)),
      publicos_combinados: seTiver(linhas(form.segPublicosCombinados)),
      interesses: seTiver(linhas(form.segInteresses)),
      topicos: seTiver(linhas(form.segTopicos)),
      placements: seTiver(linhas(form.segPlacements)),
      palavras_chave: seTiver(linhas(form.segPalavrasChave)),
      publicos_em_observacao: form.segObservacao,
      segmentacao_otimizada: form.segOtimizada,
    }),
    exclusoes: limpo({
      placements: seTiver(linhas(form.excPlacements)),
      apps: seTiver(linhas(form.excApps)),
      categorias_de_app: seTiver(linhas(form.excCategoriasDeApp)),
      excluir_todos_os_apps: form.excTodosOsApps,
      rotulos_de_conteudo: [...form.excRotulos],
      topicos: seTiver(linhas(form.excTopicos)),
      listas_existentes: seTiver(linhas(form.excListasExistentes)),
      lista_nova: listaNova,
    }),
    frequencia: seTiver(form.frequencia.map((f) => ({
      impressoes: numeroDoTexto(f.impressoes) as number, unidade: f.unidade, nivel: f.nivel,
    }))),
    agenda: seTiver(form.agenda.map(janelaDeHHMM)),
    dispositivos_excluidos: seTiver([...form.dispositivosExcluidos]),
    presenca_geo: form.presenca,
    anuncio: limpo({
      chamada_para_acao: form.rdaCta.trim() || undefined,
      cor_principal: form.rdaCorPrincipal.trim() || undefined,
      cor_destaque: form.rdaCorDestaque.trim() || undefined,
      cores_flexiveis: form.rdaCoresFlexiveis,
      formato: form.rdaFormato,
      videos_youtube: seTiver(linhas(videosYoutube)),
      melhorias_de_asset: form.rdaMelhorias,
      video_automatico: form.rdaVideoAutomatico,
    }),
  });
}

export interface EntradaDoPedidoDisplay {
  base: BaseDoPedido;
  copy: CopyGerada;
  assets: AssetDemandGen[];
  form: FormDisplay;
  videosYoutube: string;
}

export function montarPedidoDisplay(e: EntradaDoPedidoDisplay): PedidoDeProvaDisplay {
  const f = e.form;
  const tcpa = numeroDoTexto(f.tcpa);
  const roas = razaoDaPorcentagem(f.troasPct);
  const cpc = numeroDoTexto(f.cpcManual);
  return limpo({
    opportunity_id: e.base.opportunity_id,
    run_id: e.base.run_id,
    customer_id: e.base.customer_id,
    login_customer_id: e.base.login_customer_id,
    copy: e.copy,
    budget_diario: e.base.budget_diario,
    canal: 'DISPLAY' as const,
    // O envelope diz a MESMA estratégia da configuração (o motor recusa duas).
    estrategia_lance: f.estrategia as PedidoDeProvaDisplay['estrategia_lance'],
    assets_display: e.assets,
    tcpa: f.estrategia === 'MAXIMIZE_CONVERSIONS' && tcpa != null ? tcpa : undefined,
    target_roas: f.estrategia === 'MAXIMIZE_CONVERSION_VALUE' && roas != null ? roas : undefined,
    // ⚠️ Só em MANUAL_CPC, e lá é OBRIGATÓRIO: é o lance do grupo.
    cpc_inicial: f.estrategia === 'MANUAL_CPC' && cpc != null ? cpc : undefined,
    vertical: e.base.vertical,
    certificacoes: e.base.certificacoes,
    url_final: e.base.url_final,
    configuracao_display: configuracaoDisplay(f, e.videosYoutube),
  }) as PedidoDeProvaDisplay;
}

// ═══════════════════════════════════════════════════════════════════════════
// Demand Gen
// ═══════════════════════════════════════════════════════════════════════════

export function configuracaoDemandGen(form: FormDemandGen): ConfiguracaoDemandGenV25 {
  const tcpa = numeroDoTexto(form.tcpa);
  const roas = razaoDaPorcentagem(form.troasPct);
  const tcpc = numeroDoTexto(form.tcpc);
  const lance = limpo({
    estrategia: form.estrategia,
    target_cpa: form.estrategia === 'MAXIMIZE_CONVERSIONS' && tcpa != null ? tcpa : undefined,
    target_roas: form.estrategia === 'MAXIMIZE_CONVERSION_VALUE' && roas != null ? roas : undefined,
    target_cpc: form.estrategia === 'TARGET_CPC' && tcpc != null ? tcpc : undefined,
  });
  const video = form.formato === 'VIDEO_RESPONSIVO'
    ? limpo({
      youtube_ids: linhas(form.videoIds),
      call_to_action: form.videoCta || undefined,
      breadcrumb1: form.breadcrumb1.trim() || undefined,
      breadcrumb2: form.breadcrumb2.trim() || undefined,
    })
    : undefined;
  const publico = form.publico
    ? limpo({
      nome: form.publicoNome.trim(),
      user_lists: seTiver(linhas(form.userLists)),
      lookalikes: seTiver(form.lookalikes.map((l) => ({
        nome: l.nome.trim(),
        sementes: inteiros(l.sementes),
        expansao: l.expansao,
        paises: linhas(l.paises.replace(/[,;\s]+/g, '\n')).map((p) => p.toUpperCase()),
      }))),
      exclusoes_user_list: seTiver(linhas(form.exclusoesUserList)),
      idades: seTiver([...form.idades]),
      incluir_idade_indeterminada: form.inclIdade,
      generos: seTiver([...form.generos]),
      incluir_genero_indeterminado: form.inclGenero,
      rendas: seTiver([...form.rendas]),
      incluir_renda_indeterminada: form.inclRenda,
      status_parentais: seTiver([...form.parentais]),
      incluir_status_parental_indeterminado: form.inclParental,
    })
    : undefined;
  const tipos = AUTOMACOES_DEMAND_GEN_POR_FORMATO[form.formato] ?? [];
  const automacoes = tipos.length
    ? Object.fromEntries(tipos.map((t) => [t, form.automacoes[t] ? 'OPTED_IN' : 'OPTED_OUT'] as const))
    : undefined;
  return limpo({
    formato: form.formato,
    lance,
    call_to_action: form.formato === 'MULTI_ASSET' && form.cta ? form.cta : undefined,
    video,
    publico,
    segmentacao_otimizada: form.segOtimizada ?? undefined,
    automacoes,
    agenda: seTiver(faixasHHMM(form.agenda, false)),
  }) as ConfiguracaoDemandGenV25;
}

export interface EntradaDoPedidoDemandGen {
  base: BaseDoPedido;
  copy: CopyGerada;
  demandGen: ConfiguracaoDemandGen;
  assets: AssetDemandGen[];
  form: FormDemandGen;
}

export function montarPedidoDemandGen(
  e: EntradaDoPedidoDemandGen,
): PedidoDeProvaDemandGen<EstrategiaDemandGen> {
  const video = e.form.formato === 'VIDEO_RESPONSIVO';
  const copy: CopyGerada = video
    ? { ...e.copy, long_headlines: linhas(e.form.titulosLongos) }
    : { ...e.copy, long_headlines: [] };
  return limpo({
    opportunity_id: e.base.opportunity_id,
    run_id: e.base.run_id,
    customer_id: e.base.customer_id,
    login_customer_id: e.base.login_customer_id,
    copy,
    budget_diario: e.base.budget_diario,
    canal: 'DEMAND_GEN' as const,
    // Com `configuracao_demand_gen.lance`, o envelope precisa dizer a MESMA.
    estrategia_lance: e.form.estrategia,
    demand_gen: e.demandGen,
    // Vídeo responsivo: exatamente um logo quadrado e nada mais (contrato §3).
    assets_demand_gen: video ? e.assets.filter((a) => a.tipo === 'logo_quadrado') : e.assets,
    vertical: e.base.vertical,
    certificacoes: e.base.certificacoes,
    url_final: e.base.url_final,
    configuracao_demand_gen: configuracaoDemandGen(e.form),
  }) as PedidoDeProvaDemandGen<EstrategiaDemandGen>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Performance Max
// ═══════════════════════════════════════════════════════════════════════════

function opcoesDeUrl(o: FormOpcoesDeUrl): OpcoesDeUrl | undefined {
  const sufixo = pares(o.sufixo);
  const params = pares(o.parametros);
  if (!sufixo.length && !o.tracking.trim() && !params.length) return undefined;
  return limpo({
    sufixo_extra: seTiver(sufixo),
    tracking_url_template: o.tracking.trim() || undefined,
    parametros_personalizados: seTiver(params),
  });
}

function videosPorId(texto: string) {
  return linhas(texto).map((video_id) => ({ video_id }));
}

export function configuracaoPMax(
  form: FormPMax,
  imagensDosGrupos: Record<string, AssetDemandGen[]>,
  brandGuidelines: boolean,
): ConfiguracaoPMaxV25 {
  const grupos = form.grupos.map((g) => {
    const sinais: SinalDeAudiencia[] = [
      ...linhas(g.audiencias).map((valor) => ({ tipo: 'audience' as const, valor })),
      ...linhas(g.temas).map((valor) => ({ tipo: 'search_theme' as const, valor })),
    ];
    return limpo({
      nome: g.nome.trim(),
      url_final: g.url.trim(),
      textos: {
        headlines: linhas(g.titulos),
        long_headlines: linhas(g.titulosLongos),
        descriptions: linhas(g.descricoes),
      },
      imagens: imagensDosGrupos[g.id] ?? [],
      // `[]` é escolha; `null` é "ninguém escolheu" — e o servidor recusa.
      sinais: g.sinaisConfirmados ? sinais : null,
      videos: seTiver(videosPorId(g.videos)),
      path1: g.path1.trim() || undefined,
      path2: g.path2.trim() || undefined,
      opcoes_de_url: opcoesDeUrl(g.url_opcoes),
    });
  });
  const diretrizes = brandGuidelines && (form.corPrincipal || form.corDestaque || form.fonte)
    ? limpo({
      cor_principal: form.corPrincipal.trim() || undefined,
      cor_destaque: form.corDestaque.trim() || undefined,
      fonte: (form.fonte || undefined) as never,
    })
    : undefined;
  const cnValor = numeroDoTexto(form.cnValor);
  const cnMult = numeroDoTexto(form.cnMultiplicador);
  return limpo({
    path1: form.path1.trim() || undefined,
    path2: form.path2.trim() || undefined,
    opcoes_de_url: opcoesDeUrl(form.url_opcoes),
    videos: seTiver(videosPorId(form.videos)),
    grupos_adicionais: seTiver(grupos),
    automacoes_optadas: seTiver([...form.automacoes]),
    video_crawl: seTiver(form.videoCrawl.map((v) => ({
      url: v.url.trim(), plataforma: v.plataforma, habilitada: v.habilitada,
    }))),
    video_crawl_direitos_declarados:
      form.videoCrawl.length || form.direitosDeclarados ? form.direitosDeclarados : undefined,
    exclusoes_de_url: seTiver(form.exclusoesDeUrl.map((x) => ({
      nome: x.nome.trim(), argumento: x.argumento.trim(), operando: x.operando, operador: x.operador,
    }))),
    termos_excluidos: seTiver(linhas(form.termosExcluidos)),
    restricoes_de_mensagem: seTiver(linhas(form.restricoes)),
    diretrizes_de_marca: diretrizes,
    negativas_tipadas: seTiver(form.negativasTipadas
      .filter((n) => n.texto.trim())
      .map((n) => ({ texto: n.texto.trim(), match_type: n.match }))),
    listas_de_negativas: seTiver(linhas(form.listasDeNegativas)),
    marcas_excluidas: seTiver(form.marcasExcluidas.map((m) => limpo({
      entity_id: m.entity_id.trim(), nome: m.nome.trim() || undefined,
    }))),
    listas_de_marcas_excluidas: seTiver(linhas(form.listasDeMarcas)),
    metas_de_conversao: seTiver(form.metas.map((m) => ({
      categoria: m.categoria, origem: m.origem, biddable: m.lance,
    }))),
    meta_cliente_novo: form.clienteNovo
      ? limpo({
        goal: form.cnGoal.trim(),
        modo: form.cnModo,
        valor_adicional: cnValor ?? undefined,
        multiplicador_de_valor: cnMult ?? undefined,
      })
      : undefined,
  }) as ConfiguracaoPMaxV25;
}

export interface EntradaDoPedidoPMax {
  base: BaseDoPedido;
  copy: CopyGerada;
  estrategia: 'MAXIMIZE_CONVERSIONS' | 'MAXIMIZE_CONVERSION_VALUE';
  /** O alvo digitado: tCPA em moeda, ou tROAS em PORCENTAGEM. */
  meta: string;
  brandGuidelines: boolean;
  audiencias: string[];
  temas: string[];
  negativas: string[];
  nomeDoAssetGroup: string;
  assets: AssetDemandGen[];
  form: FormPMax;
  imagensDosGrupos: Record<string, AssetDemandGen[]>;
}

export function montarPedidoPMax(e: EntradaDoPedidoPMax): PedidoDeProvaPMax {
  const valor = e.estrategia === 'MAXIMIZE_CONVERSION_VALUE'
    ? razaoDaPorcentagem(e.meta) : numeroDoTexto(e.meta);
  return limpo({
    opportunity_id: e.base.opportunity_id,
    run_id: e.base.run_id,
    customer_id: e.base.customer_id,
    login_customer_id: e.base.login_customer_id,
    canal: 'PERFORMANCE_MAX' as const,
    copy: e.copy,
    budget_diario: e.base.budget_diario,
    estrategia_lance: e.estrategia,
    tcpa: e.estrategia === 'MAXIMIZE_CONVERSIONS' && valor != null ? valor : undefined,
    target_roas: e.estrategia === 'MAXIMIZE_CONVERSION_VALUE' && valor != null ? valor : undefined,
    vertical: e.base.vertical,
    certificacoes: e.base.certificacoes,
    url_final: e.base.url_final,
    pmax: {
      brand_guidelines_enabled: e.brandGuidelines,
      audiencias: e.audiencias,
      search_themes: e.temas,
      negativas: e.negativas,
      nome_do_asset_group: e.nomeDoAssetGroup.trim(),
    },
    assets_pmax: e.assets,
    configuracao_pmax: configuracaoPMax(e.form, e.imagensDosGrupos, e.brandGuidelines),
  }) as PedidoDeProvaPMax;
}

// ═══════════════════════════════════════════════════════════════════════════
// O que falta decidir — por parada
// ═══════════════════════════════════════════════════════════════════════════

export type FaltasPorParada = Partial<Record<ParadaDaBancada, string[]>>;

function empurrar(f: FaltasPorParada, p: ParadaDaBancada, texto: string) {
  (f[p] ??= []).push(texto);
}

/**
 * As DECISÕES que faltam em Search. Não são as regras do motor — essas voltam
 * no 422, no campo. São as escolhas sem default que o contrato exige que
 * alguém tome, e os números digitados que não são número.
 */
export function faltasDeSearch(
  form: FormSearch, estrategia: EstrategiaSearch,
  matchEscolhido: Record<string, string>, conjunto: RevisaoDoConjuntoPago | null,
): FaltasPorParada {
  const f: FaltasPorParada = {};
  const l = form.lance;
  for (const [bruto, nome] of [[l.tcpa, 'CPA alvo'], [l.troasPct, 'ROAS alvo'],
    [l.tetoCpc, 'teto de CPC'], [l.fracaoPct, 'parcela de impressões']] as const) {
    if (numeroInvalido(bruto)) empurrar(f, 'economia', `corrigir o ${nome}: não é número`);
  }
  if (estrategia === 'TARGET_IMPRESSION_SHARE') {
    if (!l.local) empurrar(f, 'economia', 'escolher onde a impressão deve aparecer');
    if (numeroDoTexto(l.fracaoPct) == null) empurrar(f, 'economia', 'declarar a parcela de impressões');
    if (numeroDoTexto(l.tetoCpc) == null) empurrar(f, 'economia', 'declarar o teto de CPC');
  }
  if (form.metaModo === 'personalizada' && !form.metaPersonalizada.trim()) {
    empurrar(f, 'economia', 'informar a meta personalizada ou voltar para a meta da conta');
  }
  if (form.metaModo === 'acoes' && !linhas(form.metaAcoes).length && !form.metaCategorias.length) {
    empurrar(f, 'economia', 'informar ações ou categorias de conversão, ou voltar para a meta da conta');
  }
  if (form.parceiros == null) empurrar(f, 'alcance', 'decidir sobre os parceiros de pesquisa');
  if (form.expansaoDisplay == null) empurrar(f, 'alcance', 'decidir sobre a expansão para Display');
  if (form.aiMax && (form.aiCorrespondencia == null || form.aiPersonalizacao == null
      || form.aiExpansaoUrl == null)) {
    empurrar(f, 'alcance', 'declarar as três automações do AI Max');
  }
  for (const d of form.dispositivos) {
    if (numeroDoTexto(d.fator) == null) empurrar(f, 'alcance', `declarar o fator de ${d.dispositivo.toLowerCase()}`);
  }
  if (!lancePorConversao(estrategia)) {
    const broad = Object.keys(matchPorKeywordDoPedido(matchEscolhido, conjunto))
      .filter((k) => matchEscolhido[k] === 'BROAD');
    if (broad.length) {
      empurrar(f, 'termos', `tirar a correspondência ampla de ${broad.length} keyword(s): ampla só com lance por conversão`);
    }
  }
  return f;
}

export function faltasDeDisplay(form: FormDisplay): FaltasPorParada {
  const f: FaltasPorParada = {};
  if (form.estrategia === 'MANUAL_CPC' && numeroDoTexto(form.cpcManual) == null) {
    empurrar(f, 'display_economia', 'declarar o lance por clique do grupo');
  }
  if (form.estrategia === 'MANUAL_CPM' && numeroDoTexto(form.cpm) == null) {
    empurrar(f, 'display_economia', 'declarar o CPM visível');
  }
  for (const [bruto, nome] of [[form.tcpa, 'CPA alvo'], [form.troasPct, 'ROAS alvo'],
    [form.tetoCpc, 'teto de CPC'], [form.cpm, 'CPM'], [form.cpcManual, 'lance por clique']] as const) {
    if (numeroInvalido(bruto)) empurrar(f, 'display_economia', `corrigir o ${nome}: não é número`);
  }
  for (const q of form.frequencia) {
    if (numeroDoTexto(q.impressoes) == null) empurrar(f, 'display_economia', 'declarar as impressões de cada limite de frequência');
  }
  const temItemNaLista = form.listaNovaPlacements.trim() || form.listaNovaApps.trim()
    || form.listaNovaCategorias.trim();
  if (temItemNaLista && !form.listaNovaNome.trim()) {
    empurrar(f, 'display_inventario', 'dar nome à lista de exclusão nova');
  }
  return f;
}

export function faltasDeDemandGen(form: FormDemandGen, assets: AssetDemandGen[]): FaltasPorParada {
  const f: FaltasPorParada = {};
  if (form.formato === 'CARROSSEL') {
    empurrar(f, 'demand_kit', 'trocar o formato: carrossel não atravessa a fronteira HTTP');
  }
  if (form.formato === 'VIDEO_RESPONSIVO') {
    if (!linhas(form.videoIds).length) empurrar(f, 'demand_kit', 'informar ao menos um vídeo do YouTube');
    const logos = assets.filter((a) => a.tipo === 'logo_quadrado').length;
    if (logos !== 1) empurrar(f, 'demand_kit', 'anexar exatamente um logo quadrado');
    if (!linhas(form.titulosLongos).length) empurrar(f, 'demand_mensagem', 'escrever ao menos um título longo do vídeo');
  }
  if (form.estrategia === 'TARGET_CPC' && numeroDoTexto(form.tcpc) == null) {
    empurrar(f, 'demand_economia', 'declarar o CPC alvo');
  }
  for (const [bruto, nome] of [[form.tcpa, 'CPA alvo'], [form.troasPct, 'ROAS alvo'], [form.tcpc, 'CPC alvo']] as const) {
    if (numeroInvalido(bruto)) empurrar(f, 'demand_economia', `corrigir o ${nome}: não é número`);
  }
  if (form.publico && !form.publicoNome.trim()) empurrar(f, 'demand_audiencia', 'dar nome ao público composto');
  return f;
}

export function faltasDePMax(form: FormPMax): FaltasPorParada {
  const f: FaltasPorParada = {};
  form.grupos.forEach((g, i) => {
    const n = g.nome.trim() || `grupo ${i + 2}`;
    if (!g.nome.trim()) empurrar(f, 'pmax_asset_group', `dar nome ao asset group ${i + 2}`);
    if (!g.url.trim()) empurrar(f, 'pmax_asset_group', `informar a URL final de ${n}`);
    if (!g.sinaisConfirmados) empurrar(f, 'pmax_asset_group', `confirmar os sinais de ${n}, mesmo vazios`);
  });
  if (form.clienteNovo && !form.cnGoal.trim()) {
    empurrar(f, 'pmax_objetivo', 'informar o Goal de cliente novo da conta');
  }
  return f;
}

/** Junta faltas de várias fontes sem perder nenhuma. */
export function juntarFaltas(...fontes: FaltasPorParada[]): FaltasPorParada {
  const saida: FaltasPorParada = {};
  for (const fonte of fontes) {
    for (const [p, lista] of Object.entries(fonte)) {
      for (const t of lista ?? []) empurrar(saida, p as ParadaDaBancada, t);
    }
  }
  return saida;
}
