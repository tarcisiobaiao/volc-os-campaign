/**
 * Regras puras dos primitivos V3 "Instrumento" (design.md §V3).
 *
 * Nada aqui conhece React, rede ou Supabase. Os componentes de
 * `src/components/sistema/` só desenham o que estas funções decidem, e é aqui
 * que mora a lei que o PRODUCT.md §4 impõe a todo número da interface:
 *
 *   - ausência não vira zero;
 *   - sem base de comparação não existe variação;
 *   - subir não é "bom" até alguém dizer o sentido da métrica;
 *   - data no futuro não é "agora".
 */

export const AUSENTE = '—';

// ── formatação ──────────────────────────────────────────────────────────────

export type FormatoDeNumero =
  | { tipo: 'inteiro' }
  | { tipo: 'decimal'; casas?: number }
  | { tipo: 'moeda'; moeda: string; casas?: number }
  | { tipo: 'percentual'; casas?: number }
  /** ROAS, multiplicador: 0,07× */
  | { tipo: 'razao'; casas?: number };

/**
 * Formata em pt-BR. `null`/`undefined`/`NaN` devolvem o travessão — nunca "0".
 * Percentual recebe a FRAÇÃO (0,125 → 12,5%), como o Intl.
 */
export function formatarNumero(valor: number | null | undefined, formato: FormatoDeNumero): string {
  if (valor == null || Number.isNaN(valor)) return AUSENTE;
  switch (formato.tipo) {
    case 'inteiro':
      return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(valor);
    case 'decimal': {
      const casas = formato.casas ?? 2;
      return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(valor);
    }
    case 'moeda': {
      const casas = formato.casas ?? 2;
      return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: formato.moeda,
        minimumFractionDigits: casas,
        maximumFractionDigits: casas,
      }).format(valor);
    }
    case 'percentual': {
      const casas = formato.casas ?? 1;
      return new Intl.NumberFormat('pt-BR', {
        style: 'percent',
        minimumFractionDigits: casas,
        maximumFractionDigits: casas,
      }).format(valor);
    }
    case 'razao': {
      const casas = formato.casas ?? 2;
      return `${new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(valor)}×`;
    }
  }
}

// ── variação ────────────────────────────────────────────────────────────────

/** Quem diz se subir é bom é a métrica, não o componente. */
export type Sentido = 'maior-melhor' | 'menor-melhor' | 'neutro';

export type Direcao = 'sobe' | 'desce' | 'igual' | 'desconhecida';
export type TomDoDelta = 'bom' | 'ruim' | 'neutro';

export type AvaliacaoDeDelta = {
  direcao: Direcao;
  /** Fração (0,12 = +12%). `null` quando não há base para dividir. */
  fracao: number | null;
  tom: TomDoDelta;
};

/**
 * Compara o valor atual com a base.
 *
 * ⚠️ Base zero não produz percentual: de 0 para 10 não é "+∞%" nem "+100%".
 * A direção ainda é conhecida, a magnitude relativa não.
 */
export function avaliarDelta(
  atual: number | null | undefined,
  base: number | null | undefined,
  sentido: Sentido,
): AvaliacaoDeDelta {
  if (atual == null || base == null || Number.isNaN(atual) || Number.isNaN(base)) {
    return { direcao: 'desconhecida', fracao: null, tom: 'neutro' };
  }
  const diferenca = atual - base;
  const direcao: Direcao = diferenca > 0 ? 'sobe' : diferenca < 0 ? 'desce' : 'igual';
  const fracao = base === 0 ? null : diferenca / Math.abs(base);
  let tom: TomDoDelta = 'neutro';
  if (direcao !== 'igual' && sentido !== 'neutro') {
    const subiu = direcao === 'sobe';
    tom = (sentido === 'maior-melhor') === subiu ? 'bom' : 'ruim';
  }
  return { direcao, fracao, tom };
}

// ── frescor ─────────────────────────────────────────────────────────────────

export type NivelDeFrescor = 'nunca' | 'futuro' | 'fresco' | 'envelhecido' | 'vencido';

export type LimitesDeFrescor = {
  /** A partir de quantos minutos a leitura fica envelhecida. */
  envelhecidoMin: number;
  /** A partir de quantos minutos a leitura está vencida para decidir. */
  vencidoMin: number;
};

/** Padrão para leituras de conta de mídia (custo D-1 vence em um dia). */
export const LIMITES_PADRAO: LimitesDeFrescor = { envelhecidoMin: 60, vencidoMin: 24 * 60 };

/** Tolerância de relógio entre servidor e navegador, como em `inventario/formato`. */
const TOLERANCIA_DE_RELOGIO_S = 120;

