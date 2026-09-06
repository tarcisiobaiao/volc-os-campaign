/**
 * `/trafego` → **Multicanal** — Display, Demand Gen e Performance Max lado a lado.
 *
 * ## A pergunta que esta tela responde
 *
 *   "o que cada canal pode fazer AGORA, com que conta, medindo o quê, gastando
 *    até quanto, com que peças, travado por quem — e qual é o ÚNICO próximo
 *    ato?"
 *
 * ## O que ela recusa a fazer
 *
 * **Não calcula autorização.** Os treze eixos chegam prontos de
 * `GET /api/trafego/canais`. A tentação seria concreta e o erro silencioso:
 * `capacidades.google_mutate && manifesto.sabe_criar` pareceria certo e
 * ofereceria Display, que a janela do canário recusa — e o operador descobriria
 * no clique, depois de montar o pedido inteiro.
 *
 * **Não oferece ativação.** Não existe botão de ativar nesta superfície, em
 * nenhum estado. Ativar não é ato deste fluxo, e um botão desabilitado ensinaria
 * que ele passa a existir quando alguma permissão abrir.
 *
 * **Não cria nada.** A CTA dominante desta tela abre a bancada do canal — que é
 * onde o pedido é montado. Nada aqui chama `/provar` nem `/subir`.
 *
 * **Não esconde canal bloqueado.** Os três aparecem sempre, com a razão. A conta
 * tem campanhas de Performance Max gastando dinheiro; esconder o canal faria a
 * tela mentir por omissão, e ausência declarada é conteúdo.
 *
 * ## Os três planos (`design.md` — Elevation)
 *
 * Canvas → cartão do canal (`bg-card` + `shadow-card`, a ÚNICA superfície
 * elevada) → poço interno (`bg-muted/20`, borda de 1px, sem sombra). Nada de
 * cartão dentro de cartão.
 *
 * ## Uma CTA dominante por região
 *
 * `design.md`: *"Each row, panel and step has one primary status or next
 * action"*. Cada cartão tem UM `AcaoDominante`, e a razão de ele estar travado
 * aparece INTEIRA, em todos os breakpoints — nunca `hidden sm:block`.
 *
 * ## Movimento
 *
 * Nenhum na carga: `/trafego` é superfície de alta frequência e `design.md`
 * proíbe stagger aqui. As únicas transições são as que os primitivos já trazem
 * (press e hover do botão), todas nomeadas e todas dentro de
 * `motion-reduce`/`@media (hover:hover)`.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Image as ImageIcon,
  Lock,
  RefreshCw,
  ShieldCheck,
  Target,
  Wallet,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  A_QUEM_PEDIR,
  ORDEM_DOS_PORTOES,
  PERGUNTA_DO_PORTAO,
  ROTULO_DA_MENSURACAO,
  ROTULO_DO_PORTAO,
  incoerenciasDoContrato,
  portao,
  portoesAbertos,
  type ContratoDeCanal,
  type EstadoDePortao,
  type PortaoDeCanal,
} from '@/lib/trafego/canais';
import { useCanais } from '@/components/trafego/canais/useCanais';
import { ChipDeEstado } from '@/components/trafego/bancada/ChipDeEstado';
import { AcaoDominante } from '@/components/trafego/bancada/AcaoDominante';
import { Eixo } from '@/components/trafego/multicanal/Eixo';

/** O poço padrão de um bloco interno. Sem sombra, sempre (`design.md`). */
const POCO = 'rounded-md border border-border bg-muted/20 p-3';
const TITULO_DO_POCO =
  'flex items-center gap-1.5 text-sm font-medium text-foreground';

/**
 * Os canais que esta tela apresenta.
 *
 * ⚠️ Search fica de FORA de propósito, e a ausência é a resposta: ele tem
 * cockpit próprio, completo, há meses. Repeti-lo aqui criaria uma segunda tela
 * para o mesmo canal, e a primeira divergiria da segunda no primeiro ajuste.
 * Esta superfície existe para os três que ainda não tinham nenhuma.
 */
export const CANAIS_DESTA_TELA = ['DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX'];

