/**
 * A Camada 2 no cliente — espelho do contrato de `app.validacao.oportunidade`.
 *
 * Este arquivo não deriva nada. A tese é montada no Python, determinística, e
 * aqui só existe o vocabulário para desenhá-la. Se aparecer uma conta neste
 * arquivo, ela está no lugar errado: o cliente exibe procedência, não a produz.
 */

export const VERSAO_DO_CONTRATO = 'oportunidade/1';

export type DecisaoDeOportunidade =
  | 'aprofundar'
  | 'experimentar'
  | 'insuficiente'
  | 'inadequado'
  | 'retido'
  | 'sem_validacao';

export interface TeseDeOportunidade {
  opportunity_id?: number;
  tema: string;
  decisao: DecisaoDeOportunidade;
  porque: string;
  versao_do_contrato: string;
  formato_de_funil: string | null;
  observaveis_do_formato: string[];
  fatos: string[];
  hipoteses: string[];
  desconhecidos: string[];
  contradicoes: string[];
  proximo_experimento: string | null;
  indice_citado: number | null;
  cobertura: number | null;
  perfil_citado: string | null;
  comparavel: boolean;
  motivo_incomparavel: string | null;
}

export interface TesesResposta {
  teses: TeseDeOportunidade[];
  ranking: TeseDeOportunidade[];
  fora_do_ranking: TeseDeOportunidade[];
  total: number;
}

/**
 * Glifo + palavra + frase. Nunca só cor.
 *
 * `tom` alimenta um token semântico do design system, e ele NUNCA é aurora:
 * aurora é assinatura de identidade, não estado operacional. `inadequado` e
 * `insuficiente` compartilham a mesma prioridade e divergem no que se faz
 * depois — por isso palavras diferentes, e não dois tons da mesma cor.
 */
export const DECISAO_HUMANA: Record<
  DecisaoDeOportunidade,
  { glifo: string; palavra: string; frase: string; tom: string; acao: string }
> = {
  aprofundar: {
    glifo: '●',
    palavra: 'Aprofundar',
    frase: 'Ramifica de verdade e sustenta um funil.',
    tom: 'success',
    acao: 'Escrever o funil',
  },
  experimentar: {
    glifo: '◐',
    palavra: 'Experimentar',
    frase: 'Promissor, com um buraco barato de fechar antes.',
    tom: 'warning',
    acao: 'Rodar o experimento abaixo',
  },
  insuficiente: {
    glifo: '○',
    palavra: 'Cabe numa página',
    frase: 'Não é tema ruim — é tema que não pede funil.',
    tom: 'muted',
    acao: 'Considerar artigo único',
  },
  inadequado: {
    glifo: '⊘',
    palavra: 'Não pede funil',
    frase: 'Medido, e a estrutura não sustenta a jornada.',
    tom: 'destructive',
    acao: 'Arquivar ou revisar a entidade',
  },
  retido: {
    glifo: '◌',
    palavra: 'Sem base para comparar',
    frase: 'Cobertura abaixo do mínimo. Medir antes de priorizar.',
    tom: 'info',
    acao: 'Medir os eixos que faltam',
  },
  sem_validacao: {
    glifo: '·',
    palavra: 'Nunca medido',
    frase: 'Lacuna declarada, não veredito sobre o tema.',
    tom: 'muted',
    acao: 'Arrastar para Em validação',
  },
};

export const FORMATO_HUMANO: Record<string, { nome: string; explica: string }> = {
  ferramenta_de_elegibilidade: {
    nome: 'Ferramenta de elegibilidade',
    explica: 'Condições pessoais mudam a resposta: a página pergunta antes de responder.',
  },
  comparador_de_caminhos: {
    nome: 'Comparador de caminhos',
    explica: 'Caminhos levam a ações diferentes: a página põe lado a lado.',
  },
  guia_sequencial: {
    nome: 'Guia sequencial',
    explica: 'Muitas perguntas encadeadas, sem ramificação que exija ferramenta.',
  },
  resposta_unica: {
    nome: 'Resposta única',
    explica: 'A resposta cabe inteira em uma página.',
  },
};

/**
 * Os três conjuntos, e por que são três.
 *
 * Um fato foi medido ou contado. Uma hipótese veio de fora e não decide nada.
 * Um desconhecido é buraco declarado. Achatar os três num "score de confiança"
 * é exatamente o que esta tela existe para não fazer.
 */
export const PROCEDENCIA_HUMANA = {
  fatos: { glifo: '◆', titulo: 'Fatos', explica: 'Medido por sensor ou contado sobre a resposta escrita.' },
  hipoteses: { glifo: '◇', titulo: 'Hipóteses', explica: 'Vem de fora deste card. Não move a decisão.' },
  desconhecidos: { glifo: '·', titulo: 'Desconhecidos', explica: 'Buraco declarado. Não é zero.' },
  contradicoes: { glifo: '≠', titulo: 'Contradições', explica: 'Dois sinais discordam. Ninguém resolveu por você.' },
} as const;

export const ORDEM_DA_DECISAO: DecisaoDeOportunidade[] = [
  'aprofundar', 'experimentar', 'insuficiente', 'inadequado', 'retido', 'sem_validacao',
];
