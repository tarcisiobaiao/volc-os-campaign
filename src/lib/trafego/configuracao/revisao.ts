/**
 * O que a Revisão mostra antes de provar: o resumo das escolhas de cada canal
 * e os avisos — os que o CONTRATO diz que o servidor vai emitir para estas
 * escolhas, e, depois da prova, os que o servidor de fato emitiu.
 *
 * ## Por que existe um "aviso previsto"
 *
 * Os avisos novos (GADS-CRIACAO-CANAIS-v1 §5) só voltam na resposta de
 * `/provar`. Mas a decisão que os provoca — ligar a expansão para Display,
 * colar um id de YouTube, trocar a correspondência de uma keyword — é tomada
 * ANTES, e o operador tem o direito de saber o preço dela antes do clique. O
 * previsto é a leitura literal do contrato sobre o pedido montado, rotulado
 * como previsão; quando a prova volta, os avisos do servidor tomam o lugar.
 */
import type { AvisoDoCockpit, Preparo } from '@/types/trafego';
import type {
  ConfiguracaoDemandGenV25, ConfiguracaoDisplay, ConfiguracaoPMaxV25, ConfiguracaoSearch,
  MatchPorKeyword,
} from '@/types/trafegoCanais';

export interface AvisoDaRevisao {
  codigo: string;
  titulo: string;
  detalhe: string;
  /** `contrato` = previsto pela leitura do contrato; `servidor` = devolvido. */
  fonte: 'contrato' | 'servidor';
}

export interface LinhaDoResumo { rotulo: string; valor: string }

const ROTULO_DA_ESTRATEGIA: Record<string, string> = {
  MANUAL_CPC: 'CPC manual',
  TARGET_SPEND: 'Maximizar cliques (TARGET_SPEND)',
  MAXIMIZE_CONVERSIONS: 'Maximizar conversões',
  MAXIMIZE_CONVERSION_VALUE: 'Maximizar valor de conversão',
  TARGET_IMPRESSION_SHARE: 'Parcela de impressões',
  MANUAL_CPM: 'CPM visível manual',
  TARGET_CPC: 'CPC alvo',
};

export function rotuloDaEstrategia(e: string): string {
  return ROTULO_DA_ESTRATEGIA[e] ?? e;
}

const sim = (b: boolean | undefined | null) => (b ? 'sim' : 'não');
const qtd = (n: number | undefined, palavra: string) => `${n ?? 0} ${palavra}`;
const moeda = (n: number) => `R$ ${n.toFixed(2).replace('.', ',')}`;
const pct = (razao: number) => `${Number((razao * 100).toFixed(2)).toString().replace('.', ',')}%`;

// ── Search ────────────────────────────────────────────────────────────────

