/**
 * Meta CAPI — contrato compartilhado do wizard multi-tenant.
 *
 * Fonte da verdade: docs/superpowers/specs/2026-07-30-meta-capi-wizard-contrato.md
 * Não divergir daqui: esta interface é consumida pelo motor de geração (derive/templates),
 * pelo endpoint autenticado e pela Edge Function `capi-router`.
 */
export interface MetaCapiSiteConfig {
  siteName: string;           // "Apps TechNews"
  siteKey: string;            // "apps-technews"  (chave multi-tenant; derivada, editável)
  domain: string;             // "apps.technewsbrasil.com.br"
  cookieDomain: string;       // ".technewsbrasil.com.br"  (APEX — ver regra no contrato)
  endpointSubdomain: string;  // "ev"
  endpointUrl: string;        // "https://ev.technewsbrasil.com.br/capi"
  pixelId: string;            // "940750053457681"
  events: { interstitial: boolean; rewarded: boolean };
  routerFunctionUrl: string;  // "https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router"
}

/** Entrada mínima do formulário do wizard, antes das derivações. */
export interface DeriveConfigInput {
  siteName: string;
  domain: string;
  pixelId: string;
  /** Subdomínio do endpoint (Worker + DNS). Ausente = "ev". */
  endpointSubdomain?: string;
  /** Ref do projeto Supabase, ex.: "txvvzpstquqmbhljudfn". */
  projectRef: string;
  events: { interstitial: boolean; rewarded: boolean };
  /**
   * siteKey manual. Ausente = derivado do domínio.
   * O usuário pode encurtar (`apps-technewsbrasil` → `apps-technews`).
   */
  siteKey?: string;
}

/**
 * Resultado dos validadores do formulário.
 *
 * ATENÇÃO: é um objeto, não um boolean — sempre cheque `.valid`.
 * `error` traz a mensagem em pt-BR pronta para exibir no campo.
 */
export interface ValidationResult {
  valid: boolean;
  error: string | null;
}

/** Identificadores dos artefatos gerados pelo wizard. */
export type TemplateId = 'pixelBase' | 'interstitial' | 'rewarded' | 'worker';

/** Metadados de cada artefato, para a UI mostrar onde/como colar. */
export interface TemplateMeta {
  id: TemplateId;
  title: string;
  gtmTagType: string;
  gtmTrigger: string;
  description: string;
}
