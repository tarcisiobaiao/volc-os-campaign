/**
 * O estúdio ligado às suas leituras — capacidades e vocabulário.
 *
 * Separado de `EstudioMulticanal` porque aquele é PURO: recebe manifestos e
 * capacidades e desenha. Esta casca é quem sabe de onde eles vêm.
 *
 * ⚠️ A separação não é gosto. `EstudioMulticanal` puro é testável sem cliente
 * de consulta e sem rede, e a moldura do Hub deixa de precisar conhecer as
 * leituras que só esta aba usa — as outras três abas continuam montando sem
 * um `QueryClient` que nada nelas consome.
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';

import { FaixaDeLaboratorio } from '@/components/trafego/laboratorio/SeloDePrototipo';
import { useCapacidades } from '@/hooks/useCapacidades';
import { useVocabularioDoInventario } from '@/hooks/useVocabularioDoInventario';
import { pautadorApi } from '@/lib/pautadorApi';

import { EstudioMulticanal } from './EstudioMulticanal';

export const EstudioLigado: React.FC<{
  canal?: string | null;
  aoMudarCanal?: (canal: string) => void;
}> = ({ canal, aoMudarCanal }) => {
  const capacidades = useCapacidades();
  const vocabulario = useVocabularioDoInventario();
  const trava = useQuery({
    queryKey: ['trafego', 'trava'],
    queryFn: () => pautadorApi.estadoDaTrava(),
    retry: false,
    staleTime: 60 * 1000,
  });

  return (
    <>
      <FaixaDeLaboratorio ligado={capacidades.emLaboratorio} className="mb-5" />

      {/* ⚠️ Falha de leitura NÃO some em silêncio. Um estúdio sem canais, sem
          uma frase, lê-se como "não há canal para criar" — e o operador vai
          procurar no painel do Google o que existe aqui. */}
      {vocabulario.falhou && (
        <p className="mb-4 max-w-[70ch] text-[13px] leading-relaxed" role="alert">
          Não consegui ler quais canais este servidor opera.{' '}
          <span className="text-muted-foreground">
            Isto não significa que não haja canal — significa que a leitura não
            chegou. Recarregue em instantes.
          </span>
        </p>
      )}

      <EstudioMulticanal
        manifestos={vocabulario.manifestos}
        capacidades={capacidades.capacidades}
        trava={trava.data ?? null}
        lido={!vocabulario.carregando && !vocabulario.falhou}
        canal={canal}
        aoMudarCanal={aoMudarCanal}
      />
    </>
  );
};

export default EstudioLigado;
