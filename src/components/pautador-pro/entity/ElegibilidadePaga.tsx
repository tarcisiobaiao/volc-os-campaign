/**
 * A SEGUNDA resposta, ao lado da primeira.
 *
 * `ValidacaoPainel`, logo acima deste painel na mesma aba, responde "vale
 * produzir conteúdo sobre este tema?". Este responde "quais termos podem
 * entrar num leilão?" — e o ponto de existir os dois lado a lado é que eles
 * podem discordar sem contradição. Tema institucional apto a virar pauta com
 * todas as keywords retidas é o caso comum, não o caso estranho.
 *
 * ## O que este painel foi escrito para impedir
 *
 * Antes desta sprint a tela mostrava um subconjunto escolhido e a campanha
 * recebia a mineração inteira. Medido no funil BPC/LOAS: 5 selecionadas,
 * 8 exportadas — e as duas primeiras da própria seleção eram `meu inss login`
 * e `inss telefone 135`, navegacional e suporte entrando por volume.
 *
 * Por isso aqui o conjunto vem com a IMPRESSÃO junto: o que a pessoa aprova é
 * o hash do que ela está vendo. Se qualquer termo, match type ou sub-intenção
 * mudar, o hash muda, e a aprovação anterior deixa de valer.
 *
 * ## O que ele não afirma
 *
 * "Apto para mídia paga" diz que o CONJUNTO pode ser preparado. Conta,
 * destino pago, mensuração e autorização de gasto continuam sendo portões de
 * outras lanes, e o aviso do rodapé existe para que ninguém leia o verde
 * daqui como permissão de lançar.
 */
import React from 'react';
import type { ConjuntoPago, KeywordPaga, SituacaoPaga } from '@/types/pautadorValidacao';
import { ROTULO_DECISAO_PAGA, leSinal } from '@/types/pautadorValidacao';

const MOTIVO_HUMANO: Record<string, string> = {
  teto_economico_desconhecido: 'o teto econômico do dono não foi declarado',
  nenhuma_keyword_elegivel_selecionada: 'nenhum termo passou na elegibilidade',
  congruencia_nao_avaliada: 'ninguém avaliou termo → anúncio → página ainda',
  intencao_navegacional_ou_suporte: 'intenção de acesso/suporte, não de compra',
  navegacional_para_entidade_publica: 'aponta para o canal oficial de uma entidade pública',
  aponta_para_marca_de_terceiro: 'cita marca de terceiro',
  volume_absent: 'volume não foi medido',
  volume_unknown: 'volume veio como 0 sem confirmação de medição',
  demanda_zero_confirmada_na_medicao: 'demanda medida como zero',
  volume_medido_mas_cpc_sem_medicao: 'volume medido, CPC não',
  cpc_medido_acima_do_teto_declarado: 'CPC acima do teto declarado',
  fora_da_politica_de_selecao_por_volume: 'não coube no corte por volume',
  termo_nao_congruente_com_anuncio_e_pagina: 'incongruente com anúncio e página',
  volume_e_cpc_medidos_com_intencao_compativel: 'volume e CPC medidos, intenção compatível',
};

const humano = (m: string) => MOTIVO_HUMANO[m] || m.replace(/_/g, ' ');

const Linha: React.FC<{ k: KeywordPaga }> = ({ k }) => {
  const rotulo = ROTULO_DECISAO_PAGA[k.situacao as SituacaoPaga];
  return (
    <div className="flex items-start justify-between gap-2 p-2 text-xs">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate font-medium">{k.termo}</span>
          <span className="shrink-0 rounded border px-1 text-[10px] text-muted-foreground">
            {k.match_type}
          </span>
        </div>
        {/* O motivo viaja junto do termo. Um conjunto sem razão escrita é o
            que fazia a pessoa aprovar uma lista em vez de uma decisão. */}
        <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
          {k.subintencao ? `${k.subintencao} · ` : ''}
          {k.motivos.length ? humano(k.motivos[0]) : 'sem motivo registrado'}
        </p>
      </div>
      <div className="shrink-0 text-right tabular-nums text-muted-foreground">
        {/* `—` e não `0`: a ausência tem que continuar parecendo ausência. */}
        <div>vol {leSinal(k.volume)} · CPC {leSinal(k.cpc, 2)}</div>
        <div className={`text-[10px] ${rotulo?.tom || 'text-muted-foreground'}`}>
          {rotulo?.titulo || k.situacao}
        </div>
      </div>
    </div>
  );
};

