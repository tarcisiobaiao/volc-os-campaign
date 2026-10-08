/**
 * Leitura do JSON Schema que o servidor publica em
 * `GET /api/trafego/canais/esquema` — enums, limites, defaults e a conferência
 * de forma ANTES do clique.
 *
 * ## Por que a tela lê o esquema em vez de repetir as regras
 *
 * O esquema é gerado dos mesmos dataclasses que julgam `/provar` e `/subir`.
 * Uma lista de enums escrita à mão aqui seria uma quinta cópia do contrato,
 * divergindo em silêncio no primeiro campo que o motor ganhar. Por isso:
 *
 * - as OPÇÕES de um `<select>` vêm de `opcoesDoEsquema` quando o esquema
 *   chegou (os unions de `types/trafegoCanais.ts` são só o recuo);
 * - os LIMITES (máx. itens, máx. caracteres, mín./máx. numérico) vêm de
 *   `limitesDoEsquema`;
 * - `conferirForma` roda o esquema sobre o pedido montado e devolve os erros no
 *   MESMO formato de caminho do 422 (`configuracao_x.campo[0].sub`), para que o
 *   campo da tela os mostre sem um segundo parser.
 *
 * ⚠️ A conferência daqui é PRÉVIA, não veredito. Combinações (`TARGET_IMPRESSION_SHARE`
 * sem teto, `path2` sem `path1`…) são julgadas pelo `__post_init__` do motor, que
 * o JSON Schema não expressa — elas chegam como 422 e são mostradas igual.
 */
import type { CanalDeConfiguracao, EsquemaDosCanais, EsquemaJson } from '@/types/trafegoCanais';
import type { ErroDeCampo } from './erros422';

/** O esquema de um canal, quando o servidor o publicou. */
export function esquemaDoCanal(
  esquemas: EsquemaDosCanais | null | undefined, canal: CanalDeConfiguracao,
): EsquemaJson | null {
  return esquemas?.canais?.[canal]?.esquema ?? null;
}

function resolverRef(no: EsquemaJson, raiz: EsquemaJson): EsquemaJson {
  let atual = no;
  for (let i = 0; i < 16 && atual?.$ref; i += 1) {
    const m = /^#\/\$defs\/(.+)$/.exec(atual.$ref);
    const alvo = m ? raiz.$defs?.[m[1]] : undefined;
    if (!alvo) return atual;
    atual = alvo;
  }
  return atual;
}

/** O ramo "útil" de um nó: segue `$ref` e, num `anyOf` com `null`, pega o
 *  ramo que não é `null`. */
function util(no: EsquemaJson | undefined, raiz: EsquemaJson): EsquemaJson | null {
  if (!no) return null;
  const r = resolverRef(no, raiz);
  if (r.anyOf) {
    const naoNulo = r.anyOf.find((b) => resolverRef(b, raiz).type !== 'null');
    return naoNulo ? util(naoNulo, raiz) : r;
  }
  return r;
}

/**
 * O sub-esquema de um caminho. `lance.estrategia`, `frequencia[].unidade`,
 * `exclusoes.rotulos_de_conteudo[]` — `[]` desce em `items`.
 */
