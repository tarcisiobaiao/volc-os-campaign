import type { EtapaId } from './rascunho';

/** Navigation only. The canonical draft and server compiler retain ownership of payloads. */
export const PERGUNTAS_META = [
  { id: 'conta', etapa: 'base', titulo: 'Em qual conta vamos trabalhar?', ajuda: 'Conecte a conta que vai receber esta campanha.', nome: 'Conta' },
  { id: 'pagina', etapa: 'base', titulo: 'Quem assina seus anúncios?', ajuda: 'Escolha a Página que seu público vai reconhecer.', nome: 'Página' },
  { id: 'destino', etapa: 'campanha', titulo: 'Qual página você quer anunciar?', ajuda: 'Cole o endereço da matéria ou landing page. Vamos identificar o assunto e organizar os nomes desta conta.', nome: 'Destino' },
  { id: 'resultado', etapa: 'campanha', titulo: 'O que você quer que aconteça?', ajuda: 'Escolha como a Meta deve procurar as pessoas para esta campanha.', nome: 'Resultado' },
  { id: 'conversao', etapa: 'mensuracao', titulo: 'Qual ação vale uma conversão?', ajuda: 'Escolha uma conversão existente na conta. A receita do GAM continua sendo medida por conjunto.', nome: 'Conversão' },
  { id: 'publico', etapa: 'publico', titulo: 'Quem você quer alcançar?', ajuda: 'Defina a localização e o público. Abra os ajustes se precisar refinar.', nome: 'Público' },
  { id: 'orcamento', etapa: 'orcamento', titulo: 'Qual é o orçamento?', ajuda: 'Escolha o valor e como ele será distribuído.', nome: 'Orçamento' },
  { id: 'conjuntos', etapa: 'conjunto', titulo: 'Como você quer organizar o teste?', ajuda: 'Um conjunto reúne público, orçamento e anúncios. Você pode começar com um só.', nome: 'Conjuntos' },
  { id: 'criativos', etapa: 'criativo', titulo: 'Vamos dar forma à campanha?', ajuda: 'Crie com o assistente ou escolha imagens que já estão na conta.', nome: 'Criativos' },
  { id: 'revisao', etapa: 'revisao', titulo: 'Tudo pronto para conferir?', ajuda: 'Confira o plano no servidor antes de validar ou autorizar qualquer criação.', nome: 'Revisão' },
] as const satisfies readonly { id: string; etapa: EtapaId; titulo: string; ajuda: string; nome: string }[];

export type PerguntaMeta = typeof PERGUNTAS_META[number];
export function perguntasMeta(conversao: boolean) {
  return PERGUNTAS_META.filter(p => conversao || p.id !== 'conversao');
}
export function perguntaDaUrl(params: URLSearchParams, conversao: boolean): PerguntaMeta {
  const perguntas = perguntasMeta(conversao);
  return perguntas.find(p => p.id === params.get('pergunta'))
    ?? perguntas.find(p => p.etapa === params.get('etapa')) ?? perguntas[0];
}
