/**
 * O recibo que FICA na página depois que a Ignição fecha.
 *
 * ## O defeito que este componente existe para fechar
 *
 * Até 03/09/2026 o recibo era estado local do modal (`Lancamento.tsx:93`), e
 * `onFechar` fazia `setLancando(false)` — o que DESMONTA o componente e joga
 * tudo fora. O único dado que sobrevivia ao fechamento era o id da campanha, e
 * ele só servia para montar o veredito de política. Quem fechasse a escada por
 * reflexo perdia o `request_id`, o `recibo_id`, o `item_id`, a impressão do
 * plano e o motivo declarado — exatamente o conjunto de que se precisa quando o
 * desfecho é `indeterminado` e a única saída é reconciliar por identidade.
 *
 * Havia uma segunda superfície de recibo já escrita, mais completa que a do
 * modal (`CartaoDeRecibo.tsx` mostra "motivo declarado" e "impressão do
 * pedido"), e ela nunca teve consumidor de produção. Este componente é a ponte:
 * traduz o `ReciboDeLancamento` que `/subir` devolve para o `Recibo` que aquele
 * cartão já sabe ler, e ancora tudo numa região retornável (`#recibo`).
 *
 * ⚠️ NÃO OFERECE REENVIO. Os desfechos ambíguos (`sem_resposta`, `em_voo`)
 * levam a conferir e reconciliar, nunca a repetir o pedido: uma chamada pode
 * estar a caminho, e a segunda criaria a campanha duas vezes no mesmo leilão. É
 * a mesma doutrina de `proximoAtoSeguro`, e ela mora num lugar só.
 */
import React, { useState } from 'react';
import { CircleCheck, CircleOff, CircleHelp, Copy, Check, Pause } from 'lucide-react';

import { cn } from '@/lib/utils';
import { CartaoDeRecibo } from './CartaoDeRecibo';
import { lerRecibo } from './recibo';
import { idExternoDaCampanha, proximoAtoSeguro } from '@/lib/trafego/lancamento';
import type { ProximoAto } from '@/lib/trafego/lancamento';
import type { ReciboDeLancamento } from '@/types/trafego';

/**
 * O desfecho, em quatro estados que NÃO são intercambiáveis.
 *
 * `sem_resposta` e `em_voo` parecem o mesmo do lado de fora e não são: no
 * primeiro o navegador não recebeu resposta nenhuma; no segundo o ledger
 * registrou um item que ainda não fechou. Os dois proíbem reenvio, e é só por
 * isso que se parecem.
 */
export type DesfechoDoRecibo = 'sucesso' | 'erro' | 'sem_resposta' | 'em_voo';

const APRESENTACAO: Record<DesfechoDoRecibo, {
  palavra: string;
  explicacao: string;
  glifo: React.ComponentType<{ className?: string }>;
  hairline: string;
  tinta: string;
}> = {
  sucesso: {
    palavra: 'criada, pausada',
    explicacao: 'A conta confirmou a criação. A campanha existe e não está gastando.',
    glifo: CircleCheck,
    hairline: 'before:bg-success',
    tinta: 'text-success',
  },
  erro: {
    palavra: 'recusado',
    explicacao: 'A plataforma respondeu recusando. Nada foi criado, e o motivo está abaixo.',
    glifo: CircleOff,
    hairline: 'before:bg-destructive',
    tinta: 'text-destructive',
  },
  sem_resposta: {
    palavra: 'não sei se criou',
    explicacao:
      'A resposta se perdeu antes de chegar aqui. O pedido pode ter chegado à conta. '
      + 'Não reenvie: confira na conta ou reconcilie por identidade.',
    glifo: CircleHelp,
    hairline: 'before:bg-warning',
    tinta: 'text-warning',
  },
  em_voo: {
    palavra: 'em voo',
    explicacao:
      'O ledger registrou o pedido e ainda não o fechou. Não reenvie: '
      + 'reconciliar lê a conta e fecha este recibo.',
    glifo: CircleHelp,
    hairline: 'before:bg-warning',
    tinta: 'text-warning',
  },
};

