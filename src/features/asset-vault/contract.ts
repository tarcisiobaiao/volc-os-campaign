/**
 * Contrato PÚBLICO do Cofre de Ativos.
 *
 * Ele descreve patrimônio e postura de acesso. Não transporta senha, token,
 * TOTP, recovery code, chave privada nem o identificador interno do item no
 * gerenciador de segredos. O locator administrativo ficará no backend privado
 * quando a etapa de persistência nascer.
 */

import { z } from "zod";

export const ASSET_CLUSTERS = [
  "social_presence",
  "paid_media",
  "web_properties",
  "communities",
  "creative_production",
  "automation",
  "infrastructure",
] as const;

export type AssetCluster = (typeof ASSET_CLUSTERS)[number];

export const ASSET_KINDS = [
  "facebook_profile",
  "facebook_page",
  "instagram_profile",
  "youtube_channel",
  "pinterest_account",
  "tiktok_account",
  "linkedin_page",
  "x_account",
  "meta_business_portfolio",
  "meta_ad_account",
  "google_ads_manager",
  "google_ads_account",
  "domain",
  "website",
  "wordpress_site",
  "landing_page",
  "monetization_property",
  "whatsapp_account",
  "whatsapp_community",
  "telegram_channel",
  "messaging_hub",
  "creative_engine",
  "automation_workflow",
  "integration",
  "database_service",
  "server",
  "repository",
  // Perfil de navegador isolado do AdsPower (P03-T07). Entra em `automation`
  // porque é rotina operacional, não presença social: o perfil EXECUTA, a
  // página PUBLICA. Confundi-los faria o Cofre responder "temos duas páginas"
  // quando há uma página e um perfil que a abre.
  "browser_profile",
] as const;

export type AssetKind = (typeof ASSET_KINDS)[number];

export const ASSET_STATES = [
  "declared",
  "verified",
  "ready",
  "active",
  "restricted",
  "inactive",
  "retired",
] as const;

export type AssetState = (typeof ASSET_STATES)[number];
export type AssetCriticality = "low" | "medium" | "high" | "critical";
export type VerificationState = "unverified" | "partial" | "verified" | "expired";
export type CustodyState = "not_required" | "not_registered" | "referenced" | "review_due";
export type EvidenceKind = "owner_declaration" | "live_observation" | "repository_inventory" | "provider_record";
export type RelationKind =
  | "belongs_to"
  | "managed_by"
  | "publishes_to"
  | "authenticates_through"
  | "spends_from"
  | "monetizes"
  | "depends_on"
  | "produces_for";

export const KIND_CLUSTER: Record<AssetKind, AssetCluster> = {
  facebook_profile: "social_presence",
  facebook_page: "social_presence",
  instagram_profile: "social_presence",
  youtube_channel: "social_presence",
  pinterest_account: "social_presence",
  tiktok_account: "social_presence",
  linkedin_page: "social_presence",
  x_account: "social_presence",
  meta_business_portfolio: "paid_media",
  meta_ad_account: "paid_media",
  google_ads_manager: "paid_media",
  google_ads_account: "paid_media",
  domain: "web_properties",
  website: "web_properties",
  wordpress_site: "web_properties",
  landing_page: "web_properties",
  monetization_property: "web_properties",
  whatsapp_account: "communities",
  whatsapp_community: "communities",
  telegram_channel: "communities",
  messaging_hub: "communities",
  creative_engine: "creative_production",
  automation_workflow: "automation",
  integration: "automation",
  database_service: "infrastructure",
  server: "infrastructure",
  repository: "infrastructure",
  browser_profile: "automation",
};

const shortText = z.string().trim().min(1).max(240);
const dateText = z.string().regex(/^\d{4}-\d{2}-\d{2}(?:T.*)?$/, "data inválida");

const assetSchemaBase = z.object({
  schemaVersion: z.literal(1),
  id: z.string().trim().min(3).max(180),
  name: z.string().trim().min(2).max(160),
  cluster: z.enum(ASSET_CLUSTERS),
  kind: z.enum(ASSET_KINDS),
  platform: shortText,
  state: z.enum(ASSET_STATES),
  criticality: z.enum(["low", "medium", "high", "critical"]),
  summary: z.string().trim().min(10).max(800),
  owner: z.object({
    displayName: shortText,
    custody: z.enum(["declared", "verified", "unassigned"]),
  }).strict(),
  project: shortText.optional(),
  vertical: shortText.optional(),
  external: z.object({
    /** Identificador já sanitizado para exibição. Nunca colocar segredo aqui. */
    displayId: z.string().trim().min(1).max(80).optional(),
    publicUrl: z.string().url().refine((value) => /^https?:\/\//i.test(value), "somente URL HTTP(S)").optional(),
  }).strict(),
  capabilities: z.array(shortText).min(1).max(40),
  credential: z.object({
    required: z.boolean(),
    // `1password` entrou em 01/09/2026: o ADR de 28/08 já o havia escolhido, e
    // o schema privado (v13_01) só aceita as cinco formas de referência deste
    // enum. Deixá-lo de fora aqui faria o contrato público recusar exatamente o
    // provider que o backend usa.
    provider: z.enum(["1password", "bitwarden", "vaultwarden", "passbolt", "infisical"]).nullable(),
    state: z.enum(["not_required", "not_registered", "referenced", "review_due"]),
    lastCheckedAt: dateText.optional(),
    /** Linguagem operacional; nunca inclui locator ou material do cofre. */
    note: z.string().trim().min(5).max(500),
  }).strict(),
  verification: z.object({
    state: z.enum(["unverified", "partial", "verified", "expired"]),
    checkedAt: dateText.optional(),
    reviewAt: dateText.optional(),
    checkedBy: shortText.optional(),
  }).strict(),
  evidence: z.array(z.object({
    id: z.string().trim().min(3).max(180),
    kind: z.enum(["owner_declaration", "live_observation", "repository_inventory", "provider_record"]),
    statement: z.string().trim().min(10).max(1000),
    observedAt: dateText,
    sourceLabel: shortText,
  }).strict()).min(1),
  relations: z.array(z.object({
    kind: z.enum(["belongs_to", "managed_by", "publishes_to", "authenticates_through", "spends_from", "monetizes", "depends_on", "produces_for"]),
    targetId: z.string().trim().min(3).max(180),
    targetLabel: shortText,
    state: z.enum(["declared", "verified"]),
  }).strict()).max(100),
  nextAction: z.string().trim().min(10).max(800),
  tags: z.array(shortText).max(30),
}).strict();

export const DigitalAssetSchema = assetSchemaBase.superRefine((asset, context) => {
  const expected = KIND_CLUSTER[asset.kind];
  if (asset.cluster !== expected) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["cluster"],
      message: `o tipo ${asset.kind} pertence ao cluster ${expected}`,
    });
  }
});

