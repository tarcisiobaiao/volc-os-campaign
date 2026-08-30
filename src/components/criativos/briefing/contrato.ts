/**
 * O rascunho de um briefing de imagem, e as regras que decidem quando ele pode
 * virar um pedido real.
 *
 * ## Por que a validação mora aqui e não no componente
 *
 * Porque a mesma regra precisa valer em três lugares: para habilitar o avanço
 * de etapa, para desenhar o erro do campo e para montar o `PedidoDeJobDeImagem`.
 * Três cópias divergem no dia em que alguém muda o mínimo de caracteres da
 * mensagem, e a divergência aparece como um botão habilitado que o servidor
 * recusa depois do trabalho todo feito.
 *
 * ## O que este módulo NÃO faz
 *
 * Não chama rede, não guarda nada em `localStorage` e não decide custo. Custo é
 * do servidor; a tela só declara que vai existir uma chamada real por peça, que
 * é o fato que o operador precisa saber ANTES de clicar.
 */
import type {
  FormatoDisponivel,
  ModoDeProducao,
  PedidoDeJobDeImagem,
} from '@/types/criativos';

export const ETAPAS = ['intencao', 'formatos', 'mensagem', 'marca', 'revisao'] as const;
export type EtapaDoBriefing = (typeof ETAPAS)[number];

export const TITULO_DA_ETAPA: Record<EtapaDoBriefing, string> = {
  intencao: 'Intenção e destino',
  formatos: 'Formatos',
  mensagem: 'Mensagem e conteúdo',
  marca: 'Brand pack',
  revisao: 'Revisão do contrato',
};

export const RESUMO_DA_ETAPA: Record<EtapaDoBriefing, string> = {
  intencao: 'Para que serve esta peça e onde você pretende usá-la.',
  formatos: 'Quais proporções o motor deve entregar.',
  mensagem: 'O que a peça precisa dizer, e para quem.',
  marca: 'Qual identidade visual governa a composição.',
  revisao: 'O que será gerado, e o que isso custa.',
};

export interface RascunhoDeImagem {
  projetoTitulo: string;
  objetivo: string;
  mensagem: string;
  audiencia: string;
  brandPackId: string;
  modo: ModoDeProducao;
  slots: string[];
  destinosPretendidos: string[];
}

export const RASCUNHO_VAZIO: RascunhoDeImagem = {
  projetoTitulo: '',
  objetivo: '',
  mensagem: '',
  audiencia: '',
  brandPackId: '',
  modo: 'full_llm',
  slots: [],
  destinosPretendidos: [],
};

// ── modos ───────────────────────────────────────────────────────────────────

export interface OfertaDeModo {
  modo: ModoDeProducao;
  rotulo: string;
  /** O que o operador ganha ao escolher, em termos de finalidade. */
  descricao: string;
  disponivel: boolean;
  /** Por que ainda não dá para escolher. `null` só quando `disponivel`. */
  motivo: string | null;
}

/**
 * Os seis modos do ADR-001, com a verdade sobre quais existem hoje.
 *
 * ⚠️ Os cinco indisponíveis aparecem de propósito, DESABILITADOS e com motivo.
 * Escondê-los faria a tela prometer que só existe um caminho; oferecê-los sem
 * marca faria a tela prometer capacidade que não existe. O DESIGN.md pede a
 * terceira via: "Explain why an action is unavailable and what prerequisite is
 * missing."
 */
export const MODOS: readonly OfertaDeModo[] = [
  {
    modo: 'full_llm',
    rotulo: 'Composição por modelo',
    descricao: 'O motor compõe a peça inteira a partir da mensagem. Uma chamada real por peça.',
    disponivel: true,
    motivo: null,
  },
  {
    modo: 'typography_only',
    rotulo: 'Só tipografia',
    descricao: 'Texto sobre fundo do brand pack, sem geração de imagem.',
    disponivel: false,
    motivo: 'O compositor tipográfico ainda não está ligado neste ambiente.',
  },
  {
    modo: 'deterministic_graphics',
    rotulo: 'Gráfico determinístico',
    descricao: 'Peça montada por regra, igual a cada execução, sem modelo generativo.',
    disponivel: false,
    motivo: 'O compositor determinístico ainda não está ligado neste ambiente.',
  },
  {
    modo: 'photo_preserved',
    rotulo: 'Foto real preservada',
    descricao: 'Parte de uma foto sua e a mantém intacta na composição.',
    disponivel: false,
    motivo: 'Depende do envio de insumo próprio, que ainda não existe nesta tela.',
  },
  {
    modo: 'prensa_hybrid',
    rotulo: 'Prensa híbrida',
    descricao: 'Fundo gerado e texto prensado por regra, para copy exata.',
    disponivel: false,
    motivo: 'A prensa ainda não está ligada neste ambiente.',
  },
  {
    modo: 'full_llm_then_prensa',
    rotulo: 'Modelo e depois prensa',
    descricao: 'O motor compõe, a prensa corrige a copy.',
    disponivel: false,
    motivo: 'A prensa ainda não está ligada neste ambiente.',
  },
] as const;

