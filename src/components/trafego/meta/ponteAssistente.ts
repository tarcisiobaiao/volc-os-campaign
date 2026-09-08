export type SelecaoDoAssistente = { masterRefs: string[] };
export type SelecaoDeCopy = { projectRef: string; runRef: string; creativeRef: string };
/** Only references cross the iframe boundary; copy is fetched from the owner-scoped API. */
export function lerSelecaoDeCopy(valor: unknown): SelecaoDeCopy | null {
  if (!valor || typeof valor !== 'object') return null;
  const v = valor as Record<string, unknown>;
  if (v.type !== 'volc:creative-copy'
      || typeof v.projectRef !== 'string' || !/^crproj_[a-f0-9]{24}$/.test(v.projectRef)
      || typeof v.runRef !== 'string' || !/^crrun_[a-f0-9]{24}$/.test(v.runRef)
      || typeof v.creativeRef !== 'string' || !/^creative_[a-z0-9_-]{3,64}$/.test(v.creativeRef)) return null;
  return { projectRef: v.projectRef, runRef: v.runRef, creativeRef: v.creativeRef };
}
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