export const DigitalAssetListSchema = z.array(DigitalAssetSchema);
export type DigitalAsset = z.infer<typeof DigitalAssetSchema>;

const FORBIDDEN_PUBLIC_KEYS = /^(password|senha|passphrase|secret|client_secret|access_token|refresh_token|api_key|private_key|totp|otp|recovery_code|vault_item_id|credential_locator)$/i;

/**
 * Guarda de regressão para fixtures e payloads públicos futuros. Não tenta
 * "detectar segredo" pelo valor, porque isso cria falsa confiança; impede as
 * chaves que jamais podem fazer parte deste contrato.
 */
function assertNoForbiddenPublicKeys(value: unknown, path = "asset"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoForbiddenPublicKeys(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") return;

  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    if (FORBIDDEN_PUBLIC_KEYS.test(key)) {
      throw new Error(`Campo proibido no contrato público: ${path}.${key}`);
    }
    assertNoForbiddenPublicKeys(nested, `${path}.${key}`);
  }
}

export function assertPublicAssetContract(value: unknown): asserts value is DigitalAsset | DigitalAsset[] {
  assertNoForbiddenPublicKeys(value);
  if (Array.isArray(value)) DigitalAssetListSchema.parse(value);
  else DigitalAssetSchema.parse(value);
}

export const CLUSTER_LABEL: Record<AssetCluster, string> = {
  social_presence: "Presenças sociais",
  paid_media: "Mídia paga",
  web_properties: "Sites e domínios",
  communities: "Comunidades e mensagens",
  creative_production: "Produção criativa",
  automation: "Automações e integrações",
  infrastructure: "Infraestrutura e dados",
};

export const CLUSTER_DESCRIPTION: Record<AssetCluster, string> = {
  social_presence: "Perfis, páginas e canais onde a marca publica e constrói audiência.",
  paid_media: "Gerenciadores e contas que compram mídia nas plataformas.",
  web_properties: "Domínios, sites, WordPress, páginas e propriedades monetizadas.",
  communities: "WhatsApp, Telegram e sistemas que sustentam relacionamento e retenção.",
  creative_production: "Engines que produzem imagem, vídeo, áudio e variações criativas.",
  automation: "Workflows, integrações e rotinas que movem dados e tarefas.",
  infrastructure: "Bancos, servidores, repositórios e serviços-base da operação.",
};

export const KIND_LABEL: Record<AssetKind, string> = {
  facebook_profile: "Perfil do Facebook",
  facebook_page: "Página do Facebook",
  instagram_profile: "Perfil do Instagram",
  youtube_channel: "Canal do YouTube",
  pinterest_account: "Conta do Pinterest",
  tiktok_account: "Conta do TikTok",
  linkedin_page: "Página do LinkedIn",
  x_account: "Conta do X",
  meta_business_portfolio: "Business Portfolio Meta",
  meta_ad_account: "Conta de anúncios Meta",
  google_ads_manager: "MCC Google Ads",
  google_ads_account: "Conta Google Ads",
  domain: "Domínio",
  website: "Site",
  wordpress_site: "Site WordPress",
  landing_page: "Landing page",
  monetization_property: "Propriedade monetizada",
  whatsapp_account: "Conta WhatsApp",
  whatsapp_community: "Comunidade WhatsApp",
  telegram_channel: "Canal Telegram",
  messaging_hub: "Hub de mensagens",
  creative_engine: "Engine criativo",
  automation_workflow: "Workflow de automação",
  integration: "Integração",
  database_service: "Banco e API de dados",
  server: "Servidor",
  repository: "Repositório",
  browser_profile: "Perfil de navegador isolado",
};

export const STATE_LABEL: Record<AssetState, string> = {
  declared: "Declarado",
  verified: "Verificado",
  ready: "Pronto",
  active: "Ativo",
  restricted: "Restrito",
  inactive: "Inativo",
  retired: "Aposentado",
};

export const VERIFICATION_LABEL: Record<VerificationState, string> = {
  unverified: "Não verificado",
  partial: "Verificação parcial",
  verified: "Verificado",
  expired: "Revisão vencida",
};

export const CUSTODY_LABEL: Record<CustodyState, string> = {
  not_required: "Não se aplica",
  not_registered: "Referência ausente",
  referenced: "Referência registrada",
  review_due: "Revisão pendente",
};
