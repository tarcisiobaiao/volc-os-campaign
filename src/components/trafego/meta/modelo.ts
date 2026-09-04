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
}

export const META_DEMO: Record<TipoMeta, ObjetoMetaDemo[]> = {
  campanhas: [
    {
      id: 'campanha-descoberta-01', tipo: 'campanhas', nome: 'Guia Encceja · Descoberta',
      status: 'ATIVO', objetivo: 'Tráfego', entrega: 'Estável', orcamento: 'R$ 120/dia',
      resultado: '1.842 sessões', custo: 'R$ 684,20', detalhe: 'Menor custo · lance',
    },
    {
      id: 'campanha-beneficios-02', tipo: 'campanhas', nome: 'Benefícios · Conteúdo útil',
      status: 'PAUSADO', objetivo: 'Tráfego', entrega: 'Sem veiculação', orcamento: 'R$ 80/dia',
      resultado: '—', custo: 'R$ 0,00', detalhe: 'Menor custo · lance',
    },
    {
      id: 'campanha-retargeting-03', tipo: 'campanhas', nome: 'Leitores engajados · Retorno',
      status: 'RASCUNHO', objetivo: 'Engajamento', entrega: 'Ainda não enviado', orcamento: 'R$ 45/dia',
      resultado: '—', custo: '—', detalhe: 'Menor custo · lance',
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

export const ROTULOS_META: Record<TipoMeta, { singular: string; plural: string }> = {
  campanhas: { singular: 'campanha', plural: 'campanhas' },
  conjuntos: { singular: 'conjunto', plural: 'conjuntos' },
  anuncios: { singular: 'anúncio', plural: 'anúncios' },
  criativos: { singular: 'criativo', plural: 'criativos' },
};

export function objetoMetaDemo(tipo: TipoMeta, id: string): ObjetoMetaDemo | undefined {
  return META_DEMO[tipo].find((objeto) => objeto.id === id);
}