const TOM_DO_ESTADO: Record<EstadoDePortao, 'bom' | 'ruim' | 'info' | 'neutro'> = {
  PERMITIDO: 'bom',
  BLOQUEADO: 'ruim',
  // ⚠️ `info`, e não `ruim`: ignorância não é recusa, e as duas pedem atos
  // opostos — uma pede uma leitura, a outra pede uma permissão.
  INDETERMINADO: 'info',
  NAO_APLICAVEL: 'neutro',
};

const GLIFO_DO_ESTADO: Record<EstadoDePortao, React.ComponentType<{ className?: string }>> = {
  PERMITIDO: CircleCheck,
  BLOQUEADO: CircleAlert,
  INDETERMINADO: CircleHelp,
  NAO_APLICAVEL: CircleHelp,
};

function chip(p: PortaoDeCanal) {
  return (
    <ChipDeEstado
      key={p.nome}
      glifo={GLIFO_DO_ESTADO[p.estado]}
      palavra={`${ROTULO_DO_PORTAO[p.nome]} — ${p.estado}`}
      descricao={PERGUNTA_DO_PORTAO[p.nome]}
      tom={TOM_DO_ESTADO[p.estado]}
    />
  );
}

/**
 * As faltas do canal, na ordem da escada. Todas, e nunca um "+N".
 *
 * ⚠️ `apenas` recorta por portão, e o recorte existe para não DUPLICAR a mesma
 * frase na tela: o botão explica o que trava o BOTÃO (o primeiro degrau), e o
 * poço de bloqueadores explica a escada inteira. Sem o recorte, a razão de o
 * primeiro portão estar fechado aparecia duas vezes no mesmo cartão — e uma
 * frase repetida ensina o operador a parar de ler as duas.
 */
function faltasDoCanal(c: ContratoDeCanal, apenas?: string[]): string[] {
  const fora: string[] = [];
  for (const nome of ORDEM_DOS_PORTOES) {
    if (apenas && !apenas.includes(nome)) continue;
    const p = portao(c, nome);
    if (!p || p.aberto) continue;
    for (const b of p.bloqueadores) {
      fora.push(
        `${ROTULO_DO_PORTAO[nome]}: ${b.causa} — quem resolve: ${A_QUEM_PEDIR[b.origem]}`,
      );
    }
  }
  return fora;
}

// ═══════════════════════════════════════════════════════════════════════════
// OS TREZE EIXOS
// ═══════════════════════════════════════════════════════════════════════════

function Capacidade({ c }: { c: ContratoDeCanal }) {
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
        Capacidade — {portoesAbertos(c)} de {c.portoes.length} portões liberados
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {c.portoes.map((p) => (
          <li key={p.nome}>{chip(p)}</li>
        ))}
      </ul>
    </div>
  );
}

function ContaEDestino({ c }: { c: ContratoDeCanal }) {
  const conta = c.conta ?? {};
  const d = c.destino;
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>Conta e destino</p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
        <Eixo
          rotulo="conta"
          valor={conta.rotulo ? `${conta.rotulo} (${conta.customer_id_formatado ?? conta.customer_id})` : undefined}
          ausencia={conta.customer_id ? 'presente' : 'desconhecido'}
          ressalva={
            conta.customer_id
              ? null
              : 'nenhuma conta veio no contrato deste canal nesta leitura.'
          }
        />
        <Eixo
          rotulo="MCC"
          valor={conta.login_customer_id}
          ausencia={conta.login_customer_id ? 'presente' : 'desconhecido'}
        />
        <Eixo
          rotulo="onde a URL final é lida de volta"
          valor={d ? `${d.tabela} · ${d.campo}` : undefined}
          ausencia={d ? 'presente' : 'ausente'}
          ressalva={
            d
              ? d.url_exclusiva
                ? 'este canal exige URL exclusiva: exatamente uma, a página aprovada.'
                : null
              : 'este canal não declara onde guarda a URL final, então não há como provar duplicidade de destino nele.'
          }
        />
        <Eixo
          rotulo="travas de destino"
          valor={d && d.travas.length > 0 ? `${d.travas.length} declaradas` : undefined}
          ausencia={d && d.travas.length > 0 ? 'presente' : 'ausente'}
          ressalva={
            d && d.travas.length > 0 ? d.travas.join(' · ') : 'este canal não declara trava de destino própria.'
          }
        />
      </dl>
    </div>
  );
}

