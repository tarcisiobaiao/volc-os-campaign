/**
 * O catálogo do Estúdio: formatos oferecidos e brand packs.
 *
 * ## Por que o fallback dos formatos é o do CONTRATO
 *
 * `FORMATOS_DE_IMAGEM` vive em `types/criativos.ts` porque o backend valida
 * contra a MESMA lista. Quando a leitura do catálogo falha, cair para a lista
 * do contrato oferece exatamente os slots que o motor conhece. Cair para uma
 * lista escrita à mão no componente ofereceria um slot que o servidor recusa
 * depois do formulário inteiro preenchido.
 *
 * ⚠️ O fallback é DECLARADO por `doContrato`, para que a tela possa dizer que
 * está oferecendo a lista local em vez de fingir que leu do servidor.
 */
import { useQuery } from '@tanstack/react-query';

import { criativosApi } from '@/lib/criativosApi';
import { FORMATOS_DE_IMAGEM, type BrandPack, type FormatoDisponivel } from '@/types/criativos';

export const CHAVE_FORMATOS = ['criativos', 'formatos'] as const;
export const CHAVE_BRAND_PACKS = ['criativos', 'brand-packs'] as const;

export interface LeituraDeFormatos {
  formatos: readonly FormatoDisponivel[];
  /** `true` quando a lista veio do contrato local, não do servidor. */
  doContrato: boolean;
  carregando: boolean;
  /**
   * O servidor tem credencial de provedor.
   *
   * ⚠️ `null` é "ainda não sei", e quem consome trata ignorância como
   * "não pode": um botão de gasto que aparece enquanto a leitura não chegou é
   * um botão clicável, e o pedido morre no servidor depois do formulário todo.
   */
  motorConfigurado: boolean | null;
}

export function useCriativosFormatos(): LeituraDeFormatos {
  const consulta = useQuery({
    queryKey: CHAVE_FORMATOS,
    queryFn: () => criativosApi.formatos(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const lidos = consulta.data?.formatos;
  const temLeitura = Array.isArray(lidos) && lidos.length > 0;
  return {
    formatos: temLeitura ? lidos : FORMATOS_DE_IMAGEM,
    doContrato: !temLeitura,
    carregando: consulta.isLoading,
    motorConfigurado: consulta.data ? consulta.data.motorConfigurado : null,
  };
}

export interface LeituraDeBrandPacks {
  brandPacks: BrandPack[];
  carregando: boolean;
  erro: unknown;
  /** Nome legível de um pack, para a tela nunca mostrar UUID cru. */
  nomeDoPack: (id: string) => string;
  recarregar: () => void;
}

export function useCriativosBrandPacks(): LeituraDeBrandPacks {
  const consulta = useQuery({
    queryKey: CHAVE_BRAND_PACKS,
    queryFn: () => criativosApi.brandPacks(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const brandPacks = consulta.data?.brandPacks ?? [];
  return {
    brandPacks,
    carregando: consulta.isLoading,
    erro: consulta.error,
    nomeDoPack: (id: string) => {
      const pack = brandPacks.find((p) => p.id === id);
      return pack ? `${pack.nome} v${pack.versao}` : 'pack não identificado';
    },
    recarregar: () => void consulta.refetch(),
  };
}
