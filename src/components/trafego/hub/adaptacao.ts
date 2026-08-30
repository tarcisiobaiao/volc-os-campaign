/**
 * Ponto único de adaptação entre a URL / a tela e `FiltrosDoInventario`.
 *
 * Divergências conscientes (também em ADAPTACAO.md):
 *
 * 1. O contrato v2 exclui histórico no padrão (`incluir_historico`).
 *    `totais.operacionais` / `totais.historicas` substituem `totais.campanhas`.
 * 2. O canal canônico é `PERFORMANCE_MAX` (tela, URL e contrato). `PMAX` só
 *    entra como alias legado e é normalizado na hora via `canalCanonico`.
 *    `VIDEO` e `SHOPPING` são reconhecidos; o Hub não os opera.
 * 3. `aba=oportunidades` continua válido e vira Preparar.
 * 4. Meta ainda não tem endpoint. A tela não consulta o inventário Google
 *    fingindo que é Meta.
 * 5. A ordem das campanhas é a do servidor. Este arquivo não reordena.
 */
import { canalCanonico, type Canal, type FiltrosDoInventario } from '@/types/trafego';

import {
  ABAS_DO_HUB,
  ESTADO_PADRAO,
  NIVEIS_META,
  type AbaDoHub,
  type CanalDoHub,
  type EstadoDoHub,
  type NivelMeta,
  type RedeDoHub,
} from './contrato';

export function canalDaUrl(valor: string | null): CanalDoHub | null {
  return canalCanonico(valor);
}

export function canalParaUrl(canal: CanalDoHub): string {
  return canal;
}

/** Identidade: tela e contrato já falam PERFORMANCE_MAX. */
export function canalParaContrato(canal: CanalDoHub): Canal {
  return canal;
}

export function abaDaUrl(valor: string | null): AbaDoHub {
  if (valor === 'oportunidades') return 'preparar';
  if (valor && (ABAS_DO_HUB as readonly string[]).includes(valor)) {
    return valor as AbaDoHub;
  }
  return ESTADO_PADRAO.aba;
}

export function abaParaUrl(aba: AbaDoHub): string {
  return aba;
}

export function redeDaUrl(valor: string | null): RedeDoHub {
  return valor === 'meta' ? 'meta' : 'google';
}

export function nivelDaUrl(valor: string | null): NivelMeta {
  if (valor && (NIVEIS_META as readonly string[]).includes(valor)) {
    return valor as NivelMeta;
  }
  return ESTADO_PADRAO.nivel;
}

export function lerEstadoDoHub(params: URLSearchParams): EstadoDoHub {
  const filtros: FiltrosDoInventario = {};
  const busca = params.get('busca');
  if (busca) filtros.busca = busca;
  const conta = params.get('conta');
  if (conta) filtros.conta = [conta];
  const estado = params.get('estado');
  if (estado) filtros.estado_externo = [estado];
  if (params.get('atencao') === '1') filtros.atencao = true;

  const canal = canalDaUrl(params.get('canal'));
  if (canal) filtros.canal = [canalParaContrato(canal)];

  return {
    rede: redeDaUrl(params.get('rede')),
    aba: abaDaUrl(params.get('aba')),
    canal,
    nivel: nivelDaUrl(params.get('nivel')),
    historico: params.get('historico') === '1',
    filtros,
    foco: params.get('foco'),
  };
}

/**
 * Recorte que a barra de filtros mostra e edita.
 *
 * Canal, rede, aba e histórico NÃO entram aqui: são eixos da moldura, e
 * "limpar filtros" não pode apagar o canal que o operador escolheu acima.
 */
export function filtrosDaBarra(estado: EstadoDoHub): FiltrosDoInventario {
  const { busca, conta, estado_externo, atencao } = estado.filtros;
  return {
    ...(busca ? { busca } : {}),
    ...(conta?.length ? { conta } : {}),
    ...(estado_externo?.length ? { estado_externo } : {}),
    ...(atencao ? { atencao: true } : {}),
  };
}

/**
 * Recorte enviado ao servidor para a lista OPERACIONAL.
 *
 * O contrato v2 já exclui o histórico removido no padrão. Não injetamos
 * ENABLED+PAUSED: isso zeraria `totais.historicas` e o botão do histórico
 * perderia a quantidade. Estado escolhido na barra continua indo ao servidor.
 */
