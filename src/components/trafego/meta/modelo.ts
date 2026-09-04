export type TipoMeta = 'campanhas' | 'conjuntos' | 'anuncios' | 'criativos';

export interface ObjetoMetaDemo {
  id: string;
  tipo: TipoMeta;
  nome: string;
  status: 'ATIVO' | 'PAUSADO' | 'RASCUNHO';
  pai?: string;
  paiId?: string;
  objetivo?: string;
  entrega?: string;
  orcamento?: string;
  resultado?: string;
  custo?: string;
  detalhe?: string;
  /** Projeto/site VOLC ao qual o objeto está vinculado — mesma noção que `Campaign.projectId` no Google Ads. */
  projeto?: string;
  site?: string;
  /** Data de criação, ISO `YYYY-MM-DD`. Ausente apenas quando o objeto nunca foi de fato criado na plataforma. */
  criadoEm?: string;
  /** `null` = sem término definido (contínua). Nunca inventado quando a campanha nunca rodou. */
  terminaEm?: string | null;
}

export interface MetaInsightDiarioDemo {
  data: string;
  gasto: number;
  receitaGam: number;
  impressoes: number;
  alcance: number;
  cliquesNoLink: number;
  visualizacoesDaPagina: number;
}

/**
 * Contrato visual do detalhe Meta.
 *
 * Ele espelha a granularidade planejada para `trafego_meta_insight_daily`, mas
 * não se passa por read model vivo: todos os consumidores precisam exibir o
 * modo demonstrativo. `null` significa não observado; jamais vira zero.
 */
export interface MetaCampaignInsightDemo {
  campanhaId: string;
  periodo: string;
  gasto: number | null;
  receitaGam: number | null;
  impressoes: number | null;
  alcance: number | null;
  cliquesNoLink: number | null;
  visualizacoesDaPagina: number | null;
  atribuicao: string;
  eventoDeResultado: string;
  atualizadoEm: null;
  serie: MetaInsightDiarioDemo[];
}

export const META_DEMO: Record<TipoMeta, ObjetoMetaDemo[]> = {
  campanhas: [
    {
      id: 'campanha-descoberta-01', tipo: 'campanhas', nome: 'Guia Encceja · Descoberta',
      status: 'ATIVO', objetivo: 'Tráfego', entrega: 'Estável', orcamento: 'R$ 120/dia',
      resultado: '1.842 sessões', custo: 'R$ 684,20', detalhe: 'Menor custo · lance',
      projeto: 'Foco Genial', site: 'focogenial.com.br', criadoEm: '2026-07-22', terminaEm: null,
    },
    {
      id: 'campanha-beneficios-02', tipo: 'campanhas', nome: 'Benefícios · Conteúdo útil',
      status: 'PAUSADO', objetivo: 'Tráfego', entrega: 'Sem veiculação', orcamento: 'R$ 80/dia',
      resultado: '—', custo: 'R$ 0,00', detalhe: 'Menor custo · lance',
      projeto: 'Foco Genial', site: 'focogenial.com.br', criadoEm: '2026-08-05', terminaEm: null,
    },
    {
      id: 'campanha-retargeting-03', tipo: 'campanhas', nome: 'Leitores engajados · Retorno',
      status: 'RASCUNHO', objetivo: 'Engajamento', entrega: 'Ainda não enviado', orcamento: 'R$ 45/dia',
      resultado: '—', custo: '—', detalhe: 'Menor custo · lance',
      projeto: 'Foco Genial', site: 'focogenial.com.br', criadoEm: '2026-08-29', terminaEm: null,
    },
  ],
  conjuntos: [
    {
      id: 'conjunto-aberto-01', tipo: 'conjuntos', nome: 'Brasil · Amplo · 18–54',
      pai: 'Guia Encceja · Descoberta', paiId: 'campanha-descoberta-01', status: 'ATIVO',
      entrega: 'Estável', orcamento: 'Campanha', resultado: '1.204 sessões', custo: 'R$ 422,18',
      detalhe: 'Visualização da página de destino',
    },
    {
      id: 'conjunto-interesse-02', tipo: 'conjuntos', nome: 'Educação e certificação',
      pai: 'Guia Encceja · Descoberta', paiId: 'campanha-descoberta-01', status: 'ATIVO',
      entrega: 'Aprendizado', orcamento: 'Campanha', resultado: '638 sessões', custo: 'R$ 262,02',
      detalhe: 'Visualização da página de destino',
    },
    {
      id: 'conjunto-retorno-03', tipo: 'conjuntos', nome: 'Visitou conteúdo · 30 dias',
      pai: 'Leitores engajados · Retorno', paiId: 'campanha-retargeting-03', status: 'RASCUNHO',
      entrega: 'Ainda não enviado', orcamento: 'R$ 45/dia', resultado: '—', custo: '—',
      detalhe: 'Visualização da página de destino',
    },
  ],
  anuncios: [
    {
      id: 'anuncio-certificado-01', tipo: 'anuncios', nome: 'Certificado Encceja · imagem A',
      pai: 'Brasil · Amplo · 18–54', paiId: 'conjunto-aberto-01', status: 'ATIVO',
      entrega: 'Em veiculação', resultado: '1.027 cliques', custo: 'R$ 351,33',
      detalhe: 'Saiba como consultar o certificado',
    },
    {
      id: 'anuncio-prazo-02', tipo: 'anuncios', nome: 'Prazos e documentos · imagem B',
      pai: 'Brasil · Amplo · 18–54', paiId: 'conjunto-aberto-01', status: 'ATIVO',
      entrega: 'Em veiculação', resultado: '815 cliques', custo: 'R$ 332,87',
      detalhe: 'Veja regras, prazos e documentos',
    },
    {
      id: 'anuncio-retorno-03', tipo: 'anuncios', nome: 'Continue a leitura · carrossel',
      pai: 'Visitou conteúdo · 30 dias', paiId: 'conjunto-retorno-03', status: 'RASCUNHO',
      entrega: 'Ainda não enviado', resultado: '—', custo: '—', detalhe: 'Retome o guia completo',
    },
  ],
  criativos: [
    {
      id: 'criativo-imagem-01', tipo: 'criativos', nome: 'Encceja · estudante no notebook',
      pai: 'Certificado Encceja · imagem A', paiId: 'anuncio-certificado-01', status: 'ATIVO',
      entrega: 'Aprovado', detalhe: 'Imagem 1:1 · 1080 × 1080', resultado: 'Usado em 1 anúncio', custo: '—',
    },
    {
      id: 'criativo-imagem-02', tipo: 'criativos', nome: 'Documentos · mesa de estudos',
      pai: 'Prazos e documentos · imagem B', paiId: 'anuncio-prazo-02', status: 'ATIVO',
      entrega: 'Aprovado', detalhe: 'Imagem 4:5 · 1080 × 1350', resultado: 'Usado em 1 anúncio', custo: '—',
    },
    {
      id: 'criativo-carrossel-03', tipo: 'criativos', nome: 'Passo a passo · três cartões',
      pai: 'Continue a leitura · carrossel', paiId: 'anuncio-retorno-03', status: 'RASCUNHO',
      entrega: 'Validação local', detalhe: 'Carrossel · 3 cartões', resultado: 'Ainda não usado', custo: '—',
    },
  ],
};

