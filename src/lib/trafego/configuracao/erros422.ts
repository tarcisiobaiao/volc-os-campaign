/**
 * O 422 do servidor, levado ao campo da tela.
 *
 * ## O formato (GADS-CRIACAO-CANAIS-v1 §2)
 *
 * Configuração de canal com forma errada volta como QUALQUER erro de corpo do
 * FastAPI: `detail[]` com `loc` exato —
 * `["body", "configuracao_display", "frequencia", 0, "impressoes"]` — e, quando
 * é a configuração, `ctx.caminho` já no formato de ponto
 * (`configuracao_display.frequencia[0].impressoes`). Quando o motor recusa uma
 * COMBINAÇÃO, o `loc` aponta o objeto que a contém (`configuracao_search.lance`).
 *
 * Duas outras formas de 422 também chegam à Bancada, e nenhuma pode sumir:
 *
 * - `detail` como FRASE (o `_recusar_campos_nao_operados_*` de Display e Demand
 *   Gen levanta `HTTPException(422, detail=str)`);
 * - o validador do envelope (`CONFIGURACAO_DE_OUTRO_CANAL`, `match_por_keyword`
 *   fora de Search): `loc: ["body"]`, sem campo.
 *
 * As duas viram erro GERAL, mostrado na Revisão — nunca descartado.
 *
 * ⚠️ A TELA NÃO REESCREVE A REGRA. O texto que aparece no campo é o `msg` do
 * servidor, inteiro. Este módulo só decide ONDE ele aparece.
 */
import type { ErroDeCorpo422 } from '@/types/trafegoCanais';

/** Um erro já posicionado. `caminho` vazio = do pedido inteiro. */
export interface ErroDeCampo {
  caminho: string;
  mensagem: string;
  codigo: string | null;
}

export interface ErrosDoServidor {
  campos: ErroDeCampo[];
  /** Frases sem campo — o 422 em texto e o do envelope. */
  gerais: string[];
}

export const SEM_ERROS: ErrosDoServidor = { campos: [], gerais: [] };

/** `["body","configuracao_display","frequencia",0,"impressoes"]` →
 *  `configuracao_display.frequencia[0].impressoes`. */
export function caminhoDoLoc(loc: readonly (string | number)[]): string {
  const partes = loc[0] === 'body' ? loc.slice(1) : [...loc];
  let saida = '';
  for (const p of partes) {
    if (typeof p === 'number' || /^\d+$/.test(String(p))) saida += `[${p}]`;
    else saida += saida ? `.${p}` : String(p);
  }
  return saida;
}

function ehItemDe422(x: unknown): x is ErroDeCorpo422 {
  return typeof x === 'object' && x !== null
    && Array.isArray((x as ErroDeCorpo422).loc)
    && typeof (x as ErroDeCorpo422).msg === 'string';
}

/** O `msg` do pydantic chega como "Value error, <frase>" — o prefixo é ruído. */
function limparMensagem(msg: string): string {
  return msg.replace(/^Value error,\s*/i, '').trim();
}

/**
 * Lê o erro de uma chamada e devolve os erros posicionados, ou `null` quando
 * não é um 422 (um 403, um 5xx e uma rede caída continuam sendo mensagem — não
 * são erro de campo e não podem ser pintados num).
 *
 * Aceita o `PautadorApiError` (status + `corpo`) sem importá-lo: este módulo é
 * regra pura e não depende do cliente HTTP.
 */
export function errosDo422(e: unknown): ErrosDoServidor | null {
  if (typeof e !== 'object' || e === null) return null;
  const status = (e as { status?: unknown }).status;
  if (status !== 422) return null;
  const corpo = (e as { corpo?: unknown }).corpo;
  const mensagem = (e as { message?: unknown }).message;

  const campos: ErroDeCampo[] = [];
  const gerais: string[] = [];
  if (Array.isArray(corpo)) {
    for (const item of corpo) {
      if (!ehItemDe422(item)) continue;
      const caminho = typeof item.ctx?.caminho === 'string' && item.ctx.caminho
        ? item.ctx.caminho
        : caminhoDoLoc(item.loc);
      const texto = limparMensagem(item.msg);
      if (!caminho) gerais.push(texto);
      else campos.push({ caminho, mensagem: texto, codigo: item.ctx?.codigo ?? null });
    }
  }
  if (campos.length === 0 && gerais.length === 0) {
    // 422 em frase: `detail` era texto, e o cliente o pôs em `message`.
    gerais.push(typeof mensagem === 'string' && mensagem ? mensagem : 'O servidor recusou a forma do pedido.');
  }
  return { campos, gerais };
}

/** Os erros EXATAMENTE deste caminho. */
export function errosNoCaminho(erros: ErrosDoServidor, caminho: string): string[] {
  return erros.campos.filter((e) => e.caminho === caminho).map((e) => e.mensagem);
}

/** Os erros deste caminho OU de qualquer campo dentro dele — para a seção
 *  que contém o campo (a combinação recusada aponta o objeto). */
export function errosSob(erros: ErrosDoServidor, prefixo: string): ErroDeCampo[] {
  return erros.campos.filter((e) => e.caminho === prefixo
    || e.caminho.startsWith(`${prefixo}.`) || e.caminho.startsWith(`${prefixo}[`));
}

/** Junta duas fontes (o pré-teste pelo esquema e o 422 do servidor). */
export function juntarErros(...fontes: ErrosDoServidor[]): ErrosDoServidor {
  return {
    campos: fontes.flatMap((f) => f.campos),
    gerais: fontes.flatMap((f) => f.gerais),
  };
}
