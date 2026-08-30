/**
 * Ações que podem gastar dinheiro não são cliques triviais.
 *
 * Sem endpoint seguro, o botão existe como proposta indisponível — com o
 * antes/depois que a revisão vai pedir — e não como atalho mudo. Nenhuma
 * chamada privilegiada sai daqui.
 *
 * ## O que este componente ganhou no Growth Engine
 *
 * A doutrina era boa e a forma era pequena demais: um antes e um depois soltos,
 * uma explicação fixa por tipo de ação, e um botão sempre desligado. As três
 * superfícies novas (caixa de propostas, diff, portão de aprovação) pedem a
 * MESMA ideia com mais matéria — várias linhas de diff, uma dependência REAL em
 * vez de uma frase enlatada, e um estado de aprovação com quem, quando e o quê.
 *
 * Nada disso virou componente separado. Um segundo vocabulário para "ação que
 * gasta dinheiro" é como as duas telas passam a discordar sobre o que é seguro.
 * As props novas são todas opcionais e a chamada antiga continua válida.
 */
import React from 'react';
import { Lock, ShieldCheck, ShieldX, Clock3, CircleDot } from 'lucide-react';

import { cn } from '@/lib/utils';
import { AUSENTE, dinheiro, horaExata } from '@/components/trafego/inventario/formato';
import type {
  Aprovacao,
  DependenciaDeAplicacao,
  DiffDaProposta,
  EstadoDeAprovacao,
} from '@/types/diagnostico';

export type AcaoQueGasta = 'orcamento' | 'lance' | 'status' | 'duplicacao' | 'estrutura';

export interface PropostaDeAcaoProps {
  acao: AcaoQueGasta;
  /** Forma curta: um valor de cada lado. Ignorada quando `diff` vem. */
  antes?: string | null;
  depois?: string | null;
  /** Forma completa: várias linhas, o que não muda, e o efeito no gasto. */
  diff?: DiffDaProposta | null;
  /**
   * Por que a aplicação não está disponível — a dependência REAL.
   *
   * `undefined` cai na explicação genérica desta tela. `null` significa que a
   * aplicação está liberada, e aí o portão de aprovação assume.
   */
  bloqueio?: DependenciaDeAplicacao | null;
  aprovacao?: Aprovacao;
  /** Só é chamado quando há aprovação liberada. A escrita NÃO acontece aqui. */
  aoSubmeter?: () => void;
  className?: string;
}

const ROTULO: Record<AcaoQueGasta, string> = {
  orcamento: 'Alterar orçamento',
  lance: 'Alterar lance',
  status: 'Alterar estado',
  duplicacao: 'Duplicar campanha',
  estrutura: 'Alterar estrutura',
};

const EXPLICA: Record<AcaoQueGasta, string> = {
  orcamento:
    'Mudar o orçamento gasta dinheiro na conta do cliente. Esta tela só abre uma revisão com o valor atual e o proposto; a aplicação passa por um endereço privilegiado que ainda não está ligado.',
  lance:
    'Mudar o lance altera o que a campanha paga no leilão. Sem revisão com antes e depois, o botão permanece indisponível.',
  status:
    'Ligar, pausar ou remover uma campanha muda o gasto. A confirmação não cabe num clique só.',
  duplicacao:
    'Duplicar cria campanha nova. Sem o endereço seguro, nada é enviado à conta de anúncio.',
  estrutura:
    'Mexer em grupo, keyword ou anúncio muda o que entra em leilão. A alteração passa por revisão antes de sair desta tela.',
};

/** O que destrava, em linguagem de operação. Nunca "erro de permissão". */
const DESTRAVA: Record<DependenciaDeAplicacao['destrava'], string> = {
  papel: 'depende de um papel que esta conta não tem',
  endpoint: 'depende de um endereço seguro que ainda não está ligado',
  trava: 'depende da trava de escrita, que é aberta fora desta tela',
  prova: 'depende de uma prova contra a conta que ainda não passou',
  manifesto: 'depende de o Hub declarar que opera este canal',
};

