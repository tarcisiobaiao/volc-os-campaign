/**
 * `/trafego` — os quatro canais e o estado real de cada um.
 *
 * ## O que esta tela responde
 *
 *   "o que eu posso fazer com cada canal AGORA, e por que não posso o resto?"
 *
 * ## O que ela recusa a fazer
 *
 * **Não calcula autorização.** O veredito e o motivo chegam prontos do
 * servidor; aqui só se desenha. A tentação seria concreta e o erro seria
 * silencioso: `capacidades.google_mutate && manifesto.sabe_criar` pareceria
 * certo e ofereceria Display, que a janela do canário recusa.
 *
 * **Não mostra verde sem evidência.** Onde o servidor disse `INDETERMINADO`, a
 * tela escreve que não sabe — com a razão ao lado. Um cockpit que preenche
 * ignorância com zero ou com "ok" é pior que um cockpit vazio: ele produz
 * decisão.
 *
 * ## Por que os quatro canais aparecem sempre
 *
 * Inclusive os que não criam nada. A conta tem campanhas de Performance Max
 * gastando dinheiro, e esconder o canal faria a tela mentir por omissão. A
 * ausência declarada — com o motivo — é conteúdo, não lacuna.
 */
import React from 'react';
import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Eye,
  Image as ImageIcon,
  RefreshCw,
  Target,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  incoerenciasDoContrato,
  numeroOuTraco,
  portoesAbertos,
  type ContratoDeCanal,
  type RespostaDosCanais,
} from '@/lib/trafego/canais';
import { PortoesDoCanal } from '@/components/trafego/canais/PortoesDoCanal';
import { useCanais } from '@/components/trafego/canais/useCanais';

