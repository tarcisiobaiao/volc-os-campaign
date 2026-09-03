/**
 * Rascunho do onboarding: o que pode viver no sessionStorage e o que não pode.
 *
 * Persistível: identidade do ativo e metadados da credencial (provider, nome
 * lógico, finalidade, responsável, pular).
 *
 * Efêmero, só em memória: cofre, item e campo. O localizador 1Password só é
 * montado no instante da mutation autenticada e depois as peças são descartadas.
 */
import {
  type AssetKind,
} from "../contract";
import type { PecasDaReferencia } from "./referencia";

export const CHAVE_RASCUNHO = "volc.cofre.onboarding.v2";

export const CHAVES_EFEMERAS = ["cofre", "item", "campo", "localizador"] as const;

export type MetadadosDaCredencial = {
  provider: string;
  nome_logico: string;
  owner_nome: string;
  finalidade: string;
  pular: boolean;
};

export type RascunhoPersistivel = {
  passo: number;
  kind: AssetKind;
  ativo_id: string;
  nome: string;
  plataforma: string;
  estado: string;
  criticidade: string;
  resumo: string;
  capacidades: string;
  tags: string;
  proxima_acao: string;
  dono_nome: string;
  dono_custodia: string;
  projeto: string;
  vertical: string;
  display_id: string;
  url_publica: string;
  credencial: MetadadosDaCredencial;
  relacao: { tipo: string; destino: string; rotulo: string; pular: boolean };
};

export const RASCUNHO_VAZIO: RascunhoPersistivel = {
  passo: 1,
  kind: "facebook_page",
  ativo_id: "", nome: "", plataforma: "", estado: "declared", criticidade: "medium",
  resumo: "", capacidades: "", tags: "", proxima_acao: "",
  dono_nome: "", dono_custodia: "declared",
  projeto: "", vertical: "", display_id: "", url_publica: "",
  credencial: { provider: "1password", nome_logico: "", owner_nome: "", finalidade: "", pular: false },
  relacao: { tipo: "depends_on", destino: "", rotulo: "", pular: true },
};

export function pecasVazias(): PecasDaReferencia {
  return { cofre: "", item: "", campo: "" };
}

/** Detecta o esquema 1Password sem materializar a string contígua. */
export function textoTemEsquema1Password(texto: string | null | undefined): boolean {
  if (!texto) return false;
  const marca = "op:";
  let from = 0;
  while (from < texto.length) {
    const i = texto.indexOf(marca, from);
    if (i < 0) return false;
    if (texto.charCodeAt(i + 3) === 47 && texto.charCodeAt(i + 4) === 47) return true;
    from = i + 1;
  }
  return false;
}

function chavesProibidas(): Set<string> {
  return new Set(CHAVES_EFEMERAS);
}

function objetoContemChaveProibida(valor: unknown): boolean {
  if (valor == null) return false;
  if (Array.isArray(valor)) return valor.some(objetoContemChaveProibida);
  if (typeof valor !== "object") return false;
  const proibidas = chavesProibidas();
  for (const [chave, filho] of Object.entries(valor as Record<string, unknown>)) {
    if (proibidas.has(chave)) return true;
    if (objetoContemChaveProibida(filho)) return true;
  }
  return false;
}

export function hitsDeReferenciaNoTexto(texto: string | null | undefined): string[] {
  if (!texto) return [];
  const hits: string[] = [];
  if (textoTemEsquema1Password(texto)) hits.push("esquema");
  try {
    const lido: unknown = JSON.parse(texto);
    if (objetoContemChaveProibida(lido)) hits.push("chave_efemera");
  } catch {
    for (const chave of CHAVES_EFEMERAS) {
      if (texto.includes(`"${chave}"`)) hits.push(`chave:${chave}`);
    }
  }
  return hits;
}

export function sanitizarCredencialPersistivel(cru: unknown): MetadadosDaCredencial {
  const o = cru && typeof cru === "object" ? (cru as Record<string, unknown>) : {};
  const provider = typeof o.provider === "string" && o.provider.trim() ? o.provider.trim() : "1password";
  return {
    provider,
    nome_logico: typeof o.nome_logico === "string" ? o.nome_logico : "",
    owner_nome: typeof o.owner_nome === "string" ? o.owner_nome : "",
    finalidade: typeof o.finalidade === "string" ? o.finalidade : "",
    pular: Boolean(o.pular),
  };
}

