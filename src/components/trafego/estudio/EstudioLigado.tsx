/**
 * O estúdio ligado às suas leituras — capacidades, vocabulário e portões.
 *
 * Separado de `EstudioMulticanal` porque aquele é PURO: recebe manifestos e
 * capacidades e desenha. Esta casca é quem sabe de onde eles vêm.
 *
 * ⚠️ A separação não é gosto. `EstudioMulticanal` puro é testável sem cliente
 * de consulta e sem rede, e a moldura do Hub deixa de precisar conhecer as
 * leituras que só esta aba usa — as outras três abas continuam montando sem
 * um `QueryClient` que nada nelas consome.
 *
 * ## A leitura que faltava
 *
 * Até 03/09/2026 esta casca lia capacidades, vocabulário e trava — e não lia
 * `GET /canais`, que é onde mora o VEREDITO. O vocabulário responde "este canal
 * sabe criar?"; os portões respondem "e eu posso criar nele agora, e se não, por
 * quê?". Display responde `sabe_criar: true` no manifesto e `criavel_pausada:
 * BLOQUEADO` no portão, porque a janela do canário só admite Search — e a tela
 * que lesse apenas o manifesto ofereceria Display até o servidor recusar no
 * clique, depois de o operador montar o pedido inteiro.
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';

import { FaixaDeLaboratorio } from '@/components/trafego/laboratorio/SeloDePrototipo';
import { useCanais } from '@/components/trafego/canais/useCanais';
import { useCapacidades } from '@/hooks/useCapacidades';
import { useVocabularioDoInventario } from '@/hooks/useVocabularioDoInventario';
import { pautadorApi } from '@/lib/pautadorApi';
import { canalCanonico } from '@/types/trafego';

import { EstudioMulticanal } from './EstudioMulticanal';
import { JornadaDoCanal } from './JornadaDoCanal';

export const EstudioLigado: React.FC<{
  canal?: string | null;
  aoMudarCanal?: (canal: string) => void;
}> = ({ canal, aoMudarCanal }) => {
  const capacidades = useCapacidades();
  const vocabulario = useVocabularioDoInventario();
  const canais = useCanais();
  const trava = useQuery({
    queryKey: ['trafego', 'trava'],
    queryFn: () => pautadorApi.estadoDaTrava(),
    retry: false,
    staleTime: 60 * 1000,
  });

  // ⚠️ `PMAX` é apelido de tela para `PERFORMANCE_MAX` e precisa continuar
  // abrindo — links antigos usam a forma curta. A normalização já existe uma
  // vez, em `types/trafego.ts`; refazê-la aqui criaria a segunda cópia.
  const escolhido = canal ? canalCanonico(canal) : null;
  const contrato =
    escolhido != null
      ? (canais.data?.canais.find((c) => c.canal === escolhido) ?? null)
      : null;

  /**
   * A trava, em três valores e não dois.
   *
   * ⚠️ `null` significa NÃO APURADO — a leitura falhou ou ainda não chegou — e
   * a conversa o trata como fechado. Colapsar "não sei" em "aberta" é o erro
   * que custa uma campanha criada por engano; colapsar em "fechada" mentiria
   * para o lado seguro, e por isso a conversa nomeia os dois casos separados.
   */
  const travaAberta: boolean | null = trava.isSuccess
    ? (trava.data?.escrita_permitida ?? false)
    : null;

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

      {/* A jornada só existe depois de um canal escolhido: os quatro portões
          respondem sobre UM canal, e uma escada sem sujeito não responde nada. */}
      {escolhido != null && (
        <div className="mt-10 border-t border-border pt-8">
          <JornadaDoCanal
            contrato={contrato}
            travaAberta={travaAberta}
            podeAprovar={capacidades.capacidades?.is_admin === true}
            carregando={canais.isLoading}
            falhou={canais.isError}
            aoRevalidar={() => void canais.refetch()}
          />
        </div>
      )}
    </>
  );
};

export default EstudioLigado;
