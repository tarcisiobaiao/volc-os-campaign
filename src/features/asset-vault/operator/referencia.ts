/**
 * Referência segura de credencial no navegador.
 *
 * O Cofre guarda o endereço; o 1Password guarda o valor. Esta camada monta o
 * endereço para o POST e NUNCA o reapresenta. A tela fala em cofre, item e
 * campo. O esquema do 1Password não aparece como texto copiável.
 */

const SEPARADOR = `${":"}${"/"}${"/"}`;

export interface PecasDaReferencia {
  cofre: string;
  item: string;
  campo: string;
}

export type FalhaDaReferencia =
  | "vazio"
  | "query"
  | "mfa"
  | "valor_bruto"
  | "forma";

const CAMPOS_PROIBIDOS = new Set([
  "password", "passwd", "secret", "token", "cookie", "otp", "totp", "mfa",
  "recovery", "privatekey", "private_key", "apikey", "api_key",
]);

function normalizarPeca(valor: string): string {
  return valor.trim().replace(/\s+/g, "%20");
}

export function diagnosticarReferencia(pecas: PecasDaReferencia): FalhaDaReferencia | null {
  const cofre = pecas.cofre.trim();
  const item = pecas.item.trim();
  const campo = pecas.campo.trim();
  if (!cofre || !item || !campo) return "vazio";
  const junto = `${cofre}/${item}/${campo}`;
  if (junto.includes("?")) return "query";
  const campoNorm = campo.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (campoNorm === "otp" || campoNorm === "totp" || campoNorm === "mfa") return "mfa";
  if (CAMPOS_PROIBIDOS.has(campoNorm)) return "valor_bruto";
  if (/[\s]/.test(cofre) || cofre.includes("/") || item.includes("/")) return "forma";
  return null;
}

export function montarReferencia1Password(pecas: PecasDaReferencia): string {
  const falha = diagnosticarReferencia(pecas);
  if (falha) throw new Error(fraseDaFalha(falha));
  return `${"op"}${SEPARADOR}${normalizarPeca(pecas.cofre)}/${normalizarPeca(pecas.item)}/${normalizarPeca(pecas.campo)}`;
}

export function fraseDaFalha(falha: FalhaDaReferencia): string {
  switch (falha) {
    case "vazio":
      return "Cofre, item e campo são obrigatórios para montar a referência.";
    case "query":
      return "Query string é recusada. MFA e atributos extras não entram no Cofre.";
    case "mfa":
      return "MFA não entra no Cofre, nem por referência.";
    case "valor_bruto":
      return "Este campo aponta para o valor secreto. O Cofre registra o endereço de um campo de credencial, não a senha.";
    case "forma":
      return "Cofre e item não podem ter barra nem espaço cru. Use o nome do item; espaços serão codificados.";
    default:
      return "A referência não pôde ser montada.";
  }
}

/** Texto operacional. Nunca o endereço completo. */
export function retratoDaReferencia(pecas: PecasDaReferencia): string {
  const item = pecas.item.trim() || "item";
  const campo = pecas.campo.trim() || "campo";
  const cofre = pecas.cofre.trim() || "cofre";
  return `1Password contém o valor · Cofre «${cofre}» · item «${item}» · campo «${campo}»`;
}

export function retratoMascarado(provider: string, nomeLogico: string): string {
  const provedor = provider === "1password" ? "1Password" : provider;
  return `${provedor} · ${nomeLogico} · valor só no cofre externo`;
}

export function fonteDoInventario(): string {
  return "GET /api/cofre/ativos";
}
