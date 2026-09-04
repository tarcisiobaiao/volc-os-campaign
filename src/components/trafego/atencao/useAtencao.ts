/**
 * A leitura de atenção — uma projeção, duas fontes, e a disponibilidade de cada
 * uma dita separadamente.
 *
 * ## Por que as duas fontes, e não só a varredura de entrega
 *
 * A varredura só sabe falar de campanha ligada que não gastou. O resto do que
 * pede atenção — conta que não respondeu, campanha que não veio na leitura,
 * linha sem conta, estado que a tela não sabe nomear — só existe no inventário.
 * Um sino que enxergasse metade das condições anunciaria "tudo bem" com metade
 * do problema em cena, que é pior que não anunciar nada.
 *
 * ## ⚠️ A REGRA QUE ESTE ARQUIVO EXISTE PARA GARANTIR
 *
 * **Falha de consulta nunca vira contador de condição.** "Não consegui
 * perguntar" e "perguntei e há três problemas" levam a ações opostas: a
 * primeira manda tentar de novo, a segunda manda abrir o painel do Google. Por
 * isso `indisponivel`, `parcial` e `itens.length` são três respostas separadas,
 * e nenhuma delas é derivada das outras.
 *
 * ## Por que o contador pode ser um PISO, e por que isso é dito
 *
 * O inventário chega paginado, e esta leitura consome a primeira página. Com
 * mais páginas por carregar, a projeção descreve o que já está na mão — não o
 * total. Chamar isso de total transformaria "vi 3 de 40" em "há 3", que é a
 * mentira mais fácil de cometer numa lista incompleta.
 *
 * ## O custo da consulta
 *
 * O sino vive na moldura da aplicação, então esta leitura acontece em toda
 * página. Ela pergunta ao NOSSO registro, não à conta de anúncio: abrir uma
 * tela não custa cota do Google. O cache do React Query é compartilhado com o
 * inventário do Hub e com a fila de atenção, e o intervalo é de minutos — de
 * forma que estar montado em todo lugar não multiplica a consulta.
 */
import React from 'react';
import { useLocation } from 'react-router-dom';

import { lerEstadoDoHub } from '@/components/trafego/hub/adaptacao';
import { useInventario } from '@/hooks/useInventario';
import { useNotificacoes } from '@/hooks/useNotificacoes';
import type { OcorrenciaOperacional } from '@/components/trafego/inventario/erros';

import { projetarAtencao, type Projecao } from './projecao';

export interface LeituraDaAtencao extends Projecao {
  /** A central pertence a outra rede nesta tela; não é falha de conexão. */
  foraDeEscopo: boolean;
  /** Primeira consulta desta sessão: ainda não há nada na mão. */
  carregando: boolean;
  /** Há consulta em curso por cima do que já está na tela. */
  atualizando: boolean;
  /** NENHUMA das fontes respondeu alguma vez. Não dá para afirmar nada. */
  indisponivel: boolean;
  /** A tentativa mais recente falhou; o que está na tela é a última leitura boa. */
  ultimoEstadoConhecido: boolean;
  /**
   * A lista está incompleta e sabemos disso: uma das fontes não respondeu, ou o
   * inventário tem mais páginas por carregar. O contador é um PISO.
   */
  parcial: boolean;
  /** O que ainda não pôde ser consultado, em palavras de operação. */
  motivos: string[];
  /**
   * A falha com próximo passo e código copiável, quando a leitura do registro
   * produziu uma. `null` quando não houve falha — ou quando a fonte que falhou
   * não emite ocorrência própria.
   */
  ocorrencia: OcorrenciaOperacional | null;
  conferirDeNovo: () => void;
}

/**
 * O recorte que a fila pede ao servidor.
 *
 * ⚠️ `atencao: true` NÃO é otimização — é correção. Sem o filtro, a fila
 * projetava sobre a PÁGINA carregada do inventário, e a primeira página é
 * consumida pela conta com mais campanhas. Medido em 25/08/2026: das 84
 * campanhas reais, as 74 da PMUNDO+ ocupavam a página inteira, e as duas
 * únicas condições de campanha da casa — Maquininha e FGTS, ligadas e quase
 * sem entrega, na Crédito Up — ficavam INVISÍVEIS na aba que existe para
 * mostrá-las.
 *
 * Uma fila de atenção que depende de qual página o operador carregou não é uma
 * fila de atenção. O servidor resolve o recorte no banco, sobre o universo.
 */
const RECORTE_DA_ATENCAO = { atencao: true } as const;

