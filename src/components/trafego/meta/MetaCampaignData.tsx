import React from 'react';
import { pautadorApi, type OpcoesDeLeituraMeta, type PaginaMetaReadModel, type DetalheMetaReadModel } from '@/lib/pautadorApi';

/** Scoped dependency injection. Never replace the global API singleton for a demo. */
export type MetaCampaignDataApi = Pick<typeof pautadorApi,
  'contasMetaReadModel' | 'financeiroMeta' | 'planejarGestaoMeta'> & {
    inventarioMetaReadModel: (entidade: string, escopo?: string | OpcoesDeLeituraMeta) => Promise<PaginaMetaReadModel>;
    detalheMetaReadModel: (entidade: string, referencia: string, contaRef?: string) => Promise<DetalheMetaReadModel>;
  };

export const MetaCampaignDemoContext = React.createContext<MetaCampaignDataApi | null>(null);
export const useMetaCampaignApi = () => React.useContext(MetaCampaignDemoContext) ?? pautadorApi;
export const useMetaCampaignDemo = () => React.useContext(MetaCampaignDemoContext) !== null;