function Mensuracao({ c }: { c: ContratoDeCanal }) {
  const m = c.mensuracao;
  const rotulo = (e: keyof typeof ROTULO_DA_MENSURACAO | string) =>
    `${ROTULO_DA_MENSURACAO[e as keyof typeof ROTULO_DA_MENSURACAO]} (${e})`;
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <Target className="h-3.5 w-3.5" aria-hidden />
        Mensuração — {m.lida ? rotulo(m.measurement_readiness) : 'não lida'}
      </p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
        <Eixo
          rotulo="meta de conversão"
          valor={m.lida ? rotulo(m.conversion_goal_status) : undefined}
          ausencia={m.lida ? 'presente' : 'desconhecido'}
          ressalva={m.lida ? null : m.fonte}
        />
        <Eixo
          rotulo="sinal chegando"
          valor={m.lida ? rotulo(m.conversion_signal_status) : undefined}
          ausencia={m.lida ? 'presente' : 'desconhecido'}
        />
        <Eixo
          rotulo="lance automático"
          valor={m.lida ? (m.smart_bidding_eligible ? 'elegível' : 'não elegível') : undefined}
          ausencia={m.lida ? 'presente' : 'desconhecido'}
          ressalva={
            m.lida && !m.smart_bidding_eligible
              ? 'Smart Bidding sem medição provada é recusado localmente, antes de qualquer chamada ao Google.'
              : null
          }
        />
        <Eixo
          rotulo="fontes comprovadas"
          valor={m.signal_sources.length > 0 ? m.signal_sources.join(', ') : undefined}
          // ⚠️ Lista vazia numa leitura FEITA é `nulo` (medido e vazio); numa
          // leitura que não aconteceu é `desconhecido`. O `—` de antes dizia a
          // mesma coisa para os dois.
          ausencia={
            m.signal_sources.length > 0 ? 'presente' : m.lida ? 'nulo' : 'desconhecido'
          }
          ressalva={
            m.signal_sources.length === 0 && m.lida
              ? 'nenhuma foi comprovada nesta leitura — o que não quer dizer que não exista.'
              : null
          }
          fonte={m.fonte}
        />
      </dl>
    </div>
  );
}

function Economia({ c }: { c: ContratoDeCanal }) {
  const e = c.economia;
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <Wallet className="h-3.5 w-3.5" aria-hidden />
        Orçamento e lance
      </p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
        <Eixo
          rotulo="teto diário do canário"
          valor={e.teto_diario_brl ? `R$ ${e.teto_diario_brl}` : undefined}
          ausencia={e.teto_diario_brl ? 'presente' : 'desconhecido'}
          ressalva="freio desta casa, não limite do Google."
        />
        <Eixo
          rotulo="CPC máximo"
          valor={e.cpc_maximo_brl ? `R$ ${e.cpc_maximo_brl}` : undefined}
          // ⚠️ `ausente`, e não `nulo`: estes canais NÃO TÊM CPC. Display fixa a
          // rede no builder, Demand Gen escolhe superfícies e PMax não tem
          // controle de rede nenhum. Um `R$ 0,00` aqui recusaria qualquer lance.
          ausencia={e.cpc_maximo_brl ? 'presente' : 'ausente'}
          ressalva={
            e.cpc_maximo_brl
              ? null
              : 'este canal não tem CPC a declarar — ele entrega por impressão, e o teto de verba é o único freio.'
          }
        />
        <Eixo
          rotulo="estratégias de lance aceitas"
          valor={e.lances_permitidos.length > 0 ? e.lances_permitidos.join(', ') : undefined}
          ausencia={e.lances_permitidos.length > 0 ? 'presente' : 'desconhecido'}
          ressalva={e.causa}
        />
        <Eixo
          rotulo="piso diário da conta"
          valor={e.minimo_diario_medido ?? undefined}
          ausencia={e.minimo_diario_medido ? 'presente' : 'desconhecido'}
          ressalva="o piso depende da moeda e da conta, e só a API o conhece. Ele chega no erro de uma conferência real — este sistema não inventa um."
        />
      </dl>
    </div>
  );
}

