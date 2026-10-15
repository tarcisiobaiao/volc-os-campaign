/**
 * Antes → depois, nos dois momentos em que a tela precisa mostrá-lo.
 *
 * 1. `previaDaAcao` — na CONFIRMAÇÃO de uma proposta nova. O "antes" é o que a
 *    página já leu da campanha (inventário); quando não há leitura, diz que o
 *    servidor vai ler na conta, e não inventa número. O antes que vale é o que
 *    o servidor grava ao propor — e é esse que a fila mostra.
 * 2. `linhasDoDiff` — na FILA. Sai de `valor_atual`/`valor_proposto` gravados
 *    (congelados pelo gatilho `trafego_proposta_diff_imutavel`). É este diff
 *    que vai, sem retoque, como `diff_apresentado` na aprovação.
 *
 * Módulo puro: sem React, sem HTTP.
 */
import { AUSENTE, dinheiro } from '@/components/trafego/inventario/formato';
import type { AcaoDeGestao, DiffApresentado, PropostaDoPainel, ValorDoLedger } from '@/types/gestao';

import { DIAS, DISPOSITIVOS, ROTULO_DA_ESTRATEGIA, alvoDaEstrategia } from './acoes';

export interface LinhaDeDiff {
  rotulo: string;
  antes: string | null;
  depois: string | null;
}

export interface LeituraDaCampanha {
  estadoExterno: string | null;
  verbaDiariaMicros: number | null;
  estrategia: string | null;
  moeda: string | null;
}

export const LIDO_AO_PROPOR = 'lido na conta ao propor';

const STATUS: Record<string, string> = { ENABLED: 'ativa', PAUSED: 'pausada', REMOVED: 'removida' };

