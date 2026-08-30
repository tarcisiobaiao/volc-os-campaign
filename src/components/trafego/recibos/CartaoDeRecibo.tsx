/**
 * O recibo de um lançamento — a prova do que saiu daqui.
 *
 * ## Por que o recibo é uma superfície de primeira classe
 *
 * Ele é a única coisa nesta operação que fala do PASSADO com autoridade. O
 * inventário diz o que existe agora; a escada diz por que não entrega hoje; o
 * recibo diz o que foi enviado, quando, por qual motivo declarado, e o que a
 * conta confirmou ter criado. Quando alguém pergunta "quem subiu isso e por
 * quê", esta é a resposta, e ela não depende de ninguém lembrar.
 *
 * ⚠️ Nada aqui é derivado de uma segunda leitura da conta. O recibo é o que o
 * gravador escreveu no instante do envio; conferir contra a conta é outra tela.
 */
import React from 'react';
import { CircleCheck, CircleOff, CircleHelp, TriangleAlert } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { AUSENTE } from '@/components/trafego/inventario/formato';
import type { Aprovacao, Recibo } from '@/types/diagnostico';

import {
  FRASE_DA_CONFERENCIA,
  conferirImpressao,
  contagemConfere,
  momentoDoCarimbo,
  porTipo,
} from './recibo';

const ESTADO: Record<
  string,
  { palavra: string; descricao: string; tom: Tom; glifo: React.ComponentType<{ className?: string }> }
> = {
  ACEITO: {
    palavra: 'aceito',
    descricao: 'a conta de anúncio confirmou a criação do grafo inteiro',
    tom: 'bom',
    glifo: CircleCheck,
  },
  RECUSADO: {
    palavra: 'recusado',
    descricao: 'a conta de anúncio recusou o pedido',
    tom: 'ruim',
    glifo: CircleOff,
  },
  PARCIAL: {
    palavra: 'parcial',
    descricao: 'parte do pedido foi criada e parte não',
    tom: 'atencao',
    glifo: TriangleAlert,
  },
};

export interface CartaoDeReciboProps {
  recibo: Recibo;
  /** A aprovação que autorizou este envio, quando existe. */
  aprovacao?: Aprovacao | null;
  className?: string;
}