/**
 * O desfecho LIDO DO LEDGER, nunca inferido de quanto a requisição demorou.
 *
 * Quando o ledger não registrou nada, o desfecho é `sem_resposta` — que é a
 * leitura fail-closed: "não sei" é mais barato que um "criada" otimista sobre
 * uma campanha que talvez não exista.
 */
export function desfechoDoRecibo(recibo: ReciboDeLancamento | null): DesfechoDoRecibo {
  const ledger = recibo?.ledger;
  if (!ledger?.registrado) return 'sem_resposta';
  if (ledger.desfecho === 'sucesso') return 'sucesso';
  if (ledger.desfecho === 'erro') return 'erro';
  if (ledger.desfecho === 'em_voo') return 'em_voo';
  return 'sem_resposta';
}

const FRASE_DO_PROXIMO_ATO: Record<ProximoAto, string> = {
  conferir_politica:
    'Confira o veredito de política: a campanha existe pausada, e os anúncios ainda passam por revisão do Google.',
  reconciliar_na_conta:
    'Reconciliar lê a conta e fecha este recibo. Ela não reenvia o pedido. '
    + 'Se a campanha existir, o recibo fecha como criada; se não existir, fecha como falha; '
    + 'se houver mais de uma, nada é carimbado e você decide.',
  corrigir_e_reenviar:
    'A recusa é da plataforma e está nomeada. Corrija o que ela apontou e envie de novo — '
    + 'este pedido não criou nada.',
};

/** Um identificador longo, inteiro e copiável. Truncar um id é perdê-lo. */
const IdCopiavel: React.FC<{ rotulo: string; valor: string | null }> = ({ rotulo, valor }) => {
  const [copiado, setCopiado] = useState(false);
  if (!valor) {
    return (
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">{rotulo}</dt>
        <dd className="text-sm text-muted-foreground">não declarado</dd>
      </div>
    );
  }
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="flex items-center gap-2">
        {/* ⚠️ `break-all` e não `truncate`: um id cortado no meio parece um id e
            não é. Quem for conferir na conta precisa do valor inteiro. */}
        <code className="tabular min-w-0 break-all text-sm text-foreground">{valor}</code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(valor).then(() => {
              setCopiado(true);
              window.setTimeout(() => setCopiado(false), 1600);
            });
          }}
          aria-label={`copiar ${rotulo}`}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-volc duration-[180ms] hover:bg-muted hover:text-foreground active:scale-[0.96]"
        >
          {copiado
            ? <Check className="h-3.5 w-3.5 text-success" aria-hidden />
            : <Copy className="h-3.5 w-3.5" aria-hidden />}
        </button>
        <span className="sr-only" role="status">{copiado ? 'copiado' : ''}</span>
      </dd>
    </div>
  );
};

/**
 * O desfecho DECLARADO pelo servidor quando não houve recibo.
 *
 * ⚠️ ESTE É O CASO PARA O QUAL O RECIBO PERSISTENTE FOI ESCRITO, e era
 * justamente o que não chegava até aqui.
 *
 * Quando `/subir` termina em 504 `indeterminado` ou 502 `recusado`, NÃO existe
 * `ReciboDeLancamento` nenhum — o servidor devolve `{estado, mensagem,
 * recibo_id, item_id, …}` e o modal guardava isso em estado próprio, que morria
 * no fechamento. Ou seja: a região que existe para preservar `recibo_id` e
 * `item_id` funcionava no caminho feliz e falhava exatamente onde eles importam,
 * que é quando ninguém sabe se a campanha existe.
 */