function Assets({ c }: { c: ContratoDeCanal }) {
  const a = c.assets;
  const papeis = c.operacional?.assets_exigidos?.papeis ?? [];
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <ImageIcon className="h-3.5 w-3.5" aria-hidden />
        Assets e política criativa — {a.estado}
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
      {papeis.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-1">
          {papeis
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
      ) : null}
      <dl className="mt-3 grid gap-3">
        <Eixo
          rotulo="política criativa"
          valor="portão obrigatório por peça, antes da ponte e antes da rede"
          ressalva="cada peça precisa de recibo de política (CLEAR ou AUTHORIZED). Vídeo do YouTube por referência é recusado: um resource name não tem bytes, hash nem recibo."
          fonte={a.fonte}
        />
      </dl>
      {a.causa ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
          {a.causa}
        </p>
      ) : null}
    </div>
  );
}

function Automacoes({ c }: { c: ContratoDeCanal }) {
  const travadas = c.automacoes_travadas ?? [];
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>
        <Lock className="h-3.5 w-3.5" aria-hidden />
        Automações travadas — {travadas.length}
      </p>
      {travadas.length === 0 ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
          Este canal não declara <code>asset_automation_settings</code> nesta
          receita. Isso não afirma que ele não tem automação nenhuma: Display
          trava o equivalente por <code>control_spec</code>, no anúncio.
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {travadas.map((a) => (
            <li key={a.nome} className="flex items-start gap-1.5 text-sm">
              <Lock
                className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="leading-6 text-muted-foreground text-pretty">
                <strong className="font-medium text-foreground">{a.nome}</strong>{' '}
                — {a.estado}. {a.por_que}
              </span>
            </li>
          ))}
        </ul>
      )}
      {travadas.length > 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          campo: {travadas[0].campo}
        </p>
      ) : null}
    </div>
  );
}