export function modoDisponivel(modo: ModoDeProducao): boolean {
  return MODOS.some((m) => m.modo === modo && m.disponivel);
}

// ── destinos pretendidos ────────────────────────────────────────────────────

export interface OfertaDeDestino {
  destino: string;
  rotulo: string;
  descricao: string;
}

export const DESTINOS: readonly OfertaDeDestino[] = [
  {
    destino: 'google_display',
    rotulo: 'Google Display',
    descricao: 'Rede de display do Google Ads.',
  },
  {
    destino: 'meta_feed',
    rotulo: 'Meta feed',
    descricao: 'Feed de Facebook e Instagram.',
  },
  {
    destino: 'meta_stories_reels',
    rotulo: 'Meta stories e reels',
    descricao: 'Tela cheia de stories e reels.',
  },
  {
    destino: 'instagram_organic',
    rotulo: 'Instagram orgânico',
    descricao: 'Publicação orgânica, sem verba.',
  },
  {
    destino: 'manual',
    rotulo: 'Exportação manual',
    descricao: 'Download para uso fora do VOLC O.S.',
  },
] as const;

// ── validação ───────────────────────────────────────────────────────────────

export type CampoDoBriefing = keyof RascunhoDeImagem;
export type ErrosDoBriefing = Partial<Record<CampoDoBriefing, string>>;

export const MIN_TITULO = 3;
export const MIN_OBJETIVO = 10;
export const MIN_MENSAGEM = 10;

export function validarEtapa(etapa: EtapaDoBriefing, r: RascunhoDeImagem): ErrosDoBriefing {
  const erros: ErrosDoBriefing = {};
  if (etapa === 'intencao') {
    if (r.projetoTitulo.trim().length < MIN_TITULO) {
      erros.projetoTitulo = `Dê um nome com pelo menos ${MIN_TITULO} caracteres para reencontrar este trabalho depois.`;
    }
    if (r.objetivo.trim().length < MIN_OBJETIVO) {
      erros.objetivo = `Descreva o objetivo com pelo menos ${MIN_OBJETIVO} caracteres.`;
    }
    if (r.destinosPretendidos.length === 0) {
      erros.destinosPretendidos = 'Escolha ao menos um destino pretendido.';
    }
  }
  if (etapa === 'formatos') {
    if (r.slots.length === 0) {
      erros.slots = 'Escolha ao menos um formato. Cada formato é uma peça e uma chamada ao motor.';
    }
  }
  if (etapa === 'mensagem') {
    if (r.mensagem.trim().length < MIN_MENSAGEM) {
      erros.mensagem = `Escreva a mensagem com pelo menos ${MIN_MENSAGEM} caracteres.`;
    }
  }
  if (etapa === 'marca') {
    if (!modoDisponivel(r.modo)) {
      erros.modo = 'Este modo ainda não está disponível. Escolha um modo habilitado.';
    }
  }
  return erros;
}

export function etapaCompleta(etapa: EtapaDoBriefing, r: RascunhoDeImagem): boolean {
  return Object.keys(validarEtapa(etapa, r)).length === 0;
}

/** Todos os erros do rascunho, das etapas que precedem a revisão. */
export function validarTudo(r: RascunhoDeImagem): ErrosDoBriefing {
  return ETAPAS.filter((e) => e !== 'revisao').reduce<ErrosDoBriefing>(
    (acc, etapa) => ({ ...acc, ...validarEtapa(etapa, r) }),
    {},
  );
}

export function podeGerar(r: RascunhoDeImagem): boolean {
  return Object.keys(validarTudo(r)).length === 0;
}

export function proximaEtapa(etapa: EtapaDoBriefing): EtapaDoBriefing {
  const i = ETAPAS.indexOf(etapa);
  return ETAPAS[Math.min(i + 1, ETAPAS.length - 1)];
}

export function etapaAnterior(etapa: EtapaDoBriefing): EtapaDoBriefing {
  const i = ETAPAS.indexOf(etapa);
  return ETAPAS[Math.max(i - 1, 0)];
}