export interface DesfechoDeclarado {
  estado: 'indeterminado' | 'recusado';
  mensagem: string;
  recibo_id: string | null;
  item_id: string | null;
  erro_codigo?: string | null;
  request_id?: string | null;
  /** ⚠️ `VOLC-CANARY-<impressao[:12]>`, derivada do plano APROVADO.
   *
   *  Sem `campaign_id`, o validador de `ReconciliarEntrada`
   *  (`routers/trafego.py:4213-4219`) recusa o corpo: "reconciliar exige
   *  `campaign_id` OU `marca`". E o caso que mais precisa da rota e justamente
   *  o que nao tem id externo, porque a chamada nunca respondeu — logo a marca
   *  e a unica chave possivel ali. Ela e estavel entre tentativas. */
  marca?: string | null;
}

export interface ReciboDaBancadaProps {
  /** O recibo completo, quando `/subir` respondeu com um. */
  recibo?: ReciboDeLancamento | null;
  /** O desfecho declarado, quando não houve recibo. Ver `DesfechoDeclarado`. */
  declarado?: DesfechoDeclarado | null;
  /** A conta do pedido. Necessária para reconciliar quando não há recibo. */
  customerId?: string | null;
  canal: string;
  /** Se o usuário atual pode chamar `POST /reconciliar` — que exige admin. */
  podeReconciliar: boolean;
  /** Chamado só quando `podeReconciliar`. Ausente = o botão não aparece. */
  onReconciliar?: () => void;
  className?: string;
}