export function resumoDeSearch(
  c: ConfiguracaoSearch, match: MatchPorKeyword | undefined,
): LinhaDoResumo[] {
  const l = c.lance;
  const linhas: LinhaDoResumo[] = [];
  if (l) {
    linhas.push({ rotulo: 'estratégia', valor: rotuloDaEstrategia(l.estrategia) });
    if (l.target_cpa != null) linhas.push({ rotulo: 'CPA alvo', valor: moeda(l.target_cpa) });
    if (l.target_roas != null) linhas.push({ rotulo: 'ROAS alvo', valor: pct(l.target_roas) });
    if (l.teto_cpc != null) linhas.push({ rotulo: 'teto de CPC', valor: moeda(l.teto_cpc) });
    if (l.local_impressao) linhas.push({ rotulo: 'onde aparecer', valor: l.local_impressao });
    if (l.fracao_impressao != null) linhas.push({ rotulo: 'parcela de impressões', valor: pct(l.fracao_impressao) });
  }
  linhas.push({
    rotulo: 'rede',
    valor: c.rede
      ? `Google Search · parceiros ${sim(c.rede.parceiros)} · expansão Display ${sim(c.rede.display_expansion)}`
      : 'não decidida',
  });
  linhas.push({
    rotulo: 'AI Max',
    valor: c.ai_max
      ? `termos ${sim(c.ai_max.correspondencia_de_termos)} · texto ${sim(c.ai_max.personalizacao_de_texto)} · URL final ${sim(c.ai_max.expansao_de_url_final)}`
      : 'desligado',
  });
  if (c.anuncio) {
    linhas.push({
      rotulo: 'RSA',
      valor: `caminho /${c.anuncio.path1 ?? ''}${c.anuncio.path2 ? `/${c.anuncio.path2}` : ''} · ${qtd(c.anuncio.fixacoes?.length, 'fixação(ões)')}`,
    });
  }
  linhas.push({ rotulo: 'programação', valor: c.programacao?.length ? qtd(c.programacao.length, 'faixa(s)') : 'o dia todo' });
  linhas.push({
    rotulo: 'dispositivos',
    valor: c.dispositivos?.length
      ? c.dispositivos.map((d) => `${d.dispositivo.toLowerCase()} ${d.fator === 0 ? 'excluído' : `×${d.fator}`}`).join(' · ')
      : 'todos, sem ajuste',
  });
  linhas.push({
    rotulo: 'geo',
    valor: c.geo
      ? `${c.geo.tipo_positivo} · ${qtd(c.geo.locais?.length, 'local(is)')} · ${qtd(c.geo.locais_excluidos?.length, 'excluído(s)')} · idiomas ${c.geo.idiomas?.join(', ') || 'do brief'}`
      : 'o país e o idioma do brief',
  });
  if (c.inicio || c.fim) linhas.push({ rotulo: 'datas', valor: `${c.inicio ?? 'já'} → ${c.fim ?? 'sem fim'}` });
  const m = c.meta_de_conversao;
  linhas.push({
    rotulo: 'meta de conversão',
    valor: !m ? 'a da conta'
      : m.meta_personalizada ? `personalizada ${m.meta_personalizada}`
        : `${qtd(m.acoes_de_conversao?.length, 'ação(ões)')} · ${qtd(m.categorias?.length, 'categoria(s)')}`,
  });
  const trocas = Object.entries(match ?? {});
  linhas.push({
    rotulo: 'correspondência trocada',
    valor: trocas.length ? trocas.map(([k, v]) => `${k} → ${v}`).join(' · ') : 'nenhuma',
  });
  return linhas;
}

// ── Display ───────────────────────────────────────────────────────────────

export function resumoDeDisplay(c: ConfiguracaoDisplay): LinhaDoResumo[] {
  const s = c.segmentacao ?? {};
  const e = c.exclusoes ?? {};
  const nSeg = ['listas_de_usuarios', 'publicos_personalizados', 'publicos_combinados', 'interesses',
    'topicos', 'placements', 'palavras_chave']
    .reduce((n, k) => n + ((s as Record<string, string[] | undefined>)[k]?.length ?? 0), 0);
  return [
    { rotulo: 'estratégia', valor: rotuloDaEstrategia(c.lance?.estrategia ?? 'MAXIMIZE_CONVERSIONS') },
    { rotulo: 'segmentação', valor: nSeg ? `${nSeg} critério(s) · ${s.publicos_em_observacao ? 'observação' : 'restringe'}` : 'inventário aberto' },
    { rotulo: 'segmentação otimizada', valor: sim(s.segmentacao_otimizada) },
    {
      rotulo: 'exclusões',
      valor: `todos os apps ${sim(e.excluir_todos_os_apps)} · ${qtd(e.rotulos_de_conteudo?.length, 'rótulo(s)')} · ${qtd(e.placements?.length, 'site(s)')}${e.lista_nova ? ` · lista nova "${e.lista_nova.nome}"` : ''}`,
    },
    { rotulo: 'frequência', valor: c.frequencia?.length ? c.frequencia.map((f) => `${f.impressoes}/${f.unidade ?? 'DAY'}`).join(' · ') : 'sem limite' },
    { rotulo: 'agenda', valor: c.agenda?.length ? qtd(c.agenda.length, 'janela(s)') : 'o dia todo' },
    { rotulo: 'dispositivos excluídos', valor: c.dispositivos_excluidos?.join(', ') || 'nenhum' },
    { rotulo: 'presença geográfica', valor: c.presenca_geo ?? 'PRESENCE' },
    { rotulo: 'formato do anúncio', valor: `${c.anuncio?.formato ?? 'ALL_FORMATS'} · ${qtd(c.anuncio?.videos_youtube?.length, 'vídeo(s)')}` },
  ];
}