// ── contrato final ──────────────────────────────────────────────────────────

export function paraPedido(r: RascunhoDeImagem): PedidoDeJobDeImagem {
  return {
    projetoTitulo: r.projetoTitulo.trim(),
    objetivo: r.objetivo.trim(),
    mensagem: r.mensagem.trim(),
    // String vazia não é "sem público": o contrato pede `null` para ausência.
    audiencia: r.audiencia.trim() ? r.audiencia.trim() : null,
    brandPackId: r.brandPackId ? r.brandPackId : null,
    modo: r.modo,
    slots: [...r.slots],
    destinosPretendidos: [...r.destinosPretendidos],
  };
}

export interface LinhaDaRevisao {
  rotulo: string;
  valor: string;
}

/**
 * A revisão do contrato: o que será gerado, quantas peças, qual motor, e o
 * aviso de que isto custa uma chamada real por peça.
 *
 * `nomeDoPack` e `formatoDoSlot` entram por parâmetro porque a revisão não pode
 * mostrar identificador cru: quem confere antes de gastar precisa ler nome de
 * formato e nome de pack, não UUID e não `1.91x1`.
 */
export function linhasDaRevisao(
  r: RascunhoDeImagem,
  formatos: readonly FormatoDisponivel[],
  nomeDoPack: (id: string) => string,
): LinhaDaRevisao[] {
  const escolhidos = r.slots
    .map((slot) => formatos.find((f) => f.slot === slot))
    .filter((f): f is FormatoDisponivel => Boolean(f));
  const modo = MODOS.find((m) => m.modo === r.modo);
  return [
    { rotulo: 'Projeto', valor: r.projetoTitulo.trim() || 'sem nome' },
    { rotulo: 'Objetivo', valor: r.objetivo.trim() || 'não informado' },
    { rotulo: 'Mensagem', valor: r.mensagem.trim() || 'não informada' },
    { rotulo: 'Público', valor: r.audiencia.trim() || 'não informado' },
    {
      rotulo: 'Peças',
      valor: escolhidos.length
        ? escolhidos.map((f) => `${f.rotulo} ${f.largura}x${f.altura}`).join(', ')
        : 'nenhum formato escolhido',
    },
    {
      rotulo: 'Destinos pretendidos',
      valor: r.destinosPretendidos.length
        ? r.destinosPretendidos
            .map((d) => DESTINOS.find((o) => o.destino === d)?.rotulo ?? d)
            .join(', ')
        : 'nenhum',
    },
    { rotulo: 'Modo', valor: modo ? modo.rotulo : r.modo },
    { rotulo: 'Brand pack', valor: r.brandPackId ? nomeDoPack(r.brandPackId) : 'nenhum' },
  ];
}

/**
 * A frase de consequência. É a última coisa que se lê antes de gastar.
 *
 * Não estima valor: o custo real vem do servidor depois. Estimar aqui seria
 * inventar número, e a promessa da casa é a oposta.
 */
export function fraseDeConsequencia(r: RascunhoDeImagem): string {
  const n = r.slots.length;
  if (n === 0) return 'Nenhum formato escolhido: não há o que gerar.';
  const peca = n === 1 ? 'uma peça' : `${n} peças`;
  const chamada = n === 1 ? 'uma chamada real' : `${n} chamadas reais`;
  return `Gerar produz ${peca} e faz ${chamada} ao motor. O custo é apurado pelo servidor e aparece na tela do trabalho.`;
}

/**
 * A chave de idempotência do cliente, derivada do conteúdo do formulário.
 *
 * ⚠️ Não é autoridade: o backend recalcula a dele e a dele é a que vale. Esta
 * serve para o caso comum e barato, que é o duplo clique ou o F5 no meio do
 * envio, e para a tela poder reconhecer o próprio reenvio.
 */
export function chaveDeIdempotencia(r: RascunhoDeImagem): string {
  const semente = JSON.stringify({
    t: r.projetoTitulo.trim(),
    o: r.objetivo.trim(),
    m: r.mensagem.trim(),
    a: r.audiencia.trim(),
    b: r.brandPackId,
    d: r.modo,
    s: [...r.slots].sort(),
    x: [...r.destinosPretendidos].sort(),
  });
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < semente.length; i += 1) {
    const c = semente.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 + c, 0x85ebca6b) >>> 0;
  }
  return `cli_${h1.toString(16).padStart(8, '0')}${h2.toString(16).padStart(8, '0')}`;
}