export const ReciboDaBancada: React.FC<ReciboDaBancadaProps> = ({
  recibo, declarado, customerId, canal, podeReconciliar, onReconciliar, className,
}) => {
  if (!recibo && !declarado) return null;

  // Um desfecho declarado sem recibo é SEMPRE ignorância ou recusa — nunca
  // sucesso. `recusado` fecha como erro respondido; `indeterminado` como
  // "não sei se criou".
  const desfecho: DesfechoDoRecibo = recibo
    ? desfechoDoRecibo(recibo)
    : declarado!.estado === 'recusado' ? 'erro' : 'sem_resposta';
  const ap = APRESENTACAO[desfecho];
  const Glifo = ap.glifo;
  // Sem recibo não há ledger para consultar, e a única saída segura é
  // reconciliar por identidade.
  const proximo: ProximoAto = recibo ? proximoAtoSeguro(recibo) : 'reconciliar_na_conta';
  const idExterno = recibo ? (idExternoDaCampanha(recibo) || null) : null;
  const conta = recibo?.customer_id || customerId || '';
  const reciboId = recibo?.ledger?.recibo_id ?? declarado?.recibo_id ?? null;
  const itemId = recibo?.ledger?.item_id ?? declarado?.item_id ?? null;
  const requestId = recibo?.request_id || declarado?.request_id || null;
  // O cartão completo só monta quando o recibo tem o mínimo para ser um recibo
  // (`carimbo` e `impressao`). Sem eles — e sem recibo nenhum — a região
  // continua existindo com o desfecho e os identificadores, que é justamente o
  // que salva um caso ruim.
  const detalhado = recibo ? lerRecibo(recibo as unknown) : null;

  return (
    <section
      id="recibo"
      aria-labelledby="recibo-titulo"
      className={cn(
        'relative scroll-mt-24 overflow-hidden rounded-lg border border-border bg-card p-5 shadow-card',
        'before:absolute before:inset-x-0 before:top-0 before:h-[2px]',
        ap.hairline,
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="recibo-titulo" className="flex items-center gap-2 text-base font-semibold text-foreground">
            <Glifo className={cn('h-4 w-4 shrink-0', ap.tinta)} aria-hidden />
            {ap.palavra}
          </h2>
          <p className="mt-2 max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
            {ap.explicacao}
          </p>
          {/* A frase do servidor, quando ele mandou uma. Ela nomeia o caso
              concreto; a explicação acima nomeia a CLASSE do desfecho. */}
          {declarado?.mensagem && (
            <p className="mt-2 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
              {declarado.mensagem}
            </p>
          )}
        </div>
        {/* PAUSED aparece LITERAL, e só no desfecho em que é um fato. Escrevê-lo
            num recibo indeterminado seria afirmar um estado que ninguém leu. */}
        {desfecho === 'sucesso' && (
          <span
            className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border border-verified/50 bg-verified/10 px-2.5 text-[0.8125rem] font-medium leading-none text-foreground"
            title="a campanha nasceu PAUSED e não veicula até alguém ativá-la"
          >
            <Pause className="h-3.5 w-3.5 shrink-0 text-verified" aria-hidden />
            PAUSED
            <span className="sr-only"> — não está gastando</span>
          </span>
        )}
      </div>

      <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">conta</dt>
          <dd className="tabular text-sm text-foreground">{conta || 'não declarada'}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">canal</dt>
          <dd className="text-sm text-foreground">{canal}</dd>
        </div>
        <IdCopiavel rotulo="id da campanha na conta" valor={idExterno} />
        <IdCopiavel rotulo="request id" valor={requestId} />
        <IdCopiavel rotulo="recibo em aberto" valor={reciboId} />
        <IdCopiavel rotulo="item do ledger" valor={itemId} />
        {declarado?.erro_codigo && (
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">código do erro</dt>
            <dd className="text-sm text-foreground">{declarado.erro_codigo}</dd>
          </div>
        )}
      </dl>

      <div className="mt-5 rounded-md border border-border/60 bg-muted/20 p-3">
        <p className="text-xs font-medium text-muted-foreground">próximo ato</p>
        <p className="mt-1.5 max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
          {FRASE_DO_PROXIMO_ATO[proximo]}
        </p>
        {proximo === 'reconciliar_na_conta' && (
          podeReconciliar && onReconciliar ? (
            <button
              type="button"
              onClick={onReconciliar}
              className="mt-3 inline-flex h-10 items-center justify-center rounded-md border border-[hsl(var(--input))] bg-transparent px-4 text-sm font-medium text-foreground transition-volc duration-[180ms] hover:bg-muted active:scale-[0.96]"
            >
              Reconciliar na conta
            </button>
          ) : (
            /* ⚠️ A ROTA EXIGE ADMIN e o resto do fluxo exige só usuário — logo o
               operador NÃO fecha o próprio recibo. Esconder o fato deixaria
               alguém esperando por um botão que nunca vai aparecer. */
            <p className="mt-3 text-sm leading-6 text-muted-foreground text-pretty">
              Reconciliar exige perfil de administrador. Guarde os identificadores acima
              e peça a reconciliação a quem tem esse perfil.
            </p>
          )
        )}
      </div>

      {/* ⚠️ NENHUM CAMINHO DE REENVIO É OFERECIDO AQUI, em nenhum desfecho.
          Corrigir e reenviar acontece voltando à Bancada e montando outro
          pedido — nunca por um botão dentro do recibo de um pedido que já
          partiu.

          ⚠️ O cartão completo fica RECOLHIDO, e não é economia de espaço: ele
          repete `request_id` e o id da campanha, que a grade acima já mostra —
          e lá eles são COPIÁVEIS, que é o que serve para reconciliar. Dois
          lugares com o mesmo identificador, um copiável e outro não, ensinam a
          procurar no lugar errado. Aberto, ele acrescenta o que só ele tem:
          motivo declarado, impressão do pedido, contagem por tipo e a
          conferência entre a impressão aprovada e a enviada. */}
      {detalhado && (
        <details className="mt-5 group">
          <summary className="inline-flex cursor-pointer items-center rounded-md px-2 py-1 text-sm font-medium text-foreground transition-volc duration-[180ms] hover:bg-muted">
            Ver o recibo completo
          </summary>
          <div className="mt-3">
            <CartaoDeRecibo recibo={detalhado} />
          </div>
        </details>
      )}
    </section>
  );
};

export default ReciboDaBancada;