export const META_INSIGHTS_DEMO: Record<string, MetaCampaignInsightDemo> = {
  'campanha-descoberta-01': {
    campanhaId: 'campanha-descoberta-01',
    periodo: 'Últimos 7 dias · cenário demonstrativo',
    gasto: 684.2,
    receitaGam: 1110,
    impressoes: 86420,
    alcance: 61280,
    cliquesNoLink: 2189,
    visualizacoesDaPagina: 1842,
    atribuicao: '7 dias após clique · 1 dia após visualização',
    eventoDeResultado: 'Visualização da página de destino',
    atualizadoEm: null,
    serie: [
      { data: '29/08', gasto: 82.4, receitaGam: 126.2, impressoes: 11240, alcance: 8580, cliquesNoLink: 278, visualizacoesDaPagina: 231 },
      { data: '30/08', gasto: 91.8, receitaGam: 141.7, impressoes: 11980, alcance: 8910, cliquesNoLink: 302, visualizacoesDaPagina: 252 },
      { data: '31/08', gasto: 96.1, receitaGam: 159.4, impressoes: 12470, alcance: 9140, cliquesNoLink: 317, visualizacoesDaPagina: 270 },
      { data: '01/09', gasto: 104.7, receitaGam: 166.1, impressoes: 13210, alcance: 9380, cliquesNoLink: 336, visualizacoesDaPagina: 282 },
      { data: '02/09', gasto: 99.2, receitaGam: 171.8, impressoes: 12760, alcance: 9070, cliquesNoLink: 321, visualizacoesDaPagina: 274 },
      { data: '03/09', gasto: 108.6, receitaGam: 180.5, impressoes: 13640, alcance: 9510, cliquesNoLink: 348, visualizacoesDaPagina: 293 },
      { data: '04/09', gasto: 101.4, receitaGam: 164.3, impressoes: 15120, alcance: 10690, cliquesNoLink: 287, visualizacoesDaPagina: 240 },
    ],
  },
  'campanha-beneficios-02': {
    campanhaId: 'campanha-beneficios-02', periodo: 'Últimos 7 dias · cenário demonstrativo',
    gasto: 0, receitaGam: 0, impressoes: 0, alcance: 0, cliquesNoLink: 0,
    visualizacoesDaPagina: 0, atribuicao: '7 dias após clique · 1 dia após visualização',
    eventoDeResultado: 'Visualização da página de destino', atualizadoEm: null, serie: [],
  },
  'campanha-retargeting-03': {
    campanhaId: 'campanha-retargeting-03', periodo: 'Rascunho · cenário demonstrativo',
    gasto: null, receitaGam: null, impressoes: null, alcance: null, cliquesNoLink: null,
    visualizacoesDaPagina: null, atribuicao: 'Ainda não declarada',
    eventoDeResultado: 'Ainda não declarado', atualizadoEm: null, serie: [],
  },
};

export const ROTULOS_META: Record<TipoMeta, { singular: string; plural: string }> = {
  campanhas: { singular: 'campanha', plural: 'campanhas' },
  conjuntos: { singular: 'conjunto', plural: 'conjuntos' },
  anuncios: { singular: 'anúncio', plural: 'anúncios' },
  criativos: { singular: 'criativo', plural: 'criativos' },
};

export function objetoMetaDemo(tipo: TipoMeta, id: string): ObjetoMetaDemo | undefined {
  return META_DEMO[tipo].find((objeto) => objeto.id === id);
}
