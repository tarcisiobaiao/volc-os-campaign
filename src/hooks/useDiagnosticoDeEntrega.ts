/**
 * A leitura do diagnóstico de entrega de UMA campanha.
 *
 * ## As quatro respostas, que são quatro fatos diferentes
 *
 *  - `carregando` — ainda lendo;
 *  - `diagnostico` — apurado, e a escada diz o resto;
 *  - `naoImplementado` — este servidor ainda não apura diagnóstico. Não é falha
 *    da campanha nem falha de rede: é uma capacidade que não existe aqui;
 *  - `ocorrencia` — a leitura falhou de verdade, com código para copiar.
 *
 * ⚠️ Nenhuma delas degrada para "está tudo bem". Uma tela que trata "o servidor
 * não sabe apurar" como "nada a reportar" convida o operador a mexer em gasto
 * apoiado num diagnóstico que nunca existiu.
 *
 * Zero Google Ads: o backend projeta o que a apuração já gravou.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import {
  type OcorrenciaOperacional,
  descreverFalha,
  statusDe,
} from '@/components/trafego/inventario/erros';
import type { CaixaDePropostas, DiagnosticoDeEntrega } from '@/types/diagnostico';

export const CHAVE_DIAGNOSTICO = ['trafego', 'diagnostico'] as const;

export interface LeituraDoDiagnostico {
  diagnostico: DiagnosticoDeEntrega | null;
  propostas: CaixaDePropostas | null;
  carregando: boolean;
  /**
   * `true` quando o servidor não tem a rota de diagnóstico.
   *
   * `404` e `501` chegam aqui juntos porque, do lado da tela, dizem a mesma
   * coisa útil: esta capacidade não está ligada neste servidor. A distinção
   * entre "campanha inexistente" e "rota inexistente" já foi feita na página
   * canônica, que carrega a campanha por outra rota antes desta.
   */
  naoImplementado: boolean;
  ocorrencia: OcorrenciaOperacional | null;
}

export function useDiagnosticoDeEntrega(volcCampaignId: string): LeituraDoDiagnostico {
  const consulta = useQuery({
    queryKey: [...CHAVE_DIAGNOSTICO, volcCampaignId],
    queryFn: () => pautadorApi.diagnosticoDeEntrega(volcCampaignId),
    enabled: Boolean(volcCampaignId),
    retry: false,
    // Diagnóstico é caro de apurar do lado do servidor e não muda de minuto em
    // minuto. Refazer a cada foco de janela custaria apuração sem mudar decisão.
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const status = statusDe(consulta.error);
  const naoImplementado = status === 404 || status === 501;
  const falhou = consulta.isError && !naoImplementado;

  return {
    diagnostico: consulta.data?.diagnostico ?? null,
    propostas: consulta.data?.propostas ?? null,
    carregando: consulta.isLoading && consulta.data == null,
    naoImplementado,
    ocorrencia:
      falhou && consulta.error ? descreverFalha(consulta.error, 'campanha_canonica') : null,
  };
}
