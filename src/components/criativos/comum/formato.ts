/**
 * Formatação que preserva a diferença entre "não medido" e "medido e deu X".
 *
 * O contrato guarda `number | null` em toda medida justamente para que esta
 * camada não possa achatar os dois. Um `?? 0` aqui desfaria o trabalho do
 * contrato inteiro: `bytes: null` viraria `0 B`, que é uma afirmação sobre um
 * arquivo que ninguém abriu.
 *
 * A saída é sempre uma FRASE, nunca um traço: "não medido" diz o que aconteceu,
 * "—" obriga quem lê a adivinhar entre ausência, zero e defeito de tela.
 */

export const NAO_MEDIDO = 'não medido';
export const NAO_INFORMADO = 'não informado';

export function dimensoes(largura: number | null, altura: number | null): string {
  if (largura === null || altura === null) return NAO_MEDIDO;
  return `${largura} x ${altura} px`;
}

export function bytesLegiveis(bytes: number | null): string {
  if (bytes === null) return NAO_MEDIDO;
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} kB`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
}

export function duracaoLegivel(ms: number | null): string {
  if (ms === null) return NAO_MEDIDO;
  const total = Math.round(ms / 1000);
  const minutos = Math.floor(total / 60);
  const segundos = total % 60;
  if (minutos === 0) return `${segundos}s`;
  return `${minutos}min ${String(segundos).padStart(2, '0')}s`;
}

export function segundosLegiveis(s: number | null): string {
  if (s === null) return NAO_MEDIDO;
  return `${Number.isInteger(s) ? s : s.toFixed(1)}s`;
}

/**
 * Custo em dólar. `null` é "não apurado", que não é grátis.
 *
 * Quatro casas porque uma peça costuma custar centavos de centavo, e arredondar
 * para duas transformaria a maioria dos custos reais em `US$ 0,00`, ou seja, em
 * "de graça" para quem lê rápido.
 */
export function custoLegivel(usd: number | null): string {
  if (usd === null) return 'custo não apurado';
  return `US$ ${usd.toFixed(4)}`;
}

/**
 * O custo de um JOB, dizendo qual dos dois custos está na tela.
 *
 * ⚠️ Conserto de um colapso medido (defeito D2 da auditoria P17). `JobPage` e
 * `home/Linhas` escreviam `custoLegivel(job.custoRealUsd ?? job.custoEstimadoUsd)`.
 * O `??` funde dois campos que o contrato guarda separados de propósito, e o
 * resultado é uma frase única — "US$ 0.0300" — que quem lê o cabeçalho de um job
 * em execução entende como gasto REALIZADO. Estimativa não é apuração: a
 * primeira é o que o motor achou que ia custar antes de rodar, a segunda é o que
 * o provider cobrou. Um relatório de COGS montado a partir da leitura errada
 * fecha bonito e está errado.
 *
 * `0` continua sendo zero MEDIDO — o erro simétrico (achatar zero apurado em
 * "não apurado") seria igualmente falso.
 */
export function custoDoJobLegivel(
  custoRealUsd: number | null,
  custoEstimadoUsd: number | null,
): string {
  if (custoRealUsd !== null) return `${custoLegivel(custoRealUsd)} apurado`;
  if (custoEstimadoUsd !== null) {
    return `${custoLegivel(custoEstimadoUsd)} de estimativa; custo real não apurado`;
  }
  return 'custo não apurado';
}

export function instante(iso: string | null): string {
  if (!iso) return NAO_INFORMADO;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NAO_INFORMADO;
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function dia(iso: string | null): string {
  if (!iso) return NAO_INFORMADO;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NAO_INFORMADO;
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/**
 * Hash encurtado para caber na tela, com o valor inteiro acessível no `title`.
 *
 * ⚠️ NUNCA use isto com `insumoHash` rotulado como prompt. O hash do insumo é a
 * prova de que dois pedidos foram iguais, não o texto do pedido, e o texto do
 * pedido não chega ao browser por decisão de contrato.
 */
export function hashCurto(hash: string | null): string {
  if (!hash) return NAO_INFORMADO;
  return hash.length <= 16 ? hash : `${hash.slice(0, 10)}…${hash.slice(-4)}`;
}

export function mimeLegivel(mime: string | null): string {
  return mime && mime.trim() ? mime : NAO_INFORMADO;
}

/** Nome de destino em linguagem de operação, com fallback que não mente. */
const NOME_DO_DESTINO: Record<string, string> = {
  google_display: 'Google Display',
  google_demand_gen: 'Demand Gen',
  meta_feed: 'Meta feed',
  meta_stories_reels: 'Meta stories e reels',
  instagram_organic: 'Instagram orgânico',
  youtube_shorts: 'YouTube Shorts',
  manual: 'Exportação manual',
};

export function destinoLegivel(destino: string): string {
  return NOME_DO_DESTINO[destino] ?? destino.replace(/_/g, ' ');
}

const NOME_DO_KIND: Record<string, string> = {
  imagem: 'Imagem',
  video: 'Vídeo',
  audio: 'Áudio',
  texto: 'Texto',
  logo: 'Logo',
  auxiliar: 'Auxiliar',
};

export function kindLegivel(kind: string): string {
  return NOME_DO_KIND[kind] ?? kind;
}

const NOME_DO_ENQUADRAMENTO: Record<string, { palavra: string; descricao: string }> = {
  nativo: {
    palavra: 'Nativo',
    descricao: 'O motor entregou já nesta dimensão, sem redimensionar.',
  },
  resize: {
    palavra: 'Redimensionado',
    descricao: 'O arquivo original foi escalado para chegar nesta dimensão.',
  },
  cover_crop: {
    palavra: 'Recortado',
    descricao: 'Parte da imagem original ficou fora para preencher esta proporção.',
  },
  recomposto: {
    palavra: 'Recomposto',
    descricao: 'A cena foi remontada para esta proporção, não apenas cortada.',
  },
  /**
   * ⚠️ O contrato declara este enquadramento desde a v11; o mapa é que estava
   * sem ele (defeito D4 da auditoria P17), então a tela imprimia o slug cru
   * `nao_normalizado` com a descrição "que esta versão da tela não conhece" —
   * rebaixando um MISMATCH DECLARADO a estado desconhecido. A tela conhece.
   */
  nao_normalizado: {
    palavra: 'Fora da dimensão pedida',
    descricao:
      'A normalização não pôde rodar. A peça ficou na dimensão que o provider entregou, diferente da pedida.',
  },
};

export function enquadramentoLegivel(
  enquadramento: string | null,
): { palavra: string; descricao: string } {
  if (!enquadramento) {
    return {
      palavra: 'Enquadramento não registrado',
      descricao: 'Ninguém registrou como esta peça chegou na dimensão pedida.',
    };
  }
  return (
    NOME_DO_ENQUADRAMENTO[enquadramento] ?? {
      palavra: enquadramento,
      descricao: 'Enquadramento declarado pelo motor que esta versão da tela não conhece.',
    }
  );
}