export function consultaOperacional(estado: EstadoDoHub): FiltrosDoInventario {
  const filtros: FiltrosDoInventario = { ...filtrosDaBarra(estado) };
  if (estado.canal) filtros.canal = [canalParaContrato(estado.canal)];
  if (estado.filtros.estado_externo?.[0] === 'REMOVED') {
    delete filtros.estado_externo;
  }
  return filtros;
}

/** Recorte enviado ao servidor só para listar o histórico removido. */
export function consultaDoHistorico(estado: EstadoDoHub): FiltrosDoInventario {
  const filtros: FiltrosDoInventario = { ...filtrosDaBarra(estado) };
  delete filtros.estado_externo;
  if (estado.canal) filtros.canal = [canalParaContrato(estado.canal)];
  filtros.incluir_historico = true;
  filtros.estado_externo = ['REMOVED'];
  return filtros;
}

/** Contagem operacional do envelope v2. Ausência nunca vira zero. */
export function totaisOperacionais(
  totais: { operacionais?: number } | null | undefined,
): number | null {
  return totais?.operacionais ?? null;
}

/** Contagem do histórico removido no envelope v2. */
export function totaisHistoricas(
  totais: { historicas?: number } | null | undefined,
): number | null {
  return totais?.historicas ?? null;
}

export function escreverEstadoDoHub(
  atual: URLSearchParams,
  patch: Partial<EstadoDoHub> & { filtros?: FiltrosDoInventario },
): URLSearchParams {
  const proximo = new URLSearchParams(atual);
  const estado = { ...lerEstadoDoHub(atual), ...patch };

  if (patch.filtros) {
    estado.filtros = patch.filtros;
  }

  setOuApaga(proximo, 'rede', estado.rede === 'google' ? null : estado.rede);
  setOuApaga(proximo, 'aba', estado.aba === 'campanhas' ? null : abaParaUrl(estado.aba));
  setOuApaga(proximo, 'canal', estado.canal ? canalParaUrl(estado.canal) : null);
  setOuApaga(proximo, 'nivel', estado.rede === 'meta' && estado.nivel !== 'campanhas' ? estado.nivel : null);
  setOuApaga(proximo, 'historico', estado.historico ? '1' : null);
  setOuApaga(proximo, 'foco', estado.aba === 'atencao' ? estado.foco : null);

  for (const chave of ['busca', 'conta', 'estado', 'atencao']) proximo.delete(chave);
  const barra = filtrosDaBarra(estado);
  if (barra.busca) proximo.set('busca', barra.busca);
  if (barra.conta?.[0]) proximo.set('conta', barra.conta[0]);
  if (barra.estado_externo?.[0] && barra.estado_externo[0] !== 'REMOVED') {
    proximo.set('estado', barra.estado_externo[0]);
  }
  if (barra.atencao) proximo.set('atencao', '1');
  if (barra.estado_externo?.[0] === 'REMOVED') proximo.set('historico', '1');

  return proximo;
}

function setOuApaga(params: URLSearchParams, chave: string, valor: string | null | undefined) {
  if (!valor) params.delete(chave);
  else params.set(chave, valor);
}

export function canalReconhecido(canal: string | null | undefined): canal is CanalDoHub {
  return canalDaUrl(canal ?? null) != null;
}

function corpoDosFiltros(filtros?: FiltrosDoInventario | null): Record<string, unknown> | null {
  if (!filtros) return null;
  const corpo: Record<string, unknown> = {};
  for (const chave of Object.keys(filtros).sort()) {
    const valor = filtros[chave as keyof FiltrosDoInventario];
    if (valor === undefined || valor === null || valor === false) continue;
    if (Array.isArray(valor) && valor.length === 0) continue;
    if (chave === 'busca' && String(valor).trim() === '') continue;
    corpo[chave] = valor;
  }
  return Object.keys(corpo).length === 0 ? null : corpo;
}

export function filtrosVazios(filtros?: FiltrosDoInventario | null): boolean {
  return corpoDosFiltros(filtros) == null;
}

export function filtrosEquivalentes(
  a?: FiltrosDoInventario | null,
  b?: FiltrosDoInventario | null,
): boolean {
  return JSON.stringify(corpoDosFiltros(a)) === JSON.stringify(corpoDosFiltros(b));
}