function omitirProibidos(valor: unknown): unknown {
  if (typeof valor === "string") return textoTemEsquema1Password(valor) ? "" : valor;
  if (valor == null || typeof valor !== "object") return valor;
  if (Array.isArray(valor)) return valor.map(omitirProibidos);
  const proibidas = chavesProibidas();
  const saida: Record<string, unknown> = {};
  for (const [chave, filho] of Object.entries(valor as Record<string, unknown>)) {
    if (proibidas.has(chave)) continue;
    saida[chave] = omitirProibidos(filho);
  }
  return saida;
}

export function hidratarRascunhoPersistivel(cru: unknown): RascunhoPersistivel {
  const lido = cru && typeof cru === "object" ? (cru as Partial<RascunhoPersistivel>) : {};
  const combinado: RascunhoPersistivel = {
    ...RASCUNHO_VAZIO,
    ...lido,
    credencial: sanitizarCredencialPersistivel(
      (lido as { credencial?: unknown }).credencial,
    ),
    relacao: { ...RASCUNHO_VAZIO.relacao, ...(lido.relacao ?? {}) },
  };
  return omitirProibidos(combinado) as RascunhoPersistivel;
}

export function serializarRascunhoPersistivel(rascunho: RascunhoPersistivel): string {
  const persistivel = omitirProibidos({
    ...rascunho,
    credencial: sanitizarCredencialPersistivel(rascunho.credencial),
    relacao: { ...rascunho.relacao },
  });
  const json = JSON.stringify(persistivel);
  const hits = hitsDeReferenciaNoTexto(json);
  if (hits.length) {
    return JSON.stringify(omitirProibidos({
      ...RASCUNHO_VAZIO,
      passo: rascunho.passo,
      kind: rascunho.kind,
    }));
  }
  return json;
}

export function lerRascunhoPersistivel(): RascunhoPersistivel {
  try {
    const cru = sessionStorage.getItem(CHAVE_RASCUNHO);
    if (!cru) return RASCUNHO_VAZIO;
    return hidratarRascunhoPersistivel(JSON.parse(cru) as unknown);
  } catch {
    return RASCUNHO_VAZIO;
  }
}

export function gravarRascunhoPersistivel(rascunho: RascunhoPersistivel): void {
  sessionStorage.setItem(CHAVE_RASCUNHO, serializarRascunhoPersistivel(rascunho));
}

export function limparRascunhoPersistivel(): void {
  sessionStorage.removeItem(CHAVE_RASCUNHO);
}

export function reescreverRascunhoSanitizadoSeExistir(): void {
  const cru = sessionStorage.getItem(CHAVE_RASCUNHO);
  if (!cru) return;
  gravarRascunhoPersistivel(lerRascunhoPersistivel());
}

export function rotuloDoProvider(provider: string): string {
  return provider === "1password" ? "1Password" : provider;
}

function areaDeStorage(nome: "sessionStorage" | "localStorage"): Storage | null {
  try {
    const area = globalThis[nome];
    if (!area || typeof area.getItem !== "function") return null;
    return area;
  } catch {
    return null;
  }
}

export function varrerArmazenamentoDoBrowser(): string[] {
  const hits: string[] = [];
  const varrer = (area: Storage | null, nome: string) => {
    if (!area) return;
    for (let i = 0; i < area.length; i += 1) {
      const chave = area.key(i);
      if (!chave) continue;
      const valor = area.getItem(chave);
      const encontrados = hitsDeReferenciaNoTexto(valor).concat(hitsDeReferenciaNoTexto(chave));
      if (encontrados.length) hits.push(`${nome}:${chave}:${encontrados.join(",")}`);
    }
  };
  varrer(areaDeStorage("sessionStorage"), "sessionStorage");
  varrer(areaDeStorage("localStorage"), "localStorage");
  return hits;
}
