/**
 * A tela do lote: itens, estado individual, erro por item, retomada e cancelamento.
 *
 * ## O que esta tela recusa a fazer
 *
 * Somar `indeterminado` com `falhou`. O primeiro diz "a chamada saiu e não
 * sabemos se criou"; o segundo AFIRMA que não criou. Só o segundo autoriza
 * reenviar — e reenviar um indeterminado é como um timeout de rede vira uma
 * segunda campanha real na conta do cliente, disputando o mesmo leilão contra a
 * primeira. Os dois têm balde próprio, glifo próprio e frase própria, e o botão
 * de retomar fica fechado enquanto existir um indeterminado no lote.
 *
 * ## O vocabulário é o do backend
 *
 * Os estados vêm de `ESTADOS_DO_ITEM`, e a próxima ação de cada item vem
 * decidida do servidor. Esta tela mostra as duas; não recalcula nenhuma.
 *
 * ⚠️ Retomar e cancelar são gestos declarados. Nenhum dispara escrita a partir
 * desta tela.
 */
import React from 'react';
import {
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleHelp,
  CircleOff,
  CirclePause,
  CircleSlash,
  Loader2,
  Radar,
  RotateCcw,
  ShieldQuestion,
  Sprout,
  TriangleAlert,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { horaExata } from '@/components/trafego/inventario/formato';
import { CartaoDeRecibo } from '@/components/trafego/recibos/CartaoDeRecibo';
import type { AcaoDoItem, EstadoDoItemDoLote, ItemDoLote, Lote } from '@/types/diagnostico';

import { podeRetomar, resumoDoLote } from './lote';

type Glifo = React.ComponentType<{ className?: string }>;

const ITEM: Record<
  EstadoDoItemDoLote,
  { palavra: string; descricao: string; tom: Tom; glifo: Glifo }
> = {
  planejado: {
    palavra: 'planejada',
    descricao: 'está no plano do lote e ainda não começou',
    tom: 'neutro',
    glifo: CircleDashed,
  },
  validado_local: {
    palavra: 'validada aqui',
    descricao: 'passou nas regras da casa — nada saiu para a conta ainda',
    tom: 'info',
    glifo: CircleDot,
  },
  validado_remoto: {
    palavra: 'provada na conta',
    descricao: 'a conta aceitou o pedido sem criar nada',
    tom: 'info',
    glifo: CircleDot,
  },
  aprovado: {
    palavra: 'aprovada',
    descricao: 'uma pessoa autorizou este item e ele espera execução',
    tom: 'info',
    glifo: ShieldQuestion,
  },
  criando: {
    palavra: 'criando',
    descricao: 'o pedido foi enviado à conta e a resposta não voltou ainda',
    tom: 'info',
    glifo: Loader2,
  },
  indeterminado: {
    palavra: 'sem resposta da conta',
    descricao:
      'a chamada saiu e não sabemos se criou. Não é o mesmo que ter falhado: ' +
      'reenviar aqui pode criar uma segunda campanha real. A ação é verificar na conta',
    tom: 'ruim',
    glifo: Radar,
  },
  criada_pausada: {
    palavra: 'criada, pausada',
    descricao: 'existe na conta, não entra em leilão e não gasta',
    tom: 'bom',
    glifo: CirclePause,
  },
  verificada: {
    palavra: 'verificada',
    descricao: 'existe na conta e foi conferida — uma só, do jeito esperado',
    tom: 'bom',
    glifo: CircleCheck,
  },
  canario: {
    palavra: 'canário',
    descricao: 'ligada em escala reduzida, para medir antes de abrir',
    tom: 'info',
    glifo: Sprout,
  },
  ativa: {
    palavra: 'ativa',
    descricao: 'ligada e gastando na conta do cliente',
    tom: 'bom',
    glifo: CircleDot,
  },
  falhou: {
    palavra: 'falhou',
    descricao: 'foi tentada e a conta recusou — isto AFIRMA que nada foi criado',
    tom: 'ruim',
    glifo: CircleOff,
  },
  cancelada: {
    palavra: 'cancelada',
    descricao: 'uma pessoa cancelou este item, com motivo declarado',
    tom: 'neutro',
    glifo: CircleSlash,
  },
  revertida: {
    palavra: 'revertida',
    descricao: 'existiu na conta e foi desfeita',
    tom: 'neutro',
    glifo: RotateCcw,
  },
};

/** O que fazer com este item, na palavra de quem opera. */
const ACAO: Record<AcaoDoItem, string> = {
  verificar: 'verificar na conta antes de qualquer outra coisa',
  parar_duplicidade: 'decidir qual campanha fica — há mais de uma na conta',
  nada: 'nada a fazer',
  decidir_retomada: 'decidir se retoma este item',
  ativar_canario: 'ligar em escala reduzida',
  ativar: 'ligar',
  criar: 'criar na conta, pausada',
  preparar: 'preparar',
};

function itemLegivel(valor: string) {
  return (
    ITEM[valor as EstadoDoItemDoLote] ?? {
      palavra: 'estado não reconhecido',
      descricao: `o sistema informou "${valor}", que esta versão da tela não conhece`,
      tom: 'atencao' as Tom,
      glifo: CircleHelp,
    }
  );
}

function acaoLegivel(valor: string): string {
  return ACAO[valor as AcaoDoItem] ?? `${valor.replace(/_/g, ' ')} (ação não reconhecida)`;
}

export interface QuadroDoLoteProps {
  lote: Lote;
  /** Retomada declarada. Ausente = o caminho não está ligado, e a tela o diz. */
  aoRetomar?: () => void;
  /** Cancelamento declarado, com motivo. */
  aoCancelar?: (motivo: string) => void;
}

export const QuadroDoLote: React.FC<QuadroDoLoteProps> = ({ lote, aoRetomar, aoCancelar }) => {
  const resumo = resumoDoLote(lote);
  const retomada = podeRetomar(lote);

  return (
    <section aria-labelledby="lote-titulo" className="max-w-[78ch]">
      <p className="kicker">lote de criação</p>
      <h2
        id="lote-titulo"
        className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
      >
        {resumo.total} {resumo.total === 1 ? 'campanha neste lote' : 'campanhas neste lote'}
      </h2>
      <p className="mt-1.5 max-w-[70ch] text-[13px] leading-relaxed" role="status">
        {resumo.frase}.
      </p>

      {lote.aprovado_em == null && (
        <p
          className="mt-2 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground"
          role="note"
        >
          Ainda sem aprovação humana — nada deste lote será executado.
        </p>
      )}

      {lote.cancelado_em && (
        <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
          Lote cancelado por {lote.cancelado_por ?? 'alguém não identificado'} em{' '}
          {horaExata(lote.cancelado_em) ?? lote.cancelado_em}
          {lote.motivo_do_cancelamento ? `: ${lote.motivo_do_cancelamento}.` : '.'}
        </p>
      )}

      <ul className="mt-4 border-t border-border" role="list">
        {lote.itens.map((item) => (
          <LinhaDoItem key={item.id} item={item} />
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap gap-2">
        <Acao
          rotulo="retomar de onde parou"
          disponivel={retomada.pode && aoRetomar != null}
          aoAgir={aoRetomar}
          indisponivel={
            retomada.motivo ??
            'a retomada passa por um endereço privilegiado que ainda não está ligado nesta tela.'
          }
        />
        <Acao
          rotulo="cancelar o que falta"
          disponivel={resumo.emAndamento && aoCancelar != null}
          aoAgir={aoCancelar ? () => aoCancelar('cancelado pelo operador nesta tela') : undefined}
          indisponivel={
            !resumo.emAndamento
              ? 'não há item em andamento para cancelar.'
              : 'o cancelamento passa por um endereço privilegiado que ainda não está ligado nesta tela.'
          }
        />
      </div>
    </section>
  );
};

const LinhaDoItem: React.FC<{ item: ItemDoLote }> = ({ item }) => {
  const visual = itemLegivel(item.estado);
  const girando = item.estado === 'criando';
  const duplicidade = item.proxima_acao === 'parar_duplicidade';

  return (
    <li className="border-b border-border py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="min-w-0 font-display text-[13px] font-semibold">{item.rotulo}</span>
        <Chip
          glifo={visual.glifo}
          palavra={visual.palavra}
          descricao={visual.descricao}
          tom={visual.tom}
          className={cn(girando && 'motion-safe:[&>svg]:animate-spin')}
        />
        {item.recibo_em_voo && (
          <Chip
            glifo={Radar}
            palavra="chamada em voo"
            descricao="o pedido saiu e a resposta não voltou — verificar na conta, jamais reenviar"
            tom="ruim"
          />
        )}
      </div>

      <p className="mt-1 max-w-[68ch] text-[12px] leading-relaxed text-muted-foreground">
        {visual.descricao}.
      </p>

      <p className="mt-1 text-[12px] leading-relaxed">
        <span className="text-muted-foreground">próximo passo: </span>
        {acaoLegivel(item.proxima_acao)}
      </p>

      {duplicidade && (
        <p className="mt-1.5 max-w-[68ch] text-[12px] leading-relaxed" role="alert">
          <TriangleAlert className="mr-1 inline h-3.5 w-3.5 text-destructive" aria-hidden />
          {item.encontradas_na_conta ?? 'várias'} campanhas foram encontradas na conta para este
          item. Qual pausar depende de qual já gastou, qual tem histórico e qual está vinculada a
          um funil — não há escolha automática correta, e o lote fica travado até alguém decidir.
        </p>
      )}

      {item.falha && (
        <div className="mt-2 max-w-[68ch]" role="alert">
          <p className="text-[12px] leading-relaxed">{item.falha.mensagem}</p>
          {item.falha.codigo && (
            <p className="tabular mt-0.5 text-[11px] text-muted-foreground">
              código {item.falha.codigo}
            </p>
          )}
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            A falha é deste item. Os outros itens deste lote continuam com o estado
            que cada um alcançou.
          </p>
        </div>
      )}

      {item.recibo && <CartaoDeRecibo recibo={item.recibo} className="mt-2 border-b-0 pb-0" />}
    </li>
  );
};

/**
 * Um botão que, quando não pode agir, EXPLICA a dependência real.
 *
 * Nunca um botão cinza mudo: o operador que clica e não vê nada acontecer não
 * sabe se o sistema falhou ou se ele não podia. A frase fica ao lado, legível
 * sem hover e sem cor, e ligada ao botão por `aria-describedby`.
 */
const Acao: React.FC<{
  rotulo: string;
  disponivel: boolean;
  aoAgir?: () => void;
  indisponivel: string;
}> = ({ rotulo, disponivel, aoAgir, indisponivel }) => {
  const id = `indisponivel-${rotulo.replace(/\s+/g, '-')}`;
  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={aoAgir}
        disabled={!disponivel}
        aria-describedby={disponivel ? undefined : id}
        className={cn(
          'inline-flex min-h-11 items-center rounded-md border px-3 text-xs md:min-h-9',
          'transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
          disponivel ? 'border-border hover:bg-muted/60' : 'border-border text-muted-foreground',
        )}
      >
        {rotulo}
      </button>
      {!disponivel && (
        <p id={id} className="mt-1 max-w-[46ch] text-[11px] leading-relaxed text-muted-foreground">
          {indisponivel}
        </p>
      )}
    </div>
  );
};

export default QuadroDoLote;
