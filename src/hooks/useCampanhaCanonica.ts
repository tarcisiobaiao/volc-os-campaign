/**
 * Leitura de UMA campanha pela identidade interna.
 *
 * Só `pautadorApi.campanhaCanonica`. Não passa pela listagem paginada, não
 * aceita `campaign_id` externo, não consulta o Google Ads.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import {
  type OcorrenciaOperacional,
  descreverFalha,
  statusDe,
} from '@/components/trafego/inventario/erros';
import type { CampanhaCanonica } from '@/types/trafego';

export const CHAVE_CAMPANHA_CANONICA = ['trafego', 'campanha'] as const;

export interface LeituraDaCampanhaCanonica {
  detalhe: CampanhaCanonica | null;
  carregando: boolean;
  naoEncontrada: boolean;
  falhou: boolean;
  ocorrencia: OcorrenciaOperacional | null;
}

export function useCampanhaCanonica(volcCampaignId: string): LeituraDaCampanhaCanonica {
  const consulta = useQuery({
    queryKey: [...CHAVE_CAMPANHA_CANONICA, volcCampaignId],
    queryFn: () => pautadorApi.campanhaCanonica(volcCampaignId),
    enabled: Boolean(volcCampaignId),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const status = statusDe(consulta.error);
  const naoEncontrada = Boolean(volcCampaignId) && status === 404;
  const falhou = consulta.isError && !naoEncontrada;

  return {
    detalhe: consulta.data ?? null,
    carregando: consulta.isLoading && consulta.data == null,
    naoEncontrada: !volcCampaignId || naoEncontrada,
    falhou,
    ocorrencia: falhou && consulta.error
      ? descreverFalha(consulta.error, 'campanha_canonica')
      : null,
  };
}