export function nivelDeFrescor(
  lidoEm: string | Date | null | undefined,
  agora: Date,
  limites: LimitesDeFrescor = LIMITES_PADRAO,
): { nivel: NivelDeFrescor; segundos: number | null } {
  if (lidoEm == null) return { nivel: 'nunca', segundos: null };
  const instante = lidoEm instanceof Date ? lidoEm : new Date(lidoEm);
  if (Number.isNaN(instante.getTime())) return { nivel: 'nunca', segundos: null };
  const segundos = Math.round((agora.getTime() - instante.getTime()) / 1000);
  if (segundos < -TOLERANCIA_DE_RELOGIO_S) return { nivel: 'futuro', segundos };
  const minutos = Math.max(0, segundos) / 60;
  if (minutos >= limites.vencidoMin) return { nivel: 'vencido', segundos };
  if (minutos >= limites.envelhecidoMin) return { nivel: 'envelhecido', segundos };
  return { nivel: 'fresco', segundos };
}

// ── sparkline ───────────────────────────────────────────────────────────────

export type GeometriaDaSparkline = {
  /** Um `d` de path por trecho contínuo. Um `null` na série abre um novo trecho. */
  trechos: string[];
  /** Pontos isolados (trecho de um ponto só), desenhados como marca. */
  isolados: Array<{ x: number; y: number }>;
  /** Último ponto observado, se houver. */
  final: { x: number; y: number } | null;
  /** Quantos pontos da série são ausência. */
  lacunas: number;
};

const arred = (n: number) => Math.round(n * 100) / 100;

/**
 * Converte a série em geometria SVG.
 *
 * ⚠️ Ausência quebra a linha. Interpolar por cima de um dia sem leitura, ou
 * descer a linha a zero, desenharia um fato que ninguém mediu.
 */
export function geometriaDaSparkline(
  valores: ReadonlyArray<number | null>,
  largura: number,
  altura: number,
  respiro = 2,
): GeometriaDaSparkline {
  const medidos = valores.filter((v): v is number => v != null && !Number.isNaN(v));
  const lacunas = valores.length - medidos.length;
  if (medidos.length === 0) return { trechos: [], isolados: [], final: null, lacunas };

  const min = Math.min(...medidos);
  const max = Math.max(...medidos);
  const passo = valores.length > 1 ? (largura - respiro * 2) / (valores.length - 1) : 0;
  const util = altura - respiro * 2;
  const y = (v: number) => (max === min ? altura / 2 : respiro + util - ((v - min) / (max - min)) * util);
  const x = (i: number) => (valores.length > 1 ? respiro + i * passo : largura / 2);

  const trechos: string[] = [];
  const isolados: Array<{ x: number; y: number }> = [];
  let atual: Array<{ x: number; y: number }> = [];
  let final: { x: number; y: number } | null = null;

  const fechar = () => {
    if (atual.length === 1) isolados.push(atual[0]);
    else if (atual.length > 1) {
      trechos.push(atual.map((p, k) => `${k === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' '));
    }
    atual = [];
  };

  valores.forEach((v, i) => {
    if (v == null || Number.isNaN(v)) {
      fechar();
      return;
    }
    const p = { x: arred(x(i)), y: arred(y(v)) };
    atual.push(p);
    final = p;
  });
  fechar();

  return { trechos, isolados, final, lacunas };
}

// ── ciclo fato → recomendação → autorização → ação (P09) ────────────────────

export type EstadoDeProposta =
  | 'sombra'
  | 'proposta'
  | 'aguardando'
  | 'aprovada'
  | 'aplicada'
  | 'recusada'
  | 'vencida'
  | 'revertida';

export const ESTADO_DE_PROPOSTA: Record<
  EstadoDeProposta,
  { glifo: string; palavra: string; descricao: string }
> = {
  sombra: {
    glifo: '◇',
    palavra: 'Sombra · não executada',
    descricao: 'O motor recomendou em modo sombra. Nada foi enviado à conta.',
  },
  proposta: {
    glifo: '◇',
    palavra: 'Proposta',
    descricao: 'Registrada na fila de propostas. Ainda não foi decidida.',
  },
  aguardando: {
    glifo: '◐',
    palavra: 'Aguardando aprovação',
    descricao: 'Precisa de uma decisão humana antes de qualquer escrita.',
  },
  aprovada: {
    glifo: '◆',
    palavra: 'Aprovada · ainda não aplicada',
    descricao: 'Uma pessoa aprovou. A conta ainda não recebeu a mudança.',
  },
  aplicada: {
    glifo: '●',
    palavra: 'Aplicada · com recibo',
    descricao: 'A mudança foi lida de volta na conta e tem recibo.',
  },
  recusada: { glifo: '✕', palavra: 'Recusada', descricao: 'Uma pessoa recusou. Nada foi enviado.' },
  vencida: { glifo: '◌', palavra: 'Vencida', descricao: 'A evidência envelheceu antes da decisão.' },
  revertida: { glifo: '↺', palavra: 'Revertida', descricao: 'Aplicada e depois desfeita, com recibo.' },
};
