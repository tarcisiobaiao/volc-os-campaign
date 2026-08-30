/**
 * Um artefato do backend dentro de um `<img>`, com credencial.
 *
 * `<img src="https://api/...">` é uma requisição que o navegador faz sozinho, e
 * ele não deixa acrescentar cabeçalho nenhum. Enquanto a rota de artefatos era
 * aberta isso funcionava; desde que ela passou a exigir identidade (24/08/2026),
 * a imagem simplesmente não carrega.
 *
 * Este hook busca o arquivo com `Authorization`, guarda um `blob:` URL e o
 * revoga quando o componente sai ou quando o alvo muda — sem `revokeObjectURL`
 * cada troca de página deixaria o arquivo inteiro preso na memória da aba.
 */
import { useEffect, useState } from 'react';

import { pautadorApi } from '@/lib/pautadorApi';

export interface ArtefatoAutenticado {
  url: string | null;
  carregando: boolean;
  erro: string | null;
}

export function useArtefatoAutenticado(
  runRowId: number | null | undefined,
  nome: string | null | undefined,
  versao?: string | number,
): ArtefatoAutenticado {
  const [estado, setEstado] = useState<ArtefatoAutenticado>({
    url: null,
    carregando: Boolean(runRowId && nome),
    erro: null,
  });

  useEffect(() => {
    if (!runRowId || !nome) {
      setEstado({ url: null, carregando: false, erro: null });
      return;
    }

    let vivo = true;
    let criada: string | null = null;
    setEstado({ url: null, carregando: true, erro: null });

    pautadorApi
      .artefatoBlobUrl(runRowId, nome, versao)
      .then((blob) => {
        if (!vivo) {
          // Chegou depois do desmonte: revoga na hora, senão vaza.
          URL.revokeObjectURL(blob);
          return;
        }
        criada = blob;
        setEstado({ url: blob, carregando: false, erro: null });
      })
      .catch((erro: unknown) => {
        if (!vivo) return;
        setEstado({
          url: null,
          carregando: false,
          erro: erro instanceof Error ? erro.message : 'Não foi possível carregar o arquivo.',
        });
      });

    return () => {
      vivo = false;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [runRowId, nome, versao]);

  return estado;
}