function pct(modificador: number | null | undefined): string {
  if (modificador == null) return 'sem ajuste';
  if (modificador === 0) return '−100% (não exibe)';
  const v = Math.round((modificador - 1) * 1000) / 10;
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toLocaleString('pt-BR')}%`;
}

function roas(razao: number): string {
  return `${(Math.round(razao * 10000) / 100).toLocaleString('pt-BR')}%`;
}

function diaLegivel(dia: string): string {
  return DIAS.find((d) => d.dia === dia)?.rotulo ?? dia;
}

function resumoDeLista<T>(itens: T[], f: (i: T) => string, max = 4): string {
  const ds = itens.slice(0, max).map(f);
  return itens.length > max ? `${ds.join(', ')} e mais ${itens.length - max}` : ds.join(', ');
}

/** A confirmação: o que esta ação muda, com o antes que a página conhece. */
export function previaDaAcao(acao: AcaoDeGestao, leitura: LeituraDaCampanha): LinhaDeDiff[] {
  const moeda = leitura.moeda;
  switch (acao.tipo) {
    case 'status':
      return [
        {
          rotulo: `estado (${acao.nivel} ${acao.ident})`,
          antes:
            acao.nivel === 'campanha' && leitura.estadoExterno
              ? (STATUS[leitura.estadoExterno] ?? leitura.estadoExterno)
              : LIDO_AO_PROPOR,
          depois: STATUS[acao.status] ?? acao.status,
        },
      ];
    case 'orcamento.diario':
      return [
        {
          rotulo: 'verba diária',
          antes: leitura.verbaDiariaMicros != null ? dinheiro(leitura.verbaDiariaMicros, moeda) : LIDO_AO_PROPOR,
          depois: dinheiro(acao.amount_micros, moeda),
        },
      ];
    case 'lance.alvo': {
      const a = alvoDaEstrategia(acao.estrategia ?? leitura.estrategia);
      return [
        {
          rotulo: a?.rotulo ?? acao.alvo,
          antes: LIDO_AO_PROPOR,
          depois:
            acao.alvo === 'troas'
              ? acao.valor === 0
                ? 'sem alvo'
                : roas(acao.valor)
              : acao.valor === 0
                ? 'sem alvo'
                : dinheiro(acao.valor, moeda),
        },
      ];
    }
    case 'lance.estrategia': {
      const linhas: LinhaDeDiff[] = [
        {
          rotulo: 'estratégia de lance',
          antes: leitura.estrategia ? (ROTULO_DA_ESTRATEGIA[leitura.estrategia] ?? leitura.estrategia) : LIDO_AO_PROPOR,
          depois: ROTULO_DA_ESTRATEGIA[acao.nova] ?? acao.nova,
        },
      ];
      if (acao.tcpa_micros) linhas.push({ rotulo: 'CPA desejado', antes: null, depois: dinheiro(acao.tcpa_micros, moeda) });
      if (acao.troas) linhas.push({ rotulo: 'ROAS desejado', antes: null, depois: roas(acao.troas) });
      if (acao.teto_cpc_micros) {
        linhas.push({ rotulo: 'teto de CPC', antes: null, depois: dinheiro(acao.teto_cpc_micros, moeda) });
      }
      if (acao.portfolio) linhas.push({ rotulo: 'portfólio', antes: null, depois: acao.portfolio });
      return linhas;
    }
    case 'negativa.keyword':
      return [
        {
          rotulo: `negativas no ${acao.escopo} ${acao.alvo}`,
          antes: LIDO_AO_PROPOR,
          depois: `+ ${resumoDeLista(acao.termos, (t) => `${t.texto} (${t.correspondencia})`)}`,
        },
      ];
    case 'lista.criar':
      return [
        { rotulo: 'lista compartilhada', antes: null, depois: `${acao.nome} (${acao.tipo_lista})` },
        { rotulo: 'itens', antes: null, depois: `${acao.itens.length}` },
        {
          rotulo: 'anexada a',
          antes: null,
          depois: acao.campanhas?.length ? acao.campanhas.join(', ') : 'nenhuma campanha',
        },
      ];
    case 'lista.adicionar':
      return [
        {
          rotulo: `lista ${acao.shared_set_id}`,
          antes: LIDO_AO_PROPOR,
          depois: `+ ${acao.itens.length} ${acao.itens.length === 1 ? 'item' : 'itens'}`,
        },
      ];
    case 'lista.anexar':
      return [{ rotulo: `lista ${acao.shared_set_id} anexada a`, antes: LIDO_AO_PROPOR, depois: acao.campanhas.join(', ') }];
    case 'exclusao.placement':
      return [
        {
          rotulo: `placements excluídos (${acao.escopo})`,
          antes: LIDO_AO_PROPOR,
          depois: `+ ${resumoDeLista(acao.itens, (p) => p.valor)}`,
        },
      ];
    case 'exclusao.ip':
      return [
        {
          rotulo: `IPs excluídos (${acao.escopo})`,
          antes: LIDO_AO_PROPOR,
          depois: `+ ${resumoDeLista(acao.ips, (i) => i)}`,
        },
      ];
    case 'programacao.anuncios': {
      const linhas: LinhaDeDiff[] = [];
      if (acao.substituir) linhas.push({ rotulo: 'janelas atuais', antes: LIDO_AO_PROPOR, depois: 'todas removidas' });
      if (acao.remover?.length) {
        linhas.push({ rotulo: 'janelas removidas', antes: LIDO_AO_PROPOR, depois: acao.remover.join(', ') });
      }
      for (const j of acao.janelas) {
        linhas.push({
          rotulo: `janela ${diaLegivel(j.dia)}`,
          antes: null,
          depois: `${j.inicio}–${j.fim} · ${pct(j.modificador)}`,
        });
      }
      return linhas;
    }
    case 'ajuste.dispositivo':
      return [
        {
          rotulo: `ajuste em ${DISPOSITIVOS.find((d) => d.dispositivo === acao.dispositivo)?.rotulo ?? acao.dispositivo}`,
          antes: LIDO_AO_PROPOR,
          depois: pct(acao.modificador),
        },
      ];
    case 'ajuste.horario':
      return [{ rotulo: `ajuste da janela ${acao.criterion_id}`, antes: LIDO_AO_PROPOR, depois: pct(acao.modificador) }];
    case 'recomendacao.aplicar':
      return [{ rotulo: 'recomendação', antes: 'pendente', depois: 'aplicada (sem ensaio e sem reverso)' }];
    case 'recomendacao.dispensar':
      return [{ rotulo: 'recomendação', antes: 'pendente', depois: 'dispensada' }];
    default:
      return [];
  }
}

// ── a fila ──────────────────────────────────────────────────────────────────

const ROTULO_DO_CAMPO: Record<string, string> = {
  verba_diaria_micros: 'verba diária',
  budget_id: 'orçamento',
  status: 'estado',
  estrategia: 'estratégia',
  tcpa: 'CPA desejado',
  tcpa_micros: 'CPA desejado',
  troas: 'ROAS desejado',
  teto_cpc: 'teto de CPC',
  teto_cpc_micros: 'teto de CPC',
  portfolio: 'portfólio',
  compartilhado: 'orçamento compartilhado',
  campanhas_no_orcamento: 'campanhas no orçamento',
  modificador: 'ajuste',
  dispositivo: 'dispositivo',
  criterion_id: 'critério',
  adicionar: 'adicionar',
  excluir: 'excluir',
  excluir_ips: 'excluir IPs',
  criar: 'criar janelas',
  remover: 'remover janelas',
  anexar: 'anexar a',
  lista: 'lista',
  itens: 'itens',
  aplicar: 'aplicar',
  dispensar: 'dispensar',
  escopo: 'escopo',
  origem_valor: 'origem do valor',
};

/** Campos que mudam o dinheiro: micros pela chave, ou alvos de lance em micros. */
function ehDinheiro(chave: string): boolean {
  return chave.endsWith('_micros') || chave === 'tcpa' || chave === 'teto_cpc';
}

export function valorLegivel(chave: string, valor: unknown, moeda: string | null): string | null {
  if (valor === undefined) return null;
  if (valor === null) return AUSENTE;
  if (typeof valor === 'number' && ehDinheiro(chave)) return dinheiro(valor, moeda);
  if (typeof valor === 'number' && chave === 'troas') return roas(valor);
  if (typeof valor === 'number' && chave === 'modificador') return pct(valor);
  if (typeof valor === 'boolean') return valor ? 'sim' : 'não';
  if (typeof valor === 'string') {
    if (chave === 'status') return STATUS[valor] ?? valor;
    if (chave === 'estrategia') return ROTULO_DA_ESTRATEGIA[valor] ?? valor;
    return valor;
  }
  if (chave === 'origem_valor' && valor && typeof valor === 'object') {
    const o = valor as Record<string, unknown>;
    return `${String(o.origem ?? AUSENTE)} (${String(o.evidencia ?? '')})`;
  }
  if (Array.isArray(valor)) {
    if (!valor.length) return 'nenhum';
    return resumoDeLista(valor, (i) => {
      if (i && typeof i === 'object') {
        const o = i as Record<string, unknown>;
        if (typeof o.texto === 'string') return `${o.texto}${o.correspondencia ? ` (${o.correspondencia})` : ''}`;
        if (typeof o.valor === 'string') return o.valor;
        if (typeof o.dia === 'string') return `${diaLegivel(o.dia)} ${o.inicio}–${o.fim}`;
        return JSON.stringify(o);
      }
      return String(i);
    });
  }
  return JSON.stringify(valor);
}

/** As chaves que o operador lê; o resto (ids técnicos lidos) fica de fora se igual. */
const SEMPRE_MOSTRAR = new Set(['verba_diaria_micros', 'status', 'estrategia', 'tcpa', 'troas', 'teto_cpc', 'modificador']);

export function linhasDoDiff(p: Pick<PropostaDoPainel, 'valor_atual' | 'valor_proposto' | 'moeda'>): LinhaDeDiff[] {
  const atual: ValorDoLedger = p.valor_atual ?? {};
  const proposto: ValorDoLedger = p.valor_proposto ?? {};
  const chaves = Object.keys(proposto);
  const saida: LinhaDeDiff[] = [];
  for (const k of chaves) {
    const antes = k in atual ? valorLegivel(k, atual[k], p.moeda) : null;
    const depois = valorLegivel(k, proposto[k], p.moeda);
    const igual = JSON.stringify(atual[k]) === JSON.stringify(proposto[k]);
    if (igual && !SEMPRE_MOSTRAR.has(k)) continue;
    saida.push({ rotulo: ROTULO_DO_CAMPO[k] ?? k, antes, depois });
  }
  return saida;
}

/**
 * O que vai como `diff_apresentado` — EXATAMENTE os objetos gravados que a
 * tela formatou. Retocar aqui (arredondar, traduzir) faria o servidor recusar
 * com `diff_divergente`, e com razão: seria aprovar outra coisa.
 */
export function diffApresentado(p: PropostaDoPainel): DiffApresentado {
  return { valor_atual: p.valor_atual, valor_proposto: p.valor_proposto, delta_pct: p.delta_pct };
}