// ── Demand Gen ────────────────────────────────────────────────────────────

export function resumoDeDemandGen(c: ConfiguracaoDemandGenV25): LinhaDoResumo[] {
  const ligadas = Object.entries(c.automacoes ?? {}).filter(([, v]) => v === 'OPTED_IN').map(([k]) => k);
  return [
    { rotulo: 'formato', valor: c.formato ?? 'MULTI_ASSET' },
    { rotulo: 'estratégia', valor: rotuloDaEstrategia(c.lance?.estrategia ?? 'MAXIMIZE_CONVERSIONS') },
    ...(c.video ? [{ rotulo: 'vídeos', valor: c.video.youtube_ids.join(', ') }] : []),
    { rotulo: 'público composto', valor: c.publico ? `${c.publico.nome} · ${qtd(c.publico.user_lists?.length, 'lista(s)')} · ${qtd(c.publico.lookalikes?.length, 'semelhante(s)')}` : 'nenhum' },
    { rotulo: 'segmentação otimizada', valor: c.segmentacao_otimizada == null ? 'não emitida' : sim(c.segmentacao_otimizada) },
    { rotulo: 'automações ligadas', valor: ligadas.length ? ligadas.join(', ') : 'nenhuma' },
    { rotulo: 'agenda', valor: c.agenda?.length ? qtd(c.agenda.length, 'faixa(s)') : 'o dia todo' },
  ];
}

// ── PMax ──────────────────────────────────────────────────────────────────

export function resumoDePMax(c: ConfiguracaoPMaxV25): LinhaDoResumo[] {
  return [
    { rotulo: 'asset groups', valor: `${1 + (c.grupos_adicionais?.length ?? 0)} (1 do brief + ${c.grupos_adicionais?.length ?? 0} adicional(is))` },
    { rotulo: 'automações optadas', valor: c.automacoes_optadas?.join(', ') || 'nenhuma (todas OPTED_OUT)' },
    { rotulo: 'vídeos', valor: qtd((c.videos?.length ?? 0) + (c.grupos_adicionais ?? []).reduce((n, g) => n + (g.videos?.length ?? 0), 0), 'id(s) do YouTube') },
    { rotulo: 'video crawl', valor: c.video_crawl?.length ? `${c.video_crawl.length} fonte(s) · direitos ${sim(c.video_crawl_direitos_declarados)}` : 'desligado' },
    { rotulo: 'negativas tipadas', valor: qtd(c.negativas_tipadas?.length, 'termo(s)') },
    { rotulo: 'marcas excluídas', valor: qtd((c.marcas_excluidas?.length ?? 0) + (c.listas_de_marcas_excluidas?.length ?? 0), 'item(ns)') },
    { rotulo: 'exclusões de URL', valor: qtd(c.exclusoes_de_url?.length, 'regra(s)') },
    { rotulo: 'metas de conversão', valor: c.metas_de_conversao?.length ? qtd(c.metas_de_conversao.length, 'sobrescrita(s)') : 'as da conta' },
    { rotulo: 'cliente novo', valor: c.meta_cliente_novo ? c.meta_cliente_novo.modo : 'não' },
  ];
}

// ═══════════════════════════════════════════════════════════════════════════
// Avisos previstos pelo contrato
// ═══════════════════════════════════════════════════════════════════════════

const VIDEO_SEM_PORTAO = (ids: string[]): AvisoDaRevisao => ({
  codigo: 'VIDEO_SEM_PORTAO_DE_POLITICA',
  titulo: 'Vídeo do YouTube fora do portão de política',
  detalhe: `${ids.length} vídeo(s) entram por id público (${ids.join(', ')}). O portão criativo julga bytes e o servidor não tem os bytes de um vídeo do YouTube: sem hash, sem inspeção, sem recibo. Trocar um vídeo invalida a aprovação.`,
  fonte: 'contrato',
});