export function useAtencao(habilitado = true): LeituraDaAtencao {
  const localizacao = useLocation();
  const metaPelaRota = localizacao.pathname.startsWith('/trafego/meta/');
  const googlePelaUrl = lerEstadoDoHub(new URLSearchParams(localizacao.search)).rede === 'google';
  const leituraHabilitada = habilitado && googlePelaUrl && !metaPelaRota;

  const notificacoes = useNotificacoes({ habilitado: leituraHabilitada });
  const inventario = useInventario(RECORTE_DA_ATENCAO, { habilitado: leituraHabilitada });

  // Uma query desabilitada ainda pode carregar cache Google. Sob Meta esse
  // cache não é uma leitura válida: ignorá-lo evita projetar a outra rede.
  const quadro = leituraHabilitada ? notificacoes.data ?? null : null;
  const registro = leituraHabilitada ? inventario.inventario ?? null : null;

  const projecao = React.useMemo(
    () => projetarAtencao({ alertas: quadro, inventario: registro }),
    [quadro, registro],
  );

  const nenhumaFonte = quadro == null && registro == null;
  const alguemFalhou = notificacoes.isError || inventario.falhou;

  const motivos: string[] = [];
  // ⚠️ A frase nomeia O QUE não foi consultado, sem citar rota, tabela nem
  // mensagem crua do servidor: o operador não tem o que fazer com isso, e o
  // detalhe técnico já vai para o log do backend.
  if (notificacoes.isError) motivos.push('a conferência de entrega das campanhas não respondeu');
  if (inventario.falhou) motivos.push('a conferência do registro de campanhas não respondeu');
  if (inventario.temMais) {
    motivos.push('parte do registro ainda não foi carregada nesta sessão');
  }

  if (!leituraHabilitada) {
    return {
      ...projecao,
      foraDeEscopo: true,
      carregando: false,
      atualizando: false,
      indisponivel: false,
      ultimoEstadoConhecido: false,
      parcial: false,
      motivos: ['a central de atenção ainda não está disponível para Meta Ads'],
      ocorrencia: null,
      conferirDeNovo: () => undefined,
    };
  }

  return {
    ...projecao,
    foraDeEscopo: false,
    carregando: (notificacoes.isLoading || inventario.carregando) && nenhumaFonte,
    atualizando: notificacoes.isFetching || inventario.atualizando,
    indisponivel: nenhumaFonte && alguemFalhou,
    ultimoEstadoConhecido: alguemFalhou && !nenhumaFonte,
    parcial: (alguemFalhou && !nenhumaFonte) || inventario.temMais,
    motivos,
    ocorrencia: inventario.ocorrencia ?? null,
    conferirDeNovo: () => {
      void notificacoes.refetch();
      inventario.recarregar();
    },
  };
}

/**
 * Só o contador, para quem precisa rotular uma aba sem montar a lista.
 *
 * `null` enquanto não se sabe — nunca `0`. Mostrar zero antes da resposta é
 * afirmar "não há nada", que é exatamente o que ainda não foi apurado.
 */
export function useContadorDeAtencao(habilitado = true): number | null {
  const atencao = useAtencao(habilitado);
  if (atencao.foraDeEscopo || atencao.carregando || atencao.indisponivel) return null;

  // ⚠️ O contador conta CAMPANHAS, não itens da fila.
  //
  // A fila mostra dois escopos: condições de campanha e condições de CONTA
  // (leitura antiga, conta que não respondeu). O contador contava os dois, e o
  // número passava a depender da idade do dado: com a leitura fresca dizia 2,
  // com ela velha dizia 5 — os mesmos 2 problemas mais 3 avisos de idade.
  //
  // Um número que muda sozinho com o relógio não é contagem de problema. E o
  // envelope da API conta campanhas (`totais.atencao`), então o rótulo passava
  // a discordar da fonte de verdade justamente quando o operador voltava
  // depois de um tempo — que é quando ele mais precisa confiar nela.
  //
  // A condição de conta continua VISÍVEL na fila e no cabeçalho, que a anuncia
  // em todas as abas. Ela não some; ela sai da contagem de campanhas.
  return atencao.itens.filter((i) => i.escopo !== 'conta').length;
}

// ── os cinco estados da central ─────────────────────────────────────────────

/** Qual dos cinco estados está em cena. Um só, sempre — nunca dois. */
export type EstadoDoSino =
  | 'fora_de_escopo'
  | 'sem_condicao'
  | 'com_condicao'
  | 'consultando'
  | 'indisponivel'
  | 'ultimo_conhecido'
  /**
   * Consultei, contei zero, e a lista que contei está incompleta.
   *
   * ⚠️ Este estado nasceu de um falso verde medido em 03/09/2026: com
   * `quantos === 0` e `parcial === true` — que acontece toda vez que o
   * inventário tem mais páginas do que esta sessão carregou — o sino caía em
   * `sem_condicao` e desenhava o check verde de "Nenhuma condição ativa". A
   * ressalva existia, num bloco cinza abaixo, e o operador lia o glifo.
   *
   * Zero numa lista incompleta não é "não há nada": é "não há nada NO QUE EU
   * VI". São afirmações diferentes, e só uma delas autoriza fechar a central e
   * ir cuidar de outra coisa.
   */
  | 'lista_incompleta';

export function estadoDoSino(leitura: {
  foraDeEscopo?: boolean;
  carregando: boolean;
  indisponivel: boolean;
  ultimoEstadoConhecido: boolean;
  quantos: number;
  parcial?: boolean;
}): EstadoDoSino {
  // A central Google não estar ativa numa tela Meta é escopo, não pane.
  if (leitura.foraDeEscopo) return 'fora_de_escopo';
  // A ordem é a regra. "Não consegui perguntar" vem antes de qualquer contagem,
  // porque uma contagem apurada sobre nada é uma afirmação sobre nada.
  if (leitura.indisponivel) return 'indisponivel';
  if (leitura.carregando) return 'consultando';
  if (leitura.ultimoEstadoConhecido) return 'ultimo_conhecido';
  if (leitura.quantos > 0) return 'com_condicao';
  // ⚠️ Zero E lista incompleta. `quantos > 0` vem ANTES desta linha de
  // propósito: uma condição achada é uma afirmação verdadeira mesmo quando a
  // busca não terminou, e escondê-la atrás da ressalva seria trocar um alarme
  // real por um aviso de método.
  return leitura.parcial ? 'lista_incompleta' : 'sem_condicao';
}