export const PropostaDeAcao: React.FC<PropostaDeAcaoProps> = ({
  acao,
  antes,
  depois,
  diff,
  bloqueio,
  aprovacao,
  aoSubmeter,
  className,
}) => {
  const rotulo = ROTULO[acao] ?? 'Alterar campanha';
  const explicacao = bloqueio ? bloqueio.dependencia : (EXPLICA[acao] ?? EXPLICA.status);
  const indisponivel = bloqueio !== null;

  return (
    <div className={cn('rounded-md border border-border px-3 py-3', className)}>
      <div className="flex items-start gap-2">
        <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium">{rotulo}</p>
          <p className="mt-1 max-w-[68ch] text-[12px] leading-relaxed text-muted-foreground">
            {explicacao}
            {bloqueio && (
              <span className="block mt-0.5">{DESTRAVA[bloqueio.destrava]}.</span>
            )}
          </p>

          {diff ? (
            <Diferenca diff={diff} />
          ) : (
            (antes || depois) && (
              <dl className="mt-2 grid gap-1 text-[12px]">
                {antes && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">antes</dt>
                    <dd className="tabular font-medium">{antes}</dd>
                  </div>
                )}
                {depois && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">depois</dt>
                    <dd className="tabular font-medium">{depois}</dd>
                  </div>
                )}
              </dl>
            )
          )}

          {aprovacao && <PortaoDeAprovacao aprovacao={aprovacao} />}

          {indisponivel ? (
            <button
              type="button"
              disabled
              className="mt-3 inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs text-muted-foreground md:min-h-9"
            >
              indisponível nesta tela
            </button>
          ) : (
            <button
              type="button"
              onClick={aoSubmeter}
              disabled={!aoSubmeter}
              className={cn(
                'mt-3 inline-flex min-h-11 items-center rounded-md border px-3 text-xs md:min-h-9',
                'transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
                aoSubmeter
                  ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'border-border text-muted-foreground',
              )}
            >
              {aoSubmeter ? 'submeter para aprovação' : 'aguardando quem aprova'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// ── o antes/depois ──────────────────────────────────────────────────────────

/**
 * O diff.
 *
 * ⚠️ `antes: null` aparece como `—`, nunca como `0`. Numa linha de orçamento a
 * diferença é decisiva: `0 → 50` lê-se como "vai passar a gastar", e
 * `— → 50` lê-se como "não sei quanto gasta hoje" — que é o que autoriza
 * perguntar em vez de aprovar.
 */
export const Diferenca: React.FC<{ diff: DiffDaProposta }> = ({ diff }) => (
  <div className="mt-2.5">
    <table className="w-full text-[12px]">
      <caption className="sr-only">o que muda se esta proposta for aplicada</caption>
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          <th scope="col" className="pb-1 font-normal">
            campo
          </th>
          <th scope="col" className="pb-1 pl-2 font-normal">
            antes
          </th>
          <th scope="col" className="pb-1 pl-2 font-normal">
            depois
          </th>
        </tr>
      </thead>
      <tbody>
        {diff.linhas.map((l) => (
          <tr key={l.rotulo} className="border-t border-border/60">
            <th scope="row" className="py-1 pr-2 text-left font-normal text-muted-foreground">
              {l.rotulo}
            </th>
            <td className="tabular py-1 pl-2 text-muted-foreground">{l.antes ?? AUSENTE}</td>
            <td className="tabular py-1 pl-2 font-medium">
              {l.depois ?? AUSENTE}
              {l.delta && (
                <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">
                  {l.delta}
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>

    <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
      {diff.gasto_diario
        ? `gasto diário: ${dinheiro(diff.gasto_diario.antes_micros, diff.gasto_diario.moeda)} → ${dinheiro(
            diff.gasto_diario.depois_micros,
            diff.gasto_diario.moeda,
          )}`
        : 'efeito no gasto diário não estimado — esta proposta não diz quanto passa a custar.'}
    </p>

    {diff.inalterado.length > 0 && (
      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
        não muda: {diff.inalterado.join(', ')}
      </p>
    )}
  </div>
);

// ── o portão ────────────────────────────────────────────────────────────────

const APROVACAO: Record<
  EstadoDeAprovacao,
  {
    palavra: string;
    descricao: string;
    glifo: React.ComponentType<{ className?: string }>;
    tinta: string;
  }
> = {
  nao_submetida: {
    palavra: 'não submetida',
    descricao: 'ninguém pediu autorização para esta mudança ainda',
    glifo: CircleDot,
    tinta: 'text-muted-foreground',
  },
  aguardando: {
    palavra: 'aguardando decisão',
    descricao: 'submetida e sem decisão humana até agora',
    glifo: Clock3,
    tinta: 'text-warning',
  },
  aprovada: {
    palavra: 'aprovada',
    descricao: 'uma pessoa autorizou exatamente o conteúdo carimbado abaixo',
    glifo: ShieldCheck,
    tinta: 'text-success',
  },
  recusada: {
    palavra: 'recusada',
    descricao: 'uma pessoa recusou esta mudança, com motivo declarado',
    glifo: ShieldX,
    tinta: 'text-destructive',
  },
  expirada: {
    palavra: 'aprovação expirada',
    descricao:
      'houve autorização e o prazo dela passou. A evidência envelheceu; vale de novo só com prova nova',
    glifo: Clock3,
    tinta: 'text-warning',
  },
  aplicada: {
    palavra: 'aplicada',
    descricao: 'a mudança já foi enviada à conta de anúncio, e há recibo dela',
    glifo: ShieldCheck,
    tinta: 'text-success',
  },
};

/**
 * O portão de aprovação: quem, quando, e O QUÊ.
 *
 * O "o quê" é a impressão. Um portão que grava só quem e quando autoriza uma
 * pessoa a assinar uma proposta e outra a mudá-la depois, com o carimbo
 * intacto. A impressão é a mesma que o recibo carrega, e é por ela que a tela
 * consegue afirmar que o que foi criado é o que foi aprovado.
 */
export const PortaoDeAprovacao: React.FC<{ aprovacao: Aprovacao }> = ({ aprovacao }) => {
  const visual = APROVACAO[aprovacao.estado] ?? {
    palavra: 'estado de aprovação não reconhecido',
    descricao: `o sistema informou "${aprovacao.estado}", que esta tela não conhece`,
    glifo: CircleDot,
    tinta: 'text-muted-foreground',
  };
  const Glifo = visual.glifo;
  const quando = horaExata(aprovacao.em);

  return (
    <div className="mt-3 border-t border-border pt-2.5">
      <p className="flex items-center gap-1.5 text-[12px] font-medium">
        <Glifo className={cn('h-3.5 w-3.5 shrink-0', visual.tinta)} aria-hidden />
        {visual.palavra}
      </p>
      <p className="mt-1 max-w-[68ch] text-[11px] leading-relaxed text-muted-foreground">
        {visual.descricao}.
      </p>
      <dl className="mt-1.5 grid gap-x-3 gap-y-0.5 text-[11px] sm:grid-cols-[auto_minmax(0,1fr)]">
        <dt className="text-muted-foreground">quem</dt>
        <dd className="font-medium">{aprovacao.por ?? AUSENTE}</dd>
        <dt className="text-muted-foreground">quando</dt>
        <dd className="tabular font-medium">{quando ?? AUSENTE}</dd>
        <dt className="text-muted-foreground">o que foi aprovado</dt>
        <dd className="tabular break-all font-medium">
          {aprovacao.impressao ? aprovacao.impressao.slice(0, 12) : AUSENTE}
          {aprovacao.impressao && (
            <span className="ml-1.5 font-normal text-muted-foreground">
              impressão do pedido
            </span>
          )}
        </dd>
        {aprovacao.motivo && (
          <>
            <dt className="text-muted-foreground">motivo</dt>
            <dd className="font-medium">{aprovacao.motivo}</dd>
          </>
        )}
      </dl>
      {aprovacao.impressao == null && aprovacao.estado === 'aprovada' && (
        <p className="mt-1.5 max-w-[68ch] text-[11px] leading-relaxed text-muted-foreground" role="note">
          Esta aprovação não carrega a impressão do pedido. Sem ela não dá para
          provar que o que sair é o que foi autorizado.
        </p>
      )}
    </div>
  );
};

export default PropostaDeAcao;