export function avisosPrevistosDeSearch(
  c: ConfiguracaoSearch, match: MatchPorKeyword | undefined,
): AvisoDaRevisao[] {
  const a: AvisoDaRevisao[] = [];
  if (c.rede?.display_expansion) {
    a.push({
      codigo: 'display_expansion',
      titulo: 'Expansão para Display ligada',
      detalhe: 'O plano sempre traz este aviso, e o canário de Search recusa a expansão: a prova roda, a criação pausada não sai por este canal.',
      fonte: 'contrato',
    });
  }
  if (c.rede?.parceiros) {
    a.push({
      codigo: 'search_partners',
      titulo: 'Parceiros de pesquisa ligados',
      detalhe: 'Inventário fora do Google, com outro CPC efetivo. O canário de Search recusa parceiros.',
      fonte: 'contrato',
    });
  }
  const trocas = Object.entries(match ?? {});
  if (trocas.length) {
    a.push({
      codigo: 'MATCH_TYPE_ESCOLHIDO_NA_TELA',
      titulo: 'Correspondência trocada em keyword aprovada',
      detalhe: `${trocas.map(([k, v]) => `"${k}" → ${v}`).join('; ')}. O conjunto aprovado continua o mesmo; a correspondência entra na impressão do plano.`,
      fonte: 'contrato',
    });
  }
  return a;
}

export function avisosPrevistosDeDisplay(c: ConfiguracaoDisplay): AvisoDaRevisao[] {
  const a: AvisoDaRevisao[] = [];
  const ids = c.anuncio?.videos_youtube ?? [];
  if (ids.length) a.push(VIDEO_SEM_PORTAO(ids));
  const s = c.segmentacao ?? {};
  const algum = Object.values(s).some((v) => Array.isArray(v) && v.length > 0);
  if (!algum) {
    a.push({
      codigo: 'INVENTARIO_ABERTO',
      titulo: 'Segmentação vazia = inventário aberto',
      detalhe: 'Sem critério positivo, o anúncio pode aparecer em qualquer lugar da rede que a estratégia de lance escolher. O plano avisa.',
      fonte: 'contrato',
    });
  }
  return a;
}

export function avisosPrevistosDeDemandGen(c: ConfiguracaoDemandGenV25): AvisoDaRevisao[] {
  const ids = c.video?.youtube_ids ?? [];
  return ids.length ? [VIDEO_SEM_PORTAO(ids)] : [];
}

export function avisosPrevistosDePMax(c: ConfiguracaoPMaxV25): AvisoDaRevisao[] {
  const a: AvisoDaRevisao[] = [];
  const ids = [
    ...(c.videos ?? []).map((v) => v.video_id),
    ...(c.grupos_adicionais ?? []).flatMap((g) => (g.videos ?? []).map((v) => v.video_id)),
  ];
  if (ids.length) a.push(VIDEO_SEM_PORTAO(ids));
  if (c.meta_cliente_novo) {
    a.push({
      codigo: 'META_CLIENTE_NOVO_POS_CRIACAO',
      titulo: 'Meta de cliente novo fica fora do validate_only',
      detalhe: 'Aceita na forma, mas aplicada numa SEGUNDA chamada depois da criação (CampaignGoalConfig não existe no mutate). A prova não a confere.',
      fonte: 'contrato',
    });
  }
  return a;
}

/** Os avisos que a prova devolveu: os do plano e os da validação local. */
export function avisosDaProva(
  resposta: { avisos?: AvisoDoCockpit[]; preparo?: Pick<Preparo, 'avisos_locais'> } | null,
): AvisoDaRevisao[] {
  if (!resposta) return [];
  return [
    ...(resposta.avisos ?? []).map((x) => ({
      codigo: x.codigo, titulo: x.titulo, detalhe: x.detalhe, fonte: 'servidor' as const,
    })),
    ...(resposta.preparo?.avisos_locais ?? []).map((texto) => ({
      codigo: 'AVISO_LOCAL', titulo: 'Validação local', detalhe: texto, fonte: 'servidor' as const,
    })),
  ];
}
