/**
 * As quatro leituras do Hub — uma fonte para cada pergunta.
 *
 *   situacao         — o conjunto, sem recorte (barra de situação + contas)
 *   operacional      — a lista que a aba Campanhas mostra
 *   universoFiltros  — o "de N" da frase do recorte (canal, sem busca/conta)
 *   historico        — só quando o operador abre
 *
 * O inventário filho recebe estas leituras. Ele não dispara as mesmas
 * consultas de novo para a tela funcionar.
 */
import React from 'react';

import {
  consultaDoHistorico,
  consultaOperacional,
  filtrosDaBarra,
  filtrosEquivalentes,
  filtrosVazios,
} from '@/components/trafego/hub/adaptacao';
import type { EstadoDoHub } from '@/components/trafego/hub/contrato';
import { useInventario, type LeituraDoInventario } from '@/hooks/useInventario';
import type { FiltrosDoInventario } from '@/types/trafego';

export interface LeiturasDoHub {
  situacao: LeituraDoInventario;
  operacional: LeituraDoInventario;
  universoFiltros: LeituraDoInventario;
  historico: LeituraDoInventario;
  recorte: FiltrosDoInventario;
  consulta: FiltrosDoInventario;
  consultaHistorico: FiltrosDoInventario;
  recarregar: () => void;
}

export function useLeiturasDoHub(estado: EstadoDoHub): LeiturasDoHub {
  const recorte = React.useMemo(() => filtrosDaBarra(estado), [estado]);
  const consulta = React.useMemo(() => consultaOperacional(estado), [estado]);
  const consultaHistorico = React.useMemo(() => consultaDoHistorico(estado), [estado]);
  const consultaUniverso = React.useMemo(
    () => consultaOperacional({ ...estado, filtros: {} }),
    [estado],
  );

  const situacaoSemRecorte = filtrosVazios(consulta);
  const universoCoincide = filtrosEquivalentes(consultaUniverso, consulta);

  const situacao = useInventario();
  const operacionalFiltrado = useInventario(consulta, { habilitado: !situacaoSemRecorte });
  const universoFiltrado = useInventario(consultaUniverso, {
    habilitado: !filtrosVazios(consultaUniverso) && !universoCoincide,
  });
  const historico = useInventario(consultaHistorico, { habilitado: estado.historico });

  const operacional = situacaoSemRecorte ? situacao : operacionalFiltrado;
  const universoFiltros = filtrosVazios(consultaUniverso)
    ? situacao
    : universoCoincide
      ? operacional
      : universoFiltrado;

  const recarregar = React.useCallback(() => {
    situacao.recarregar();
    if (!situacaoSemRecorte) operacionalFiltrado.recarregar();
    if (!filtrosVazios(consultaUniverso) && !universoCoincide) universoFiltrado.recarregar();
    if (estado.historico) historico.recarregar();
  }, [
    situacao,
    operacionalFiltrado,
    universoFiltrado,
    historico,
    situacaoSemRecorte,
    consultaUniverso,
    universoCoincide,
    estado.historico,
  ]);

  return {
    situacao,
    operacional,
    universoFiltros,
    historico,
    recorte,
    consulta,
    consultaHistorico,
    recarregar,
  };
}
