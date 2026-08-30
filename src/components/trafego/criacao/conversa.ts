/**
 * A conversa de criação — a máquina de etapas, pura.
 *
 * ## Não é o formulário da API
 *
 * A API de Search pede dezenas de campos. Um formulário que os despejasse na
 * tela obrigaria o operador a saber a API para responder, e o VOLC O.S. existe
 * exatamente para ele não precisar. A conversa pergunta o que decide, na ordem
 * em que uma resposta restringe a seguinte: objetivo restringe conta, conta
 * restringe canal, canal restringe o que pode ser perguntado depois.
 *
 * ## Os cinco portões do fim são cinco perguntas diferentes
 *
 *  - `validacao_local` — as regras da casa passam? (não sai da máquina)
 *  - `prova` — a conta aceita o pedido? (`validate_only`: valida e descarta)
 *  - `aprovacao` — uma pessoa autoriza este gasto?
 *  - `criacao` — criar, PAUSADA (não entra em leilão, não gasta)
 *  - `ativacao` — ligar. É esta que faz gastar, e por isso é separada
 *
 * Juntar `criacao` e `ativacao` num botão só é o que transforma gasto em
 * clique. Elas ficam separadas mesmo quando a intenção é obviamente subir e
 * ligar: a separação é o que dá um lugar para conferir o que foi criado antes
 * de ele começar a custar.
 *
 * Módulo puro: sem React, sem HTTP, sem Google Ads.
 */
import {
  ETAPAS_DA_CRIACAO,
  type DependenciaDeAplicacao,
  type EtapaDaCriacao,
  type PassoDaCriacao,
} from '@/types/diagnostico';
import type { ManifestoDeCanal } from '@/types/trafego';

/** O que cada etapa pergunta. Uma frase, na língua de quem opera. */
export const PERGUNTA: Record<EtapaDaCriacao, string> = {
  objetivo: 'o que esta campanha precisa produzir, e em que etapa do funil?',
  conta: 'em que conta de anúncio e em que canal ela vive?',
  destino: 'para onde o clique leva?',
  conversao: 'o que conta como resultado, e quem registra isso?',
  targeting: 'quem deve ver, em que lugar e em que idioma?',
  orcamento: 'quanto por dia, e como pagar o leilão?',
  criativos: 'com que títulos, descrições e assets?',
  revisao: 'o pedido inteiro está certo?',
  validacao_local: 'as regras da casa passam sem sair desta máquina?',
  prova: 'a conta de anúncio aceita este pedido sem criar nada?',
  aprovacao: 'quem autoriza este gasto?',
  criacao: 'criar na conta, pausada?',
  ativacao: 'ligar? é esta decisão que faz a campanha gastar.',
};

/** O rótulo curto da etapa, para o trilho lateral. */
export const ROTULO_DA_ETAPA: Record<EtapaDaCriacao, string> = {
  objetivo: 'Objetivo e funil',
  conta: 'Conta e canal',
  destino: 'Destino',
  conversao: 'Conversão',
  targeting: 'Segmentação',
  orcamento: 'Orçamento e lance',
  criativos: 'Criativos',
  revisao: 'Revisão',
  validacao_local: 'Validação local',
  prova: 'Prova contra a conta',
  aprovacao: 'Aprovação',
  criacao: 'Criação pausada',
  ativacao: 'Ativação',
};

export interface EntradaDaConversa {
  /** `null` = o Hub não opera este canal. A conversa inteira não existe. */
  manifesto: ManifestoDeCanal | null;
  /** As respostas já dadas, já legíveis. */
  respostas: Partial<Record<EtapaDaCriacao, string>>;
  /**
   * A trava de escrita, lida do servidor.
   *
   * ⚠️ `null` significa NÃO APURADO, e trava não apurada nunca é tratada como
   * aberta. A leitura otimista aqui custaria uma campanha criada por engano.
   */
  travaAberta: boolean | null;
  /** Se quem está nesta tela pode assinar a aprovação. */
  podeAprovar: boolean;
}

const DEP: Record<string, DependenciaDeAplicacao> = {
  semManifesto: {
    dependencia: 'o Hub não declara construtor para este canal.',
    destrava: 'manifesto',
  },
  semCriacao: {
    dependencia: 'o manifesto deste canal não autoriza criação.',
    destrava: 'manifesto',
  },
  semPapel: {
    dependencia: 'assinar esta aprovação exige um papel que esta conta não tem.',
    destrava: 'papel',
  },
  travaFechada: {
    dependencia: 'a trava de escrita está fechada. Ela é aberta fora desta tela.',
    destrava: 'trava',
  },
  travaNaoLida: {
    dependencia:
      'o estado da trava de escrita não foi lido. Enquanto não se sabe se ela está aberta, esta etapa fica fechada.',
    destrava: 'trava',
  },
  semProva: {
    dependencia: 'a prova contra a conta ainda não passou.',
    destrava: 'prova',
  },
  semCriacaoFeita: {
    dependencia: 'não há campanha criada para ligar.',
    destrava: 'endpoint',
  },
};

