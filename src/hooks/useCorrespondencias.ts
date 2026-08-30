/**
 * De quem é esta campanha? — a leitura, e a resposta humana.
 *
 * ## Por que este hook existe
 *
 * `POST /api/trafego/vinculos` existe desde 26/08/2026 e `trafego_vinculo`
 * continua com zero linhas. Não porque a gravação falhe: porque nenhuma
 * superfície chegava até ela. O selo do inventário mostra "sem vínculo" e não
 * oferece caminho para deixar de estar.
 *
 * ## Sugerir e responder são coisas diferentes
 *
 * A leitura SUGERE — e a sugestão não vira vínculo por ser única, por ser forte
 * ou por o operador ter olhado para ela. Confirmar é uma mutação separada, com
 * regra e evidência explícitas, e quem confirmou sai do token no servidor
 * (ADR-09).
 *
 * ⚠️ Nada aqui toca no Google Ads. Confirmar vínculo grava no NOSSO banco: não
 * cria campanha, não altera lance, não gasta um centavo.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import {
  type OcorrenciaOperacional,
  descreverFalha,
  statusDe,
} from '@/components/trafego/inventario/erros';
import { CHAVE_CAMPANHA_CANONICA } from '@/hooks/useCampanhaCanonica';
import type { Correspondencia, RevisaoDeCorrespondencia } from '@/types/trafego';

export const CHAVE_CORRESPONDENCIAS = ['trafego', 'correspondencias'] as const;

export interface LeituraDasCorrespondencias {
  revisao: RevisaoDeCorrespondencia | null;
  carregando: boolean;
  naoEncontrada: boolean;
  falhou: boolean;
  ocorrencia: OcorrenciaOperacional | null;
  recarregar: () => void;
}

export function useCorrespondencias(volcCampaignId: string): LeituraDasCorrespondencias {
  const consulta = useQuery({
    queryKey: [...CHAVE_CORRESPONDENCIAS, volcCampaignId],
    queryFn: () => pautadorApi.correspondenciasDaCampanha(volcCampaignId),
    enabled: Boolean(volcCampaignId),
    retry: false,
    // Curto: o operador confirma, volta e precisa ver o resultado da própria
    // decisão. Cache longo aqui mostraria a pergunta já respondida.
    staleTime: 30 * 1000,
  });

  const status = statusDe(consulta.error);
  const naoEncontrada = Boolean(volcCampaignId) && status === 404;
  const falhou = consulta.isError && !naoEncontrada;

  return {
    revisao: consulta.data ?? null,
    carregando: consulta.isLoading && consulta.data == null,
    naoEncontrada,
    falhou,
    ocorrencia:
      falhou && consulta.error
        ? descreverFalha(consulta.error, 'correspondencias')
        : null,
    recarregar: () => void consulta.refetch(),
  };
}

/**
 * A regra que o operador está aceitando, montada da evidência — não digitada.
 *
 * ⚠️ O servidor RECUSA vínculo sem regra (`trafego_vinculo_regra_nao_vazia`), e
 * não é formalidade: um vínculo sem regra visível é uma caixa-preta que o
 * operador não tem como contestar depois. Derivá-la dos sinais garante que a
 * frase gravada descreva o que de fato casou, e não o que alguém lembrou de
 * escrever.
 */
export function regraDaCorrespondencia(c: Correspondencia): string {
  const regras = c.sinais.map((s) => `${s.regra}(${s.forca})`).join(' + ');
  return regras || 'confirmacao_manual_sem_sinal';
}

export interface PedidoDeConfirmacao {
  volcCampaignId: string;
  correspondencia: Correspondencia;
  /** O vínculo que este substitui, quando há. Reconstrói a cadeia de decisões. */
  vinculoAnterior?: string;
}

/**
 * Confirma o vínculo e reflete a decisão nas telas que dependem dela.
 *
 * ⚠️ Invalida a campanha canônica junto. Sem isso o selo do inventário e o
 * detalhe continuariam dizendo "sem vínculo" logo depois de o operador
 * vincular — e uma tela que não reflete a própria ação ensina o operador a
 * clicar duas vezes.
 */
export function useConfirmarVinculo() {
  const cliente = useQueryClient();

  return useMutation({
    mutationFn: ({ volcCampaignId, correspondencia, vinculoAnterior }: PedidoDeConfirmacao) =>
      pautadorApi.confirmarVinculo({
        volc_campaign_id: volcCampaignId,
        opportunity_id: correspondencia.opportunity_id,
        project_id: correspondencia.project_id ?? undefined,
        funnel_run_id: correspondencia.run_id ?? undefined,
        regra: regraDaCorrespondencia(correspondencia),
        // A evidência viaja inteira: é ela que permite reconstruir POR QUE
        // alguém decidiu isto, meses depois, sem depender de memória.
        evidencia: {
          sinais: correspondencia.sinais,
          destinos: correspondencia.destinos,
          estado_do_funil: correspondencia.estado_do_funil,
          outras_campanhas_presentes: correspondencia.outras_campanhas_presentes,
        },
        vinculo_anterior: vinculoAnterior,
      }),
    onSuccess: (_dados, variaveis) => {
      void cliente.invalidateQueries({
        queryKey: [...CHAVE_CORRESPONDENCIAS, variaveis.volcCampaignId],
      });
      void cliente.invalidateQueries({
        queryKey: [...CHAVE_CAMPANHA_CANONICA, variaveis.volcCampaignId],
      });
      void cliente.invalidateQueries({ queryKey: ['trafego', 'inventario'] });
    },
  });
}

export function useDesfazerVinculo() {
  const cliente = useQueryClient();

  return useMutation({
    mutationFn: ({ vinculoId, motivo }: { vinculoId: string; motivo?: string; volcCampaignId: string }) =>
      pautadorApi.desfazerVinculo(vinculoId, motivo),
    onSuccess: (_dados, variaveis) => {
      void cliente.invalidateQueries({
        queryKey: [...CHAVE_CORRESPONDENCIAS, variaveis.volcCampaignId],
      });
      void cliente.invalidateQueries({
        queryKey: [...CHAVE_CAMPANHA_CANONICA, variaveis.volcCampaignId],
      });
      void cliente.invalidateQueries({ queryKey: ['trafego', 'inventario'] });
    },
  });
}