const Grupo: React.FC<{ titulo: string; itens: KeywordPaga[] }> = ({ titulo, itens }) =>
  itens.length === 0 ? null : (
    <div>
      <p className="kicker mb-1">{titulo} ({itens.length})</p>
      <div className="max-h-48 divide-y overflow-y-auto rounded-lg border">
        {itens.map((k, i) => <Linha key={`${k.termo_normalizado}-${k.subintencao ?? ''}-${i}`} k={k} />)}
      </div>
    </div>
  );

export const ElegibilidadePaga: React.FC<{
  conjunto?: ConjuntoPago | null;
  /** `apto` do resumo do Validador. Vem de fora porque a resposta editorial
   *  NÃO é recalculada aqui — ela já tem dono em `app.validacao`. */
  valeProduzirConteudo?: boolean | null;
}> = ({ conjunto, valeProduzirConteudo }) => {
  if (!conjunto) {
    // Ausência de conjunto NÃO é "inapto": é lacuna, e se lê como lacuna.
    return (
      <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
        Elegibilidade paga <span className="font-medium">não avaliada</span> — minere a
        oportunidade para que o conjunto de keywords seja montado.
      </div>
    );
  }

  const elegiveisForaDoCorte = conjunto.excluded_keywords.filter((k) => k.decisao === 'INCLUDE');
  const emExperimento = conjunto.excluded_keywords.filter((k) => k.decisao === 'EXPERIMENT');
  const retidas = conjunto.excluded_keywords.filter((k) => k.decisao === 'HOLD' || k.decisao === 'REJECT');

  return (
    <div className="mt-3 space-y-3">
      {/* AS DUAS PERGUNTAS, LADO A LADO. Elas podem discordar. */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border p-2">
          <p className="kicker">Vale produzir conteúdo?</p>
          <p className="text-sm font-medium">
            {valeProduzirConteudo === true ? 'sim' : valeProduzirConteudo === false ? 'não' : 'não medido'}
          </p>
        </div>
        <div className="rounded-lg border p-2">
          <p className="kicker">Apto para mídia paga?</p>
          <p className="text-sm font-medium">
            {conjunto.ready_for_campaign_plan ? 'conjunto preparável' : 'não'}
          </p>
        </div>
      </div>

      {conjunto.blockers.length > 0 && (
        <ul className="space-y-0.5 text-[11px] text-warning">
          {conjunto.blockers.map((b) => <li key={b}>· {humano(b)}</li>)}
        </ul>
      )}

      <Grupo titulo="No conjunto" itens={conjunto.selected_keywords} />
      <Grupo titulo="Em experimento" itens={emExperimento} />
      <Grupo titulo="Revisão humana" itens={conjunto.human_review_keywords} />
      <Grupo titulo="Elegíveis fora do corte" itens={elegiveisForaDoCorte} />
      <Grupo titulo="Retidas do conjunto" itens={retidas} />

      {conjunto.alertas.length > 0 && (
        <ul className="space-y-0.5 text-[10px] text-muted-foreground">
          {conjunto.alertas.map((a) => <li key={a}>· {humano(a)}</li>)}
        </ul>
      )}

      {/* A IMPRESSÃO DO QUE ESTÁ NA TELA. É o que a aprovação congela: mudou
          termo, match type ou sub-intenção, o hash muda e a aprovação cai. */}
      <p className="font-mono text-[10px] text-muted-foreground">
        conjunto {conjunto.selected_set_sha256.slice(0, 12)}
        {conjunto.approved_set_sha256
          ? ` · aprovado por ${conjunto.aprovado_por ?? '—'}`
          : ' · não aprovado'}
      </p>

      {/* ⚠️ O AVISO NÃO É DECORAÇÃO. Foi escrito porque "apto para mídia paga"
          é lido como permissão, e não é. */}
      <p className="rounded-lg border border-warning/40 bg-warning/5 p-2 text-[11px] text-muted-foreground">
        Aprovar este conjunto de keywords <span className="font-medium">não autoriza campanha</span>.
        Conta, destino pago, mensuração e aprovação de gasto continuam sendo portões
        independentes — nenhum deles é avaliado aqui.
      </p>
    </div>
  );
};
