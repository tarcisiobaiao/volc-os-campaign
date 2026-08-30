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
