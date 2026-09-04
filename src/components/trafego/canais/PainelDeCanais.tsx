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
 *
 * ## Os três planos desta tela
 *
 * `design.md:143-152` — canvas, superfície de trabalho, poço. O cartão do canal
 * é a ÚNICA superfície elevada (`bg-card` + `shadow-card`); tudo que mora
 * dentro dele — assets, mensuração, observabilidade, canário — é poço
 * (`bg-muted/20`, borda de 1px, sem sombra). Antes eram todos caixas de borda
 * cinza sem plano nenhum, o que fazia o cartão do canal desaparecer no fundo da
 * página: `--background` (#F3F5F7) e `--card` (#FAFBFC) são quase a mesma
 * tinta, e um `bg-card` chapado sobre o canvas é invisível (`design.md:95`).
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
  ROTULO_DA_MENSURACAO,
  type ContratoDeCanal,
} from '@/lib/trafego/canais';
import { CartaoDoPlanoDeMensuracao } from '@/components/trafego/canais/PlanoDeMensuracao';
import { PortoesDoCanal } from '@/components/trafego/canais/PortoesDoCanal';
import { Fato } from '@/components/trafego/canais/Fato';
import { useCanais } from '@/components/trafego/canais/useCanais';

/** O poço padrão de um bloco interno do cartão do canal. Sem sombra, sempre. */
const POCO = 'rounded-md border border-border bg-muted/20 p-3';

/** O título de um poço: 14px, tinta de texto, glifo à esquerda. */
const TITULO_DO_POCO =
  'flex items-center gap-1.5 text-sm font-medium text-foreground';

/**
 * A mensuração do canal.
 *
 * ⚠️ `lida: false` NÃO vira "não pronto". Ele vira "ninguém leu", com a razão —
 * e as duas pedem ações opostas: uma pede conserto, a outra pede uma leitura.
 */
function Mensuracao({ c }: { c: ContratoDeCanal }) {
  const m = c.mensuracao;
  // ⚠️ Palavra E estado cru, como nos portões. Quem lê a tela e quem lê o
  // contrato na API precisam ver o mesmo nome — e o operador não deveria
  // precisar aprender o vocabulário do backend para entender a própria tela.
  const rotulo = (e: typeof m.measurement_readiness) =>
    `${ROTULO_DA_MENSURACAO[e]} (${e})`;
  if (!m.lida) {
    return (
      <div className={POCO}>
        <p className={TITULO_DO_POCO}>
          <Target className="h-3.5 w-3.5" aria-hidden />
          Mensuração — não lida
        </p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
          {m.fonte}
        </p>
      </div>
    );
  }
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <Target className="h-3.5 w-3.5" aria-hidden />
        Mensuração — {rotulo(m.measurement_readiness)}
      </p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
        <Fato
          rotulo="meta de conversão"
          valor={rotulo(m.conversion_goal_status)}
        />
        <Fato rotulo="sinal chegando" valor={rotulo(m.conversion_signal_status)} />
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
        {/* ⚠️ A procedência da LEITURA, no ramo lido. Ela só aparecia no ramo
            não-lido, e sumia justo quando havia o que explicar. `fonte` (como a
            leitura foi obtida) e `signal_sources` (por onde a conversão chega)
            são coisas diferentes, e a tela mostrava uma por vez. */}
        <Fato rotulo="procedência da leitura" valor={m.fonte ?? '—'} />
      </dl>
      {m.plano ? (
        <div className="mt-3 border-t border-border pt-3">
          <CartaoDoPlanoDeMensuracao plano={m.plano} />
        </div>
      ) : null}
    </div>
  );
}