export function subesquema(raiz: EsquemaJson | null, caminho: string): EsquemaJson | null {
  if (!raiz) return null;
  let no: EsquemaJson | null = util(raiz, raiz);
  for (const pedaco of caminho.split('.').filter(Boolean)) {
    const m = /^([^[]*)((?:\[\])*)$/.exec(pedaco);
    if (!m || !no) return null;
    if (m[1]) no = util(no.properties?.[m[1]], raiz);
    const descidas = (m[2].match(/\[\]/g) ?? []).length;
    for (let i = 0; i < descidas && no; i += 1) no = util(no.items, raiz);
  }
  return no;
}

/** As opções de um enum, do esquema; `recuo` quando ele não chegou. */
export function opcoesDoEsquema<T extends string>(
  raiz: EsquemaJson | null, caminho: string, recuo: readonly T[],
): T[] {
  const no = subesquema(raiz, caminho);
  const valores = no?.enum ?? no?.propertyNames?.enum;
  if (Array.isArray(valores) && valores.length > 0) {
    return valores.filter((v): v is T => typeof v === 'string');
  }
  return [...recuo];
}

export interface LimitesDoCampo {
  maxLength?: number;
  minLength?: number;
  maxItems?: number;
  minItems?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  /** Do item, quando o campo é lista. */
  itemMaxLength?: number;
}

export function limitesDoEsquema(raiz: EsquemaJson | null, caminho: string): LimitesDoCampo {
  const no = subesquema(raiz, caminho);
  if (!no) return {};
  const item = no.items ? util(no.items, raiz!) : null;
  const l: LimitesDoCampo = {};
  for (const k of ['maxLength', 'minLength', 'maxItems', 'minItems', 'minimum', 'maximum', 'exclusiveMinimum'] as const) {
    if (typeof no[k] === 'number') l[k] = no[k] as number;
  }
  if (typeof item?.maxLength === 'number') l.itemMaxLength = item.maxLength;
  return l;
}

/** O default declarado (`exclusoes.rotulos_de_conteudo` → a lista de nascimento). */
export function defaultDoEsquema(raiz: EsquemaJson | null, caminho: string): unknown {
  if (!raiz) return undefined;
  const partes = caminho.split('.');
  const campo = partes.pop()!;
  const pai = partes.length ? subesquema(raiz, partes.join('.')) : util(raiz, raiz);
  const direto = pai?.properties?.[campo]?.default;
  if (direto !== undefined) return direto;
  // O default de um objeto pai (`exclusoes`: {...}) carrega os dos filhos.
  if (partes.length) {
    const avo = defaultDoEsquema(raiz, partes.join('.'));
    if (avo && typeof avo === 'object' && campo in (avo as object)) {
      return (avo as Record<string, unknown>)[campo];
    }
  }
  return undefined;
}

/**
 * O motivo declarado pelo servidor para um ramo não viajar por HTTP
 * (`x-volc-indisponivel-por-http`), procurado em toda a sub-árvore do caminho.
 * É assim que a tela explica o carrossel de Demand Gen com a frase do contrato,
 * e não com uma frase própria.
 */
export function motivoIndisponivelPorHttp(raiz: EsquemaJson | null, caminho: string): string | null {
  const inicio = subesquema(raiz, caminho);
  if (!inicio || !raiz) return null;
  const vistos = new Set<EsquemaJson>();
  const visitar = (no: EsquemaJson | undefined): string | null => {
    if (!no || typeof no !== 'object' || vistos.has(no)) return null;
    vistos.add(no);
    if (no['x-volc-indisponivel-por-http'] === true) {
      return typeof no.description === 'string' ? no.description : 'indisponível pela fronteira HTTP';
    }
    const filhos: (EsquemaJson | undefined)[] = [
      no.$ref ? resolverRef(no, raiz) : undefined,
      ...(no.anyOf ?? []), ...(no.oneOf ?? []), no.items, no.not,
      ...Object.values(no.properties ?? {}),
    ];
    for (const f of filhos) {
      const r = visitar(f);
      if (r) return r;
    }
    return null;
  };
  return visitar(inicio);
}

// ═══════════════════════════════════════════════════════════════════════════
// A conferência de forma
// ═══════════════════════════════════════════════════════════════════════════

const DATA = /^\d{4}-\d{2}-\d{2}$/;

function tipoDe(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
  return typeof v;
}

function casaTipo(esperado: string, v: unknown): boolean {
  const t = tipoDe(v);
  if (esperado === 'number') return t === 'number' || t === 'integer';
  return esperado === t;
}

const NOME_DO_TIPO: Record<string, string> = {
  object: 'objeto', array: 'lista', string: 'texto', number: 'número',
  integer: 'inteiro', boolean: 'sim/não', null: 'vazio',
};

function juntar(caminho: string, chave: string | number): string {
  if (typeof chave === 'number') return `${caminho}[${chave}]`;
  return caminho ? `${caminho}.${chave}` : chave;
}

function conferirNo(
  v: unknown, no: EsquemaJson | undefined, raiz: EsquemaJson, caminho: string, saida: ErroDeCampo[],
): void {
  if (!no) return;
  const s = resolverRef(no, raiz);
  const add = (mensagem: string) => saida.push({ caminho, mensagem, codigo: 'ESQUEMA' });

  if (s.anyOf || s.oneOf) {
    const ramos = (s.anyOf ?? s.oneOf)!;
    const tentativas = ramos.map((r) => {
      const e: ErroDeCampo[] = [];
      conferirNo(v, r, raiz, caminho, e);
      return e;
    });
    if (tentativas.some((e) => e.length === 0)) return;
    // Mostra os erros do ramo que não é `null`: é o que o operador tentou.
    const i = ramos.findIndex((r) => resolverRef(r, raiz).type !== 'null');
    saida.push(...tentativas[i >= 0 ? i : 0]);
    return;
  }
  if (s.not) {
    const e: ErroDeCampo[] = [];
    conferirNo(v, s.not, raiz, caminho, e);
    if (e.length === 0) {
      add(typeof s.description === 'string' ? s.description : 'valor não aceito por este campo');
      return;
    }
  }
  if (s.type) {
    const tipos = Array.isArray(s.type) ? s.type : [s.type];
    if (!tipos.some((t) => casaTipo(t, v))) {
      add(`esperado ${tipos.map((t) => NOME_DO_TIPO[t] ?? t).join(' ou ')}, veio ${NOME_DO_TIPO[tipoDe(v)] ?? tipoDe(v)}`);
      return;
    }
  }
  if (s.enum && !s.enum.some((x) => x === v)) {
    add(`valor ${JSON.stringify(v)} fora da lista aceita`);
    return;
  }
  if (s.const !== undefined && s.const !== v) {
    add(`precisa ser ${JSON.stringify(s.const)}`);
    return;
  }
  if (typeof v === 'string') {
    if (typeof s.minLength === 'number' && v.length < s.minLength) {
      add(s.minLength === 1 ? 'não pode ficar vazio' : `mínimo de ${s.minLength} caracteres`);
    }
    if (typeof s.maxLength === 'number' && v.length > s.maxLength) add(`máximo de ${s.maxLength} caracteres`);
    if (typeof s.pattern === 'string') {
      try {
        if (!new RegExp(s.pattern, 'u').test(v)) add(`formato inválido (${s.pattern})`);
      } catch { /* padrão que o motor de regex do navegador não lê: o servidor julga */ }
    }
    if (s.format === 'date' && !DATA.test(v)) add('data no formato AAAA-MM-DD');
  }
  if (typeof v === 'number') {
    if (typeof s.minimum === 'number' && v < s.minimum) add(`mínimo ${s.minimum}`);
    if (typeof s.maximum === 'number' && v > s.maximum) add(`máximo ${s.maximum}`);
    if (typeof s.exclusiveMinimum === 'number' && v <= s.exclusiveMinimum) add(`precisa ser maior que ${s.exclusiveMinimum}`);
    if (typeof s.exclusiveMaximum === 'number' && v >= s.exclusiveMaximum) add(`precisa ser menor que ${s.exclusiveMaximum}`);
  }
  if (Array.isArray(v)) {
    if (typeof s.minItems === 'number' && v.length < s.minItems) add(`mínimo de ${s.minItems} item(ns)`);
    if (typeof s.maxItems === 'number' && v.length > s.maxItems) add(`máximo de ${s.maxItems} item(ns)`);
    if (s.uniqueItems) {
      const vistos = new Set(v.map((x) => JSON.stringify(x)));
      if (vistos.size !== v.length) add('itens repetidos');
    }
    v.forEach((item, i) => {
      const doItem = s.prefixItems?.[i] ?? s.items;
      conferirNo(item, doItem, raiz, juntar(caminho, i), saida);
    });
  }
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const obj = v as Record<string, unknown>;
    for (const r of s.required ?? []) {
      if (!(r in obj) || obj[r] === undefined) {
        saida.push({ caminho: juntar(caminho, r), mensagem: 'campo obrigatório', codigo: 'ESQUEMA' });
      }
    }
    for (const [k, valor] of Object.entries(obj)) {
      if (valor === undefined) continue;
      if (s.propertyNames?.enum && !s.propertyNames.enum.includes(k)) {
        saida.push({ caminho: juntar(caminho, k), mensagem: 'chave fora da lista aceita', codigo: 'ESQUEMA' });
        continue;
      }
      const prop = s.properties?.[k];
      if (prop) conferirNo(valor, prop, raiz, juntar(caminho, k), saida);
      else if (s.additionalProperties === false) {
        saida.push({ caminho: juntar(caminho, k), mensagem: 'chave desconhecida', codigo: 'ESQUEMA' });
      } else if (s.additionalProperties && typeof s.additionalProperties === 'object') {
        conferirNo(valor, s.additionalProperties, raiz, juntar(caminho, k), saida);
      }
    }
  }
}

/**
 * Confere `valor` contra o esquema do canal e devolve os erros com o caminho
 * prefixado pelo campo HTTP (`configuracao_search.lance.target_cpa`). Sem
 * esquema, devolve `[]`: ausência de régua não é aprovação — o servidor julga.
 */
export function conferirForma(
  valor: unknown, raiz: EsquemaJson | null, campoHttp: string,
): ErroDeCampo[] {
  if (!raiz || valor == null) return [];
  const saida: ErroDeCampo[] = [];
  conferirNo(valor, raiz, raiz, campoHttp, saida);
  return saida;
}
