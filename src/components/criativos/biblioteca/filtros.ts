/**
 * Os filtros da biblioteca como DADO, e a lista de remoção que deles nasce.
 *
 * DESIGN.md: "Every active filter is removable and the result count states both
 * the visible subset and the universe." Um filtro que a tela aplica e não
 * mostra é a forma mais barata de fazer alguém concluir que um ativo sumiu.
 */
import type { KindDeMaster } from '@/types/criativos';
import { destinoLegivel, dia, kindLegivel } from '@/components/criativos/comum/formato';

export type EstadoDeAprovacaoFiltravel =
  | ''
  | 'aguardando'
  | 'aprovado'
  | 'ajuste_solicitado'
  | 'rejeitado';

export interface FiltrosDaBiblioteca {
  busca: string;
  kind: KindDeMaster | '';
  estado: EstadoDeAprovacaoFiltravel;
  brandPack: string;
  destino: string;
  desde: string;
  ate: string;
}

export const FILTROS_VAZIOS: FiltrosDaBiblioteca = {
  busca: '',
  kind: '',
  estado: '',
  brandPack: '',
  destino: '',
  desde: '',
  ate: '',
};

export const ROTULO_DO_ESTADO_FILTRAVEL: Record<Exclude<EstadoDeAprovacaoFiltravel, ''>, string> = {
  aguardando: 'Aguardando revisão',
  aprovado: 'Aprovado',
  ajuste_solicitado: 'Ajuste pedido',
  rejeitado: 'Rejeitado',
};

export interface FiltroAtivo {
  chave: keyof FiltrosDaBiblioteca;
  rotulo: string;
  valor: string;
}

export function temFiltro(f: FiltrosDaBiblioteca): boolean {
  return (Object.keys(FILTROS_VAZIOS) as (keyof FiltrosDaBiblioteca)[]).some(
    (k) => f[k] !== FILTROS_VAZIOS[k],
  );
}

/**
 * Um item por filtro ativo, com rótulo legível.
 *
 * `nomeDoPack` entra por parâmetro porque o identificador do brand pack é um
 * UUID: mostrar o UUID como se fosse o nome do pack é a mesma classe de defeito
 * que mostrar `gerando_voz` como etapa.
 */
export function filtrosAtivos(
  f: FiltrosDaBiblioteca,
  nomeDoPack: (id: string) => string = (id) => id,
): FiltroAtivo[] {
  const itens: FiltroAtivo[] = [];
  if (f.busca) itens.push({ chave: 'busca', rotulo: 'Busca', valor: f.busca });
  if (f.kind) itens.push({ chave: 'kind', rotulo: 'Tipo', valor: kindLegivel(f.kind) });
  if (f.estado) {
    itens.push({ chave: 'estado', rotulo: 'Estado', valor: ROTULO_DO_ESTADO_FILTRAVEL[f.estado] });
  }
  if (f.brandPack) {
    itens.push({ chave: 'brandPack', rotulo: 'Brand pack', valor: nomeDoPack(f.brandPack) });
  }
  if (f.destino) {
    itens.push({ chave: 'destino', rotulo: 'Destino', valor: destinoLegivel(f.destino) });
  }
  if (f.desde) itens.push({ chave: 'desde', rotulo: 'A partir de', valor: dia(f.desde) });
  if (f.ate) itens.push({ chave: 'ate', rotulo: 'Até', valor: dia(f.ate) });
  return itens;
}

export function removerFiltro(
  f: FiltrosDaBiblioteca,
  chave: keyof FiltrosDaBiblioteca,
): FiltrosDaBiblioteca {
  return { ...f, [chave]: FILTROS_VAZIOS[chave] };
}

/**
 * A contagem que diz o recorte E o universo.
 *
 * "12" sozinho não responde se a busca achou pouco ou se existe pouco.
 */
export function contagemLegivel(total: number, universo: number, comFiltro: boolean): string {
  if (!comFiltro && total === universo) {
    return `${universo} ${universo === 1 ? 'ativo' : 'ativos'} na biblioteca`;
  }
  return `${total} de ${universo} ${universo === 1 ? 'ativo' : 'ativos'}`;
}

/**
 * A contagem que a tela pode AFIRMAR, dado o estado da leitura.
 *
 * ⚠️ Conserto do defeito D5 da auditoria P17. A `BibliotecaPage` montava a frase
 * com `total = consulta.data?.total ?? 0` e ramificava só em `isLoading`. Quando
 * a leitura FALHAVA, `isLoading` já era falso, `data` era `undefined` e o painel
 * de filtros escrevia "0 ativos neste recorte" — logo acima do próprio alerta de
 * erro de leitura. Zero medido e leitura que não chegou viravam a mesma frase, e
 * é a diferença entre "não existe ativo" e "não sei o que existe".
 *
 * Os quatro casos são fatos diferentes com ações diferentes: esperar, tentar de
 * novo, ler o recorte sabendo que o total não veio, ou confiar no número.
 */
export interface SituacaoDaContagem {
  carregando: boolean;
  erro: boolean;
  /** `null` = a leitura não trouxe número nenhum. Nunca substituir por `0`. */
  total: number | null;
  /** `null` = o servidor não informou o total sem filtro. */
  universo: number | null;
  comFiltro: boolean;
}

export function fraseDaContagem(s: SituacaoDaContagem): string {
  if (s.carregando) return 'Contagem ainda não lida.';
  if (s.erro || s.total === null) {
    return 'A contagem não chegou nesta leitura. Nenhum ativo desapareceu; o que falhou foi a leitura.';
  }
  if (s.universo === null) {
    const recorte = `${s.total} ${s.total === 1 ? 'ativo neste recorte' : 'ativos neste recorte'}`;
    return `${recorte}. O servidor não informou o total da biblioteca.`;
  }
  return contagemLegivel(s.total, s.universo, s.comFiltro);
}