/** Um par rótulo/valor em que o valor pode legitimamente ser desconhecido. */
function Fato({
  rotulo,
  valor,
  ressalva,
}: {
  rotulo: string;
  valor: React.ReactNode;
  ressalva?: string | null;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {rotulo}
      </dt>
      <dd className="text-sm text-slate-800 dark:text-slate-200">{valor}</dd>
      {ressalva ? (
        <p className="mt-0.5 text-[11px] leading-snug text-slate-500 dark:text-slate-500">
          {ressalva}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A mensuração do canal.
 *
 * ⚠️ `lida: false` NÃO vira "não pronto". Ele vira "ninguém leu", com a razão —
 * e as duas pedem ações opostas: uma pede conserto, a outra pede uma leitura.
 */
function Mensuracao({ c }: { c: ContratoDeCanal }) {
  const m = c.mensuracao;
  if (!m.lida) {
    return (
      <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
        <p className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
          <Target className="h-3.5 w-3.5" aria-hidden />
          Mensuração — não lida
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-500">
          {m.fonte}
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
        <Target className="h-3.5 w-3.5" aria-hidden />
        Mensuração — {m.measurement_readiness}
      </p>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        <Fato rotulo="meta de conversão" valor={m.conversion_goal_status} />
        <Fato rotulo="sinal chegando" valor={m.conversion_signal_status} />
        <Fato
          rotulo="fontes comprovadas"
          valor={
            m.signal_sources.length > 0 ? m.signal_sources.join(', ') : 'nenhuma'
          }
          // ⚠️ Lista vazia é "nenhuma foi COMPROVADA nesta leitura", e isso é
          // diferente de "não existe nenhuma".
          ressalva={
            m.signal_sources.length === 0
              ? 'nenhuma foi comprovada nesta leitura — o que não quer dizer que não exista'
              : null
          }
        />
        <Fato
          rotulo="lance automático"
          valor={m.smart_bidding_eligible ? 'elegível' : 'não elegível'}
        />
      </dl>
    </div>
  );
}

/** O que sabemos sobre reler as campanhas deste canal depois de criadas. */
function Observabilidade({ c }: { c: ContratoDeCanal }) {
  const o = c.observabilidade;
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
        <Eye className="h-3.5 w-3.5" aria-hidden />
        Observabilidade — {o.estado}
      </p>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        <Fato
          rotulo="campanhas lidas de volta"
          // ⚠️ `null` vira `—`, nunca `0`. Um zero inventado no lugar de uma
          // leitura ausente é a mentira mais barata desta tela.
          valor={numeroOuTraco(
            o.campanhas_no_espelho,
            o.contagem_truncada ? '+' : '',
          )}
          ressalva={
            o.contagem_truncada
              ? 'a contagem bateu no teto da consulta: este número é um piso'
              : null
          }
        />
        <Fato rotulo="quem lê" valor={o.coletor ?? '—'} />
      </dl>
      {o.causa ? (
        <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-500">
          {o.causa}
        </p>
      ) : null}
    </div>
  );
}

/** Os recursos criativos que o canal monta — ou por que não sabemos. */
function Assets({ c }: { c: ContratoDeCanal }) {
  const a = c.assets;
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
        <ImageIcon className="h-3.5 w-3.5" aria-hidden />
        Assets — {a.estado}
      </p>
      {a.recursos.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1">
          {a.recursos.map((r) => (
            <li
              key={r}
              className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
            >
              {r}
            </li>
          ))}
        </ul>
      ) : null}
      {a.causa ? (
        <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-500">
          {a.causa}
        </p>
      ) : null}
      {a.fonte ? (
        <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-600">
          fonte: {a.fonte}
        </p>
      ) : null}
    </div>
  );
}

/** O canário pausado, por superfície — onde ele aparece e onde não aparece. */
function Canario({ c }: { c: ContratoDeCanal }) {
  const k = c.operacional.canario;
  if (!k) return null;
  const leitura = k.leitura_de_campo;
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
        Campanha canário {k.campaign_id} — {k.estado_declarado}
      </p>
      <p className="text-xs text-slate-500 dark:text-slate-500">
        {k.conta_label} ({k.conta})
      </p>

      {leitura ? (
        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
          <Fato
            rotulo="estratégia de lance"
            valor={leitura.estrategia_de_lance.valor}
            // ⚠️ Não é campo em branco: é uma ESCOLHA registrada. Mostrá-lo
            // vazio faria o operador procurar o que "faltou configurar".
            ressalva={leitura.estrategia_de_lance.por_que_importa}
          />
          <Fato
            rotulo="estado no Google"
            valor={leitura.primary_status}
            ressalva={`lido em ${leitura.observado_em}`}
          />
        </dl>
      ) : null}

      {/* ⚠️ RAZÕES, no plural. São simultâneas e dizem coisas diferentes: uma é
          consequência do desenho, a outra é o veredito que ainda não chegou. */}
      {leitura?.primary_status_reasons?.length ? (
        <ul className="mt-2 space-y-1">
          {leitura.primary_status_reasons.map((r) => (
            <li key={r.codigo} className="flex items-start gap-1.5 text-xs">
              {r.natureza === 'em_revisao' ? (
                // ⚠️ Nem verde nem vermelho. "Em revisão" é o terceiro estado —
                // o Google ainda não decidiu —, e pintá-lo de verde afirmaria
                // uma aprovação que não houve.
                <CircleHelp
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-600 dark:text-sky-400"
                  aria-hidden
                />
              ) : (
                <CircleCheck
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400"
                  aria-hidden
                />
              )}
              <span className="text-slate-600 dark:text-slate-400">
                <strong className="font-medium">{r.codigo}</strong> · {r.texto}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 text-xs font-medium text-slate-600 dark:text-slate-400">
        Onde ele aparece
      </p>
      <ul className="mt-1 space-y-1">
        {k.superficies.map((s) => (
          <li key={s.nome} className="flex items-start gap-1.5 text-xs">
            {/* TRI-ESTADO na tela também: visto, ausente, e NÃO LIDO. */}
            <span
              className={cn(
                'mt-0.5 shrink-0 font-mono text-[11px]',
                s.visivel === true && 'text-emerald-700 dark:text-emerald-400',
                s.visivel === false && 'text-amber-700 dark:text-amber-400',
                s.visivel === null && 'text-slate-500',
              )}
            >
              {s.visivel === true ? 'sim' : s.visivel === false ? 'não' : '?'}
            </span>
            <span className="text-slate-600 dark:text-slate-400">
              <strong className="font-medium">{s.descricao}</strong>
              {s.causa ? ` — ${s.causa}` : ''}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs italic text-slate-500 dark:text-slate-500">
        {k.resumo}
      </p>
    </div>
  );
}

/** A observabilidade de Performance Max, quando o canal a traz. */
function ObservabilidadeDePMax({ c }: { c: ContratoDeCanal }) {
  const o = c.operacional.observabilidade;
  const exigidos = c.operacional.assets_exigidos;
  if (!o && !exigidos) return null;
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
        Estrutura observada — {o?.estado_da_coleta ?? '—'}
      </p>
      {o?.causa ? (
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-500">
          {o.causa}
        </p>
      ) : null}
      {/* ⚠️ `quantidade: null` é "não coletei"; `0` seria "coletei e não há".
          O `numeroOuTraco` preserva a diferença. */}
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
        campanhas observadas: {numeroOuTraco(o?.quantidade ?? null)}
      </p>
      {exigidos?.papeis?.length ? (
        <>
          <p className="mt-3 text-xs font-medium text-slate-600 dark:text-slate-400">
            Assets que o canal exige
          </p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {exigidos.papeis
              .filter((p) => p.obrigatorio)
              .map((p) => (
                <li
                  key={p.papel}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  title={p.descricao}
                >
                  {p.papel} ({p.minimo}–{p.maximo})
                </li>
              ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function Canal({ c }: { c: ContratoDeCanal }) {
  const abertos = portoesAbertos(c);
  const incoerencias = incoerenciasDoContrato(c);
  return (
    <section className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {c.rotulo}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-500">
            {c.manifesto.hierarquia.join(' › ')}
          </p>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {abertos} de {c.portoes.length} portões liberados
        </p>
      </header>

      {/* ⚠️ Se o servidor mandar um contrato incoerente — liberado com motivo
          de recusa, ou fechado sem causa —, a tela DIZ isso em vez de escolher
          uma das duas metades. Escolher seria inventar um veredito. */}
      {incoerencias.length > 0 ? (
        <div className="mb-3 rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
          <p className="flex items-center gap-1.5 font-medium">
            <CircleAlert className="h-3.5 w-3.5" aria-hidden />
            A resposta do servidor está incoerente e não pode ser lida como
            veredito:
          </p>
          <ul className="ml-5 mt-1 list-disc">
            {incoerencias.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <PortoesDoCanal contrato={c} />

      <div className="mt-3 grid gap-2">
        <Assets c={c} />
        <Mensuracao c={c} />
        <Observabilidade c={c} />
        <Canario c={c} />
        <ObservabilidadeDePMax c={c} />
      </div>

      {c.manifesto.indisponibilidades.length > 0 ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-slate-600 dark:text-slate-400">
            O que este canal declaradamente não faz (
            {c.manifesto.indisponibilidades.length})
          </summary>
          <ul className="ml-5 mt-1 list-disc space-y-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
            {c.manifesto.indisponibilidades.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

export function PainelDeCanais() {
  const { data, isLoading, isError, error, refetch, isFetching } = useCanais();

  if (isLoading) {
    // ⚠️ "Lendo", e não quatro portões fechados. Um contrato de mentira
    // enquanto a resposta não chega faria a tela afirmar recusas que ninguém
    // avaliou.
    return (
      <p className="p-4 text-sm text-slate-500 dark:text-slate-500">
        Lendo o que cada canal pode fazer…
      </p>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <p className="flex items-center gap-1.5 text-sm font-medium text-slate-800 dark:text-slate-200">
          <CircleAlert className="h-4 w-4" aria-hidden />
          Não foi possível ler o estado dos canais.
        </p>
        {/* ⚠️ A falha NÃO vira "nenhum canal disponível". Não saber e não haver
            são coisas diferentes, e só uma delas é motivo para parar. */}
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-500">
          Isto é uma falha de leitura, e não uma afirmação sobre os canais: eles
          continuam existindo, e o que cada um pode fazer segue desconhecido
          nesta tela até a leitura voltar.
        </p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
          {(error as Error | undefined)?.message}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => void refetch()}
        >
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          Tentar de novo
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Canais
          </h2>
          <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-500">
            O que cada canal pode fazer agora, decidido no servidor. Quatro
            perguntas distintas por canal — montar, conferir, criar pausada e
            ativar —, com o motivo de cada recusa.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <RefreshCw
            className={cn('mr-1.5 h-3.5 w-3.5', isFetching && 'animate-spin')}
            aria-hidden
          />
          Reler
        </Button>
      </header>

      {/* ⚠️ A procedência da resposta, dita em voz alta. Sem ela, um
          `INDETERMINADO` na tela pareceria um defeito; com ela, ele é uma
          escolha explícita de não gastar quota da conta para pintar um cockpit. */}
      <p className="rounded-md bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-500 dark:bg-slate-900 dark:text-slate-500">
        {data.fontes.por_que_sem_leitura_viva}
        {data.fontes.espelho_lido
          ? ' O registro operacional foi consultado.'
          : ' O registro operacional não foi consultado nesta leitura — o que aparece como “não medido” não é o mesmo que “não há”.'}
      </p>

      {data.canais.map((c) => (
        <Canal key={c.canal} c={c} />
      ))}
    </div>
  );
}

export default PainelDeCanais;