export const CartaoDeRecibo: React.FC<CartaoDeReciboProps> = ({
  recibo,
  aprovacao,
  className,
}) => {
  const visual = ESTADO[recibo.estado] ?? {
    palavra: 'estado não reconhecido',
    descricao: `o gravador informou "${recibo.estado}", que esta versão da tela não conhece`,
    tom: 'atencao' as Tom,
    glifo: CircleHelp,
  };
  const momento = momentoDoCarimbo(recibo.carimbo);
  const tipos = porTipo(recibo);
  const confere = contagemConfere(recibo);
  const conferencia = conferirImpressao(aprovacao, recibo);

  return (
    <article className={cn('border-b border-border py-4', className)} aria-label="recibo de lançamento">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="min-w-0 font-display text-[13px] font-semibold">
          {recibo.nome_campanha}
        </h3>
        <Chip
          glifo={visual.glifo}
          palavra={visual.palavra}
          descricao={visual.descricao}
          tom={visual.tom}
        />
      </header>

      <p className="mt-1.5 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
        {recibo.explicacao || 'o gravador não deixou explicação neste recibo.'}
      </p>

      <dl className="mt-3 grid gap-x-4 gap-y-1 text-[12px] sm:grid-cols-[auto_minmax(0,1fr)]">
        <dt className="text-muted-foreground">quando</dt>
        <dd className="tabular font-medium">
          {momento ? momento.texto : recibo.carimbo}
          {momento?.semFuso && (
            <span className="ml-1.5 font-normal text-muted-foreground">
              (fuso não declarado no recibo)
            </span>
          )}
        </dd>

        <dt className="text-muted-foreground">motivo declarado</dt>
        <dd className="font-medium">{recibo.motivo || AUSENTE}</dd>

        <dt className="text-muted-foreground">conta</dt>
        <dd className="tabular font-medium">{recibo.customer_id || AUSENTE}</dd>

        <dt className="text-muted-foreground">impressão do pedido</dt>
        <dd className="tabular break-all font-medium">{recibo.impressao.slice(0, 16)}</dd>

        <dt className="text-muted-foreground">identificador do pedido</dt>
        <dd className="tabular break-all font-medium">
          {recibo.request_id || (
            <span className="font-normal text-muted-foreground">
              não devolvido pela conta de anúncio
            </span>
          )}
        </dd>
      </dl>

      {recibo.nada_foi_criado ? (
        <p className="mt-3 max-w-[70ch] text-[12px] leading-relaxed" role="status">
          <strong className="font-medium">Nada foi criado.</strong> Isto é uma
          afirmação do gravador, não uma lista que não carregou: a conta de
          anúncio não recebeu nenhuma operação deste pedido.
        </p>
      ) : (
        <div className="mt-3">
          <p className="text-[12px] text-muted-foreground">
            {recibo.n_operacoes === null ? (
              <>
                {recibo.criados.length} operações confirmadas pela conta
                <span className="ml-1 text-foreground">
                  — o recibo não declara quantas foram enviadas, então não dá para
                  conferir se falta alguma
                </span>
              </>
            ) : (
              <>
                {recibo.criados.length} de {recibo.n_operacoes} operações confirmadas pela conta
                {confere === 'difere' && (
                  <span className="ml-1 text-foreground">
                    — o recibo declara {recibo.n_operacoes} e lista {recibo.criados.length}
                  </span>
                )}
              </>
            )}
          </p>
          {tipos.length > 0 && (
            <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              {tipos.map((t) => (
                <li key={t.tipo} className="tabular">
                  {t.n} × {rotuloDoTipo(t.tipo)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {recibo.falha && (
        <div className="mt-3 max-w-[70ch]" role="alert">
          <p className="text-[12px] font-medium">O que a conta de anúncio recusou</p>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            {recibo.falha.mensagem ?? 'o gravador registrou uma falha sem mensagem.'}
          </p>
          <dl className="mt-1.5 grid gap-x-3 gap-y-0.5 text-[11px] sm:grid-cols-[auto_minmax(0,1fr)]">
            {recibo.falha.posicao != null && (
              <>
                <dt className="text-muted-foreground">parou na operação</dt>
                <dd className="tabular font-medium">{recibo.falha.posicao}</dd>
              </>
            )}
            {recibo.falha.campo && (
              <>
                <dt className="text-muted-foreground">campo</dt>
                <dd className="font-medium">{recibo.falha.campo}</dd>
              </>
            )}
            {recibo.falha.codigo && (
              <>
                <dt className="text-muted-foreground">código</dt>
                <dd className="tabular font-medium">{recibo.falha.codigo}</dd>
              </>
            )}
          </dl>
        </div>
      )}

      <p
        className={cn(
          'mt-3 max-w-[70ch] text-[11px] leading-relaxed',
          conferencia === 'difere' ? 'text-foreground' : 'text-muted-foreground',
        )}
        role={conferencia === 'difere' ? 'alert' : 'note'}
      >
        {FRASE_DA_CONFERENCIA[conferencia]}
      </p>
    </article>
  );
};

/** O tipo de operação, em português. Valor desconhecido aparece como veio. */
const TIPO: Record<string, string> = {
  campaign_budget_result: 'orçamento',
  campaign_result: 'campanha',
  campaign_criterion_result: 'critério de campanha',
  ad_group_result: 'grupo',
  ad_group_criterion_result: 'keyword',
  ad_group_ad_result: 'anúncio',
  ad_group_ad_label_result: 'rótulo de anúncio',
};

export function rotuloDoTipo(tipo: string): string {
  return TIPO[tipo] ?? tipo.replace(/_result$/, '').replace(/_/g, ' ');
}

export default CartaoDeRecibo;