function ProvaEReleitura({ c }: { c: ContratoDeCanal }) {
  const o = c.observabilidade;
  return (
    <div className={POCO}>
      <p className={TITULO_DO_POCO}>Conferência e releitura</p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
        <Eixo
          rotulo="cobertura de validate_only"
          valor={c.prova.estado}
          ressalva={c.prova.causa}
          fonte={c.prova.flag}
        />
        <Eixo
          rotulo="read-back"
          valor={o.estado}
          ressalva={o.causa}
          fonte={o.coletor}
        />
        <Eixo
          rotulo="campanhas lidas de volta"
          valor={
            o.campanhas_no_espelho === null
              ? undefined
              : `${o.campanhas_no_espelho}${o.contagem_truncada ? '+' : ''}`
          }
          // ⚠️ `null` aqui é NÃO LIDO — nunca `0`. Um zero inventado no lugar de
          // uma leitura ausente é a mentira mais barata desta tela.
          ausencia={o.campanhas_no_espelho === null ? 'desconhecido' : 'presente'}
          ressalva={
            o.contagem_truncada
              ? 'a contagem bateu no teto da consulta: este número é um piso, e leitura truncada não prova ausência.'
              : null
          }
        />
      </dl>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// O CARTÃO DO CANAL
// ═══════════════════════════════════════════════════════════════════════════

function CartaoDoCanal({ c }: { c: ContratoDeCanal }) {
  const navegar = useNavigate();
  const incoerencias = incoerenciasDoContrato(c);
  // A escada inteira, para o poço de bloqueadores.
  const faltas = faltasDoCanal(c);
  // Só o que trava a CTA, para o parágrafo adjacente ao botão.
  const faltasDaCta = faltasDoCanal(c, ['planejavel']);
  const planejavel = portao(c, 'planejavel');
  // ⚠️ A CTA desta tela é MONTAR, e não criar. Ela abre a bancada do canal, que
  // é onde o pedido nasce; nada aqui chama `/provar` nem `/subir`, e não existe
  // botão de ativar em nenhum estado desta superfície.
  const podeMontar = Boolean(planejavel?.aberto);

  return (
    <section
      aria-labelledby={`canal-${c.canal}`}
      className="rounded-lg border border-border bg-card p-4 shadow-card"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <h3
            id={`canal-${c.canal}`}
            className="font-display text-base font-semibold text-foreground"
          >
            {c.rotulo}
          </h3>
          <p className="text-sm text-muted-foreground">
            {c.manifesto.hierarquia.join(' › ')}
          </p>
        </div>
      </header>

      {incoerencias.length > 0 ? (
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

      <div className="grid gap-2">
        <Capacidade c={c} />
        <ContaEDestino c={c} />
        <Mensuracao c={c} />
        <Economia c={c} />
        <Assets c={c} />
        <Automacoes c={c} />
        <ProvaEReleitura c={c} />
      </div>

      {/* ── o bloqueador e o próximo ato, e UMA CTA ────────────────────────
          ⚠️ O próximo ato vem do servidor e é UM. Uma lista de próximos atos é
          o mesmo que nenhum: o operador escolhe o mais fácil em vez do
          primeiro. */}
      {/* ── o que está bloqueado, e por quem — SEMPRE visível ──────────────
          ⚠️ Ele NÃO depende do estado da CTA. A razão de um portão fechado
          aparecia só quando o botão estava travado; com o primeiro portão
          aberto, os três seguintes fechavam em silêncio e a tela parecia dizer
          que estava tudo bem. Bloqueado continua visível, e explicável. */}
      {faltas.length > 0 ? (
        <div className={cn(POCO, 'mt-2')}>
          <p className={TITULO_DO_POCO}>
            <CircleAlert className="h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
            Bloqueadores — {faltas.length}
          </p>
          <ul className="ml-5 mt-1 list-disc space-y-0.5 text-sm leading-relaxed text-muted-foreground text-pretty">
            {faltas.map((f, i) => (
              <li key={`${f}-${i}`}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-3 border-t border-border pt-3">
        <p className="text-sm font-medium text-foreground">Próximo ato</p>
        <p className="mt-1 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
          {c.proximo_ato ??
            'o servidor não declarou um próximo ato para este canal nesta leitura.'}
        </p>
        <div className="mt-3">
          <AcaoDominante
            pode={podeMontar}
            faltas={podeMontar ? [] : faltasDaCta}
            onClick={() => navegar(`/trafego?canal=${c.canal}`)}
          >
            Abrir a bancada de {c.rotulo}
          </AcaoDominante>
        </div>
        <p className="mt-2 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
          Esta tela não cria nem ativa nada. Abrir a bancada monta o pedido; a
          conferência e a criação continuam sendo atos separados, com portões
          próprios.
        </p>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// A TELA
// ═══════════════════════════════════════════════════════════════════════════

export function VisaoMulticanal() {
  const { data, isLoading, isError, error, refetch, isFetching } = useCanais();

  if (isLoading) {
    // ⚠️ "Lendo", e não três canais bloqueados. Um contrato de mentira enquanto
    // a resposta não chega faria a tela afirmar recusas que ninguém avaliou.
    return (
      <p className="p-4 text-sm text-muted-foreground">
        Lendo o que cada canal pode fazer…
      </p>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 shadow-card">
        <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <CircleAlert className="h-4 w-4 shrink-0 text-destructive" aria-hidden />
          Não foi possível ler o estado dos canais.
        </p>
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

  const canais = data.canais.filter((c) => CANAIS_DESTA_TELA.includes(c.canal));

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-display text-xl font-semibold text-foreground">
            Multicanal
          </h2>
          <p className="max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
            Display, Demand Gen e Performance Max, com o que cada um pode fazer
            agora — capacidade, conta, mensuração, destino, peças, política,
            orçamento, lance, automações travadas, conferência, releitura,
            bloqueador e o próximo ato. Tudo decidido no servidor.
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

      <p className="rounded-md border border-border bg-muted/40 p-3 text-sm leading-6 text-muted-foreground text-pretty">
        {data.fontes.por_que_sem_leitura_viva}
        {data.fontes.espelho_lido
          ? ' O registro operacional foi consultado.'
          : ' O registro operacional não foi consultado nesta leitura — o que aparece como “não lido” não é o mesmo que “não há”.'}
      </p>

      {canais.length === 0 ? (
        <p className="rounded-md border border-border bg-muted/20 p-3 text-sm leading-6 text-muted-foreground text-pretty">
          O servidor não devolveu nenhum dos três canais desta tela. Isto é uma
          resposta inesperada do contrato, e não uma afirmação de que os canais
          não existem.
        </p>
      ) : (
        // Coluna única no telefone, duas em telas largas. Nunca um grid de
        // cartões idênticos para inventário comparável — aqui cada cartão é uma
        // superfície de decisão, não uma linha de tabela.
        <div className="grid gap-4 xl:grid-cols-2">
          {canais.map((c) => (
            <CartaoDoCanal key={c.canal} c={c} />
          ))}
        </div>
      )}
    </div>
  );
}

export default VisaoMulticanal;
