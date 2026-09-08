import React from 'react';
import { pautadorApi } from '@/lib/pautadorApi';

/** Scoped dependency injection. Never replace the global API singleton for a demo. */
export type MetaCampaignDataApi = Pick<typeof pautadorApi,
  'contasMetaReadModel' | 'inventarioMetaReadModel' | 'detalheMetaReadModel' |
  'financeiroMeta' | 'planejarGestaoMeta'>;

export const MetaCampaignDemoContext = React.createContext<MetaCampaignDataApi | null>(null);
export const useMetaCampaignApi = () => React.useContext(MetaCampaignDemoContext) ?? pautadorApi;
export const useMetaCampaignDemo = () => React.useContext(MetaCampaignDemoContext) !== null;
