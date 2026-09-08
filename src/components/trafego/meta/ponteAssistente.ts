export type SelecaoDoAssistente = { masterRefs: string[] };
export function assistenteIntegrado(): boolean {
  try { return window.frameElement?.getAttribute('data-meta-assistant') === 'true'; }
  catch { return false; }
}
/** References are selections, never authority to upload, approve or dispatch. */
export function lerSelecaoDoAssistente(valor: unknown): SelecaoDoAssistente | null {
  if (!valor || typeof valor !== 'object') return null;
  const v = valor as Record<string, unknown>;
  if (v.type !== 'volc:creative-selection' || !Array.isArray(v.masterRefs)
      || v.masterRefs.length < 1 || v.masterRefs.length > 10
      || v.masterRefs.some(r => typeof r !== 'string' || !/^[a-zA-Z0-9_-]{8,180}$/.test(r))) return null;
  return { masterRefs: [...new Set(v.masterRefs as string[])] };
}
