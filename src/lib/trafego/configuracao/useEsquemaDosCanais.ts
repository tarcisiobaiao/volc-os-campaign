/**
 * O esquema vivo dos quatro canais, lido UMA vez por sessão do navegador.
 *
 * ⚠️ Sem React Query de propósito: a Bancada inteira lê o servidor por efeito
 * próprio (cockpit, copy, conjunto) e é montada em testes sem
 * `QueryClientProvider`. Um `useQuery` aqui derrubaria a página nesses
 * ambientes por um dado que é só régua auxiliar.
 *
 * Falha de leitura NÃO bloqueia nada: sem esquema, as opções caem nos unions
 * de `types/trafegoCanais.ts`, a conferência prévia não roda, e o servidor
 * continua sendo o juiz final no 422. `indisponivel` diz isso à tela.
 */
import { useEffect, useState } from 'react';

import { pautadorApi } from '@/lib/pautadorApi';
import type { EsquemaDosCanais } from '@/types/trafegoCanais';

let cache: EsquemaDosCanais | null = null;
let emVoo: Promise<EsquemaDosCanais> | null = null;

/** Só para testes: esquece o que foi lido. */
export function esquecerEsquemaDosCanais(): void {
  cache = null;
  emVoo = null;
}

export function useEsquemaDosCanais(): {
  esquemas: EsquemaDosCanais | null;
  indisponivel: string | null;
} {
  const [esquemas, setEsquemas] = useState<EsquemaDosCanais | null>(cache);
  const [indisponivel, setIndisponivel] = useState<string | null>(null);

  useEffect(() => {
    if (cache) return;
    let ativo = true;
    void (async () => {
      try {
        emVoo ??= pautadorApi.esquemaDosCanais();
        const lido = await emVoo;
        if (!lido?.canais) throw new Error('resposta sem `canais`');
        cache = lido;
        if (ativo) setEsquemas(lido);
      } catch (e) {
        emVoo = null;
        if (ativo) {
          setIndisponivel(e instanceof Error
            ? `Não deu para ler o esquema dos canais (${e.message}). As opções usam a lista do contrato v1 e a forma é julgada só pelo servidor.`
            : 'Não deu para ler o esquema dos canais. A forma é julgada só pelo servidor.');
        }
      }
    })();
    return () => { ativo = false; };
  }, []);

  return { esquemas, indisponivel };
}