/** O que sabemos sobre reler as campanhas deste canal depois de criadas. */
function Observabilidade({ c }: { c: ContratoDeCanal }) {
  const o = c.observabilidade;
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <Eye className="h-3.5 w-3.5" aria-hidden />
        Observabilidade — {o.estado}
      </p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
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
        <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
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
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <ImageIcon className="h-3.5 w-3.5" aria-hidden />
        Assets — {a.estado}
      </p>
      {a.recursos.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1">
          {a.recursos.map((r) => (
            <li
              key={r}
              className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground"
            >
              {r}
            </li>
          ))}
        </ul>
      ) : null}
      {a.causa ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
          {a.causa}
        </p>
      ) : null}
      {a.fonte ? (
        // Era ardósia clara sobre o poço — cinza sobre cinza, abaixo de 3:1 no
        // tema claro. `text-muted-foreground` é o token já calibrado.
        <p className="mt-1 text-xs text-muted-foreground">fonte: {a.fonte}</p>
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
    <div className={POCO}>
      <p className="text-sm font-medium text-foreground">
        Campanha canário {k.campaign_id} — {k.estado_declarado}
      </p>
      <p className="text-sm text-muted-foreground">
        {k.conta_label} ({k.conta})
      </p>

      {leitura ? (
        <dl className="mt-2 grid gap-3 sm:grid-cols-2">
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
            <li key={r.codigo} className="flex items-start gap-1.5 text-sm">
              {r.natureza === 'em_revisao' ? (
                // ⚠️ Nem verde nem vermelho. "Em revisão" é o terceiro estado —
                // o Google ainda não decidiu —, e pintá-lo de verde afirmaria
                // uma aprovação que não houve.
                //
                // `info` é o token do vocabulário fechado (`design.md:105`) que
                // preserva isso: informa sem julgar. `success` afirmaria a
                // aprovação, `warning` mandaria o operador agir sobre uma
                // decisão que não é dele.
                <CircleHelp
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info"
                  aria-hidden
                />
              ) : (
                <CircleCheck
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              )}
              <span className="leading-6 text-muted-foreground text-pretty">
                <strong className="font-medium text-foreground">
                  {r.codigo}
                </strong>{' '}
                · {r.texto}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 text-sm font-semibold text-foreground">
        Onde ele aparece
      </p>
      <ul className="mt-1 space-y-1">
        {k.superficies.map((s) => (
          <li key={s.nome} className="flex items-start gap-1.5 text-sm">
            {/* TRI-ESTADO na tela também: visto, ausente, e NÃO LIDO. A palavra
                — `sim` / `não` / `?` — é o portador primário; a tinta é o
                terceiro sinal, e agora vem do vocabulário fechado. */}
            <span
              className={cn(
                'mt-0.5 shrink-0 font-mono text-sm',
                s.visivel === true && 'text-success',
                s.visivel === false && 'text-warning',
                s.visivel === null && 'text-muted-foreground',
              )}
            >
              {s.visivel === true ? 'sim' : s.visivel === false ? 'não' : '?'}
            </span>
            <span className="leading-6 text-muted-foreground text-pretty">
              <strong className="font-medium text-foreground">
                {s.descricao}
              </strong>
              {s.causa ? ` — ${s.causa}` : ''}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm italic leading-6 text-muted-foreground text-pretty">
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
    <div className={POCO}>
      <p className="text-sm font-medium text-foreground">
        Estrutura observada — {o?.estado_da_coleta ?? '—'}
      </p>
      {o?.causa ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
          {o.causa}
        </p>
      ) : null}
      {/* ⚠️ `quantidade: null` é "não coletei"; `0` seria "coletei e não há".
          O `numeroOuTraco` preserva a diferença. */}
      <p className="mt-1 text-sm text-muted-foreground">
        campanhas observadas: {numeroOuTraco(o?.quantidade ?? null)}
      </p>
      {exigidos?.papeis?.length ? (
        <>
          <p className="mt-3 text-sm font-semibold text-foreground">
            Assets que o canal exige
          </p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {exigidos.papeis
              .filter((p) => p.obrigatorio)
              .map((p) => (
                <li
                  key={p.papel}
                  className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground"
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
    // A superfície de trabalho — a única elevada desta tela (`design.md:146`).
    <section className="rounded-lg border border-border bg-card p-4 shadow-card">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="font-display text-base font-semibold text-foreground">
            {c.rotulo}
          </h3>
          <p className="text-sm text-muted-foreground">
            {c.manifesto.hierarquia.join(' › ')}
          </p>
        </div>
        <p className="tabular text-sm text-muted-foreground">
          {abertos} de {c.portoes.length} portões liberados
        </p>
      </header>

      {/* ⚠️ Se o servidor mandar um contrato incoerente — liberado com motivo
          de recusa, ou fechado sem causa —, a tela DIZ isso em vez de escolher
          uma das duas metades. Escolher seria inventar um veredito. */}
      {incoerencias.length > 0 ? (
        // ⚠️ A tinta vermelha está no leito, na borda e no glifo — nunca na
        // frase. Escrever a explicação com a cor do estado é o jeito mais
        // eficiente de tornar ilegível exatamente o texto que decide
        // (`ChipDeEstado.tsx:25-28`).
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-foreground">
          <p className="flex items-center gap-1.5 font-medium">
            <CircleAlert
              className="h-3.5 w-3.5 shrink-0 text-destructive"
              aria-hidden
            />
            A resposta do servidor está incoerente e não pode ser lida como
            veredito:
          </p>
          <ul className="ml-5 mt-1 list-disc leading-6">
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
          <summary className="cursor-pointer text-sm text-muted-foreground">
            O que este canal declaradamente não faz (
            {c.manifesto.indisponibilidades.length})
          </summary>
          <ul className="ml-5 mt-1 list-disc space-y-1 text-sm leading-6 text-muted-foreground">
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
    return <p className="p-4 text-sm text-muted-foreground">Lendo o que cada canal pode fazer…</p>;
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 shadow-card">
        <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <CircleAlert
            className="h-4 w-4 shrink-0 text-destructive"
            aria-hidden
          />
          Não foi possível ler o estado dos canais.
        </p>
        {/* ⚠️ A falha NÃO vira "nenhum canal disponível". Não saber e não haver
            são coisas diferentes, e só uma delas é motivo para parar. */}
        <p className="mt-1 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
          Isto é uma falha de leitura, e não uma afirmação sobre os canais: eles
          continuam existindo, e o que cada um pode fazer segue desconhecido
          nesta tela até a leitura voltar.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
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
          <h2 className="font-display text-xl font-semibold text-foreground">
            Canais
          </h2>
          <p className="max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
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
      <p className="rounded-md border border-border bg-muted/40 p-3 text-sm leading-6 text-muted-foreground text-pretty">
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
