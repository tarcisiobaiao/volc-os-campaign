/**
 * O estado do Hub mora na URL. Este hook é a única porta de leitura/escrita.
 *
 * Um recorte que não sobrevive ao recarregamento não pode ser compartilhado.
 * `?rede=google&aba=campanhas&canal=SEARCH` é o que alguém cola no chat.
 */
import React from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  escreverEstadoDoHub,
  lerEstadoDoHub,
} from '@/components/trafego/hub/adaptacao';
import type { EstadoDoHub } from '@/components/trafego/hub/contrato';
import type { FiltrosDoInventario } from '@/types/trafego';

export function useEstadoDoHub() {
  const [params, setParams] = useSearchParams();

  const estado = React.useMemo(() => lerEstadoDoHub(params), [params]);

  const aplicar = React.useCallback(
    (patch: Partial<EstadoDoHub> & { filtros?: FiltrosDoInventario }) => {
      setParams(escreverEstadoDoHub(params, patch), { replace: true });
    },
    [params, setParams],
  );

  return { estado, aplicar, params };
}