/**
 * Monta a conversa inteira, com o estado de cada etapa.
 *
 * A lista sai SEMPRE completa, inclusive as etapas que não se aplicam a este
 * canal. Omitir uma etapa faria o operador contar treze numa campanha e onze
 * noutra sem saber por quê; `nao_se_aplica` diz que aquela pergunta não existe
 * aqui, que é informação e não ruído.
 */
export function montarConversa(entrada: EntradaDaConversa): PassoDaCriacao[] {
  const { manifesto, respostas, travaAberta, podeAprovar } = entrada;

  if (manifesto == null) {
    return ETAPAS_DA_CRIACAO.map((etapa) => ({
      etapa,
      estado: 'bloqueada' as const,
      pergunta: PERGUNTA[etapa],
      resposta: null,
      dependencia: DEP.semManifesto,
    }));
  }
  if (!manifesto.sabe_criar) {
    const recusa: DependenciaDeAplicacao = {
      dependencia:
        manifesto.indisponibilidades[0] ?? DEP.semCriacao.dependencia,
      destrava: 'manifesto',
    };
    return ETAPAS_DA_CRIACAO.map((etapa) => ({
      etapa,
      estado: 'bloqueada' as const,
      pergunta: PERGUNTA[etapa],
      resposta: null,
      dependencia: recusa,
    }));
  }

  const naoSeAplica = etapasQueNaoSeAplicam(manifesto);
  let jaMarcouAtual = false;

  return ETAPAS_DA_CRIACAO.map((etapa) => {
    const resposta = respostas[etapa] ?? null;
    const base = { etapa, pergunta: PERGUNTA[etapa], resposta };

    if (naoSeAplica.has(etapa)) {
      return { ...base, estado: 'nao_se_aplica' as const, resposta: null, dependencia: null };
    }

    const trava = travaDaEtapa(etapa, { travaAberta, podeAprovar, respostas });
    if (trava) {
      return { ...base, estado: 'bloqueada' as const, dependencia: trava };
    }

    if (resposta != null) {
      return { ...base, estado: 'respondida' as const, dependencia: null };
    }
    if (!jaMarcouAtual) {
      jaMarcouAtual = true;
      return { ...base, estado: 'atual' as const, dependencia: null };
    }
    return { ...base, estado: 'pendente' as const, dependencia: null };
  });
}

/**
 * As etapas que este canal não pede.
 *
 * Deriva de `campos_do_pedido`, que é o que o backend declara saber receber.
 * Um canal cujo pedido não tem campo de conversão não ganha a pergunta de
 * conversão — inventá-la produziria uma resposta que ninguém sabe usar.
 */
export function etapasQueNaoSeAplicam(manifesto: ManifestoDeCanal): Set<EtapaDaCriacao> {
  const campos = manifesto.campos_do_pedido.join(' ').toLowerCase();
  const fora = new Set<EtapaDaCriacao>();
  if (campos.length > 0 && !/convers/.test(campos)) fora.add('conversao');
  return fora;
}

function travaDaEtapa(
  etapa: EtapaDaCriacao,
  ctx: {
    travaAberta: boolean | null;
    podeAprovar: boolean;
    respostas: Partial<Record<EtapaDaCriacao, string>>;
  },
): DependenciaDeAplicacao | null {
  if (etapa === 'aprovacao' && !ctx.podeAprovar) return DEP.semPapel;
  if (etapa === 'criacao') {
    if (ctx.respostas.prova == null) return DEP.semProva;
    if (ctx.travaAberta == null) return DEP.travaNaoLida;
    if (ctx.travaAberta === false) return DEP.travaFechada;
  }
  if (etapa === 'ativacao' && ctx.respostas.criacao == null) return DEP.semCriacaoFeita;
  return null;
}

/** A etapa em que a conversa está agora. `null` quando não há nenhuma jogável. */
export function etapaAtual(passos: PassoDaCriacao[]): EtapaDaCriacao | null {
  return passos.find((p) => p.estado === 'atual')?.etapa ?? null;
}

export interface ProgressoDaConversa {
  respondidas: number;
  /** Só as etapas que se aplicam. `nao_se_aplica` não entra na conta. */
  aplicaveis: number;
  /** Etapas bloqueadas — visíveis na contagem para não parecerem opcionais. */
  bloqueadas: number;
}

export function progressoDaConversa(passos: PassoDaCriacao[]): ProgressoDaConversa {
  const aplicaveis = passos.filter((p) => p.estado !== 'nao_se_aplica');
  return {
    respondidas: aplicaveis.filter((p) => p.estado === 'respondida').length,
    aplicaveis: aplicaveis.length,
    bloqueadas: aplicaveis.filter((p) => p.estado === 'bloqueada').length,
  };
}
