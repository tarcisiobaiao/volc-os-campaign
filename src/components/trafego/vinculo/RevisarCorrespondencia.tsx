/**
 * "De quem é esta campanha?" — a pergunta que ninguém podia responder.
 *
 * ## O buraco que esta superfície fecha
 *
 * `POST /api/trafego/vinculos` existe desde 26/08/2026, `pautadorApi` já tinha
 * `confirmarVinculo`, e `trafego_vinculo` continua com **zero linhas**. Não
 * porque a gravação falhe — porque nenhuma tela chegava até ela. O inventário
 * mostrava o selo "sem vínculo" e não oferecia caminho nenhum para deixar de
 * estar assim.
 *
 * ## Por que "sem vínculo" não é um erro
 *
 * ⚠️ É o estado NORMAL de toda campanha que a varredura descobre antes de
 * alguém responder. Medido em 27/08/2026: as duas campanhas ENABLED da Crédito
 * Up nasceram `procedencia: descoberta` e nunca foram perguntadas a ninguém.
 *
 * Desenhar isso como falha — vermelho, ícone de alerta, "erro de vínculo" —
 * ensina o operador que o sistema está quebrado quando ele está apenas
 * esperando uma decisão que só um humano pode tomar. A palavra é
 * **associação pendente**, e o tom é o de uma pergunta.
 *
 * ## Sugerir não é vincular
 *
 * A correspondência mais limpa possível continua sendo pergunta. Um vínculo
 * errado contamina a atribuição de receita de forma permanente e silenciosa
 * (ADR-09), e a linha gravada é imutável: só dá para desfazer, nunca corrigir.
 * Por isso não existe "confirmar todas", não existe pré-seleção quando há mais
 * de uma candidata, e a força do sinal aparece do lado de cada opção.
 *
 * ## Zero Google
 *
 * Confirmar grava no NOSSO banco. Não cria campanha, não altera lance, não
 * gasta um centavo — e é por isso que o portão é `exigir_usuario` e não
 * `exigir_admin`.
 */
import React from 'react';
import {
  CircleCheck,
  CircleHelp,
  Clock,
  Link2,
  Link2Off,
  Loader2,
  PenLine,
  ShieldQuestion,
  TriangleAlert,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { AUSENTE } from '@/components/trafego/inventario/formato';
import {
  useConfirmarVinculo,
  useCorrespondencias,
  useDesfazerVinculo,
} from '@/hooks/useCorrespondencias';
import type {
  Correspondencia,
  EstadoDeCorrespondencia,
  SinalDeReconciliacao,
} from '@/types/trafego';

// ── vocabulário ─────────────────────────────────────────────────────────────
//
// ⚠️ Nenhuma destas frases usa palavra de backend. `volc_campaign_id`,
// `opportunity_id` e `funnel_run_id` aparecem como número identificado por
// rótulo humano ("funil 74"), nunca como nome de coluna. O operador não tem por
// que aprender o schema para decidir de quem é uma campanha.

const PALAVRA_DO_ESTADO: Record<
  EstadoDeCorrespondencia,
  { palavra: string; descricao: string; tom: Tom; glifo: React.ComponentType<{ className?: string }> }
> = {
  associada: {
    palavra: 'associada',
    descricao: 'uma pessoa já confirmou a que funil esta campanha pertence',
    tom: 'bom',
    glifo: Link2,
  },
  correspondencia_unica: {
    palavra: 'correspondência encontrada',
    descricao: 'um funil casa com esta campanha, e a confirmação é sua',
    tom: 'atencao',
    glifo: ShieldQuestion,
  },
  mais_de_uma_correspondencia: {
    palavra: 'mais de uma correspondência',
    descricao: 'mais de um funil casa — escolher em silêncio vincularia ao errado',
    tom: 'atencao',
    glifo: TriangleAlert,
  },
  sem_correspondencia: {
    palavra: 'não associada ao VOLC',
    descricao:
      'nenhum funil interno casa com esta campanha. Não é defeito: é o estado de toda campanha encontrada na conta antes de alguém respondê-la',
    tom: 'neutro',
    glifo: Link2Off,
  },
  nao_apurada: {
    palavra: 'não foi possível apurar',
    descricao:
      'faltou o que comparar — e isso é diferente de ter comparado e não encontrado nada',
    tom: 'atencao',
    glifo: CircleHelp,
  },
};

/**
 * A força do sinal, dita ao operador — sem a palavra `historica` crua.
 *
 * ⚠️ `historica` é vocabulário do motor e significa uma coisa muito específica:
 * observado na conta, mas SEM carimbo próprio. A tela precisa dizer isso, e não
 * traduzir para "fraco" — o sinal não é fraco, ele é de idade desconhecida, que
 * é outra ressalva e leva a outra decisão.
 */
// ⚠️ O glifo carrega o EIXO da ressalva, e o eixo aqui é o TEMPO: quando isto
// foi observado. Uma seta genérica ao lado de "observado, sem data" desenha
// direção onde a pergunta é idade — e o operador lê o selo antes da frase.
const FORCA: Record<
  SinalDeReconciliacao['forca'],
  { palavra: string; explica: string; glifo: React.ComponentType<{ className?: string }>; tom: Tom }
> = {
  forte: {
    palavra: 'observado agora',
    explica: 'lido da conta nesta varredura, com carimbo próprio',
    glifo: CircleCheck,
    // ⚠️ `verificado`, e não `bom`. Um sinal observado agora é forte — e não é
    // um estado saudável. Pintá-lo de verde diria ao operador que está tudo
    // certo com a campanha, quando o que se afirma é só "eu vi isto na conta".
    tom: 'verificado',
  },
  medio: {
    palavra: 'declarado por nós',
    explica:
      'foi o VOLC que escreveu isto ao lançar — pode ter mudado no painel do Google desde então',
    glifo: PenLine,
    tom: 'neutro',
  },
  historica: {
    palavra: 'observado, sem data',
    explica:
      'veio da conta, mas não se sabe de quando: o registro guarda a URL e não guarda quando ela foi lida. Sustenta a correspondência e não a fecha sozinha',
    glifo: Clock,
    tom: 'neutro',
  },
};

const REGRA: Record<SinalDeReconciliacao['regra'], string> = {
  url_final_da_conta: 'o anúncio na conta aponta para uma página deste funil',
  url_no_nome_declarado: 'o nome da campanha carrega o endereço deste funil',
  linhagem_declarada: 'as duas pontas declaram a mesma linhagem',
  lancamento_declarado: 'esta campanha foi lançada por aqui, a partir deste funil',
};

/**
 * A chave de um funil na tela — espelha `reconciliacao.chave_do_funil`.
 *
 * ⚠️ NÃO é só a oportunidade. Duas versões do mesmo funil são dois candidatos
 * distintos, com destinos distintos, e distinguir os dois é o que separa
 * confirmar o vínculo certo de confirmar o parecido.
 */
export function chaveDaCorrespondencia(c: Correspondencia): string {
  return `${c.opportunity_id}:${c.run_id ?? 'sem-versao'}`;
}

function regraLegivel(regra: string): string {
  return (
    REGRA[regra as SinalDeReconciliacao['regra']] ??
    'uma regra que esta versão da tela ainda não sabe explicar'
  );
}

// ── a superfície ────────────────────────────────────────────────────────────

export interface RevisarCorrespondenciaProps {
  volcCampaignId: string;
  /** O nome da campanha do lado do Google, para o operador se situar. */
  nomeDaCampanha?: string | null;
  contaExterna?: string | null;
  idExterno?: string | null;
  estadoExterno?: string | null;
  className?: string;
}

export const RevisarCorrespondencia: React.FC<RevisarCorrespondenciaProps> = ({
  volcCampaignId,
  nomeDaCampanha,
  contaExterna,
  idExterno,
  estadoExterno,
  className,
}) => {
  const leitura = useCorrespondencias(volcCampaignId);
  const confirmar = useConfirmarVinculo();
  const desfazer = useDesfazerVinculo();

  // ⚠️ Nenhuma pré-seleção. Com uma candidata só, marcar por comodidade
  // transformaria "confirmar" em "clicar em OK" — e o clique de OK é o que o
  // ADR-09 existe para não aceitar como decisão sobre atribuição de receita.
  //
  // ⚠️ E a escolha é a CHAVE INTEIRA do funil, não a oportunidade.
  // `reconciliacao.chave_do_funil` já documenta a armadilha: uma oportunidade
  // pode ter mais de um run — é o caso normal quando o funil é reprocessado —,
  // e os dois aparecem como candidatos separados, com URLs diferentes.
  // Guardando só `opportunity_id`, clicar no segundo marcava os DOIS e gravava
  // o primeiro: o vínculo ia para a versão errada do funil, em silêncio, numa
  // decisão que contamina atribuição de receita e não pode ser corrigida.
  const [escolhida, setEscolhida] = React.useState<string | null>(null);
  const [recusada, setRecusada] = React.useState(false);

  if (leitura.carregando) {
    return (
      <section className={cn('max-w-[80ch]', className)} aria-label="revisão de correspondência">
        <p className="kicker">a que funil esta campanha pertence</p>
        <div className="mt-3 space-y-2" role="status" aria-live="polite">
          <span className="sr-only">procurando funis que casem com esta campanha</span>
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-sm bg-muted motion-reduce:animate-none"
            />
          ))}
        </div>
      </section>
    );
  }

  // ⚠️ 404 é endereço que NÃO EXISTE, e convidar a insistir nele é mandar o
  // operador tentar de novo para sempre. Distinto de falha transitória.
  if (leitura.naoEncontrada) {
    return (
      <section className={cn('max-w-[80ch]', className)} aria-label="revisão de correspondência">
        <p className="kicker">a que funil esta campanha pertence</p>
        <p className="mt-2 max-w-[70ch] text-[13px] leading-relaxed" role="status">
          Não há campanha com esta identidade interna, então não há o que
          comparar.{' '}
          <span className="text-muted-foreground">
            Um identificador do painel do Google não abre esta página — a
            identidade aqui é a interna.
          </span>
        </p>
      </section>
    );
  }

  // ⚠️ Falha de leitura NÃO vira "não associada". Uma lista vazia por erro de
  // rede leria como prova de que nada casa, e o operador trataria a campanha
  // como órfã com base num timeout.
  if (leitura.falhou || !leitura.revisao) {
    return (
      <section className={cn('max-w-[80ch]', className)} aria-label="revisão de correspondência">
        <p className="kicker">a que funil esta campanha pertence</p>
        <div className="mt-2" role="alert">
          <p className="text-sm leading-relaxed">
            {leitura.ocorrencia?.mensagem ??
              'Não consegui comparar esta campanha com os funis agora.'}
          </p>
          <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
            Isto <strong className="font-medium text-foreground">não</strong> significa que ela
            não tenha funil — significa que a comparação não pôde ser feita.{' '}
            {leitura.ocorrencia?.proximoPasso ?? 'Tente de novo em instantes.'}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3 h-11 md:h-9"
            onClick={leitura.recarregar}
          >
            Tentar de novo
          </Button>
        </div>
      </section>
    );
  }

  const { revisao } = leitura;
  const estado = PALAVRA_DO_ESTADO[revisao.estado] ?? PALAVRA_DO_ESTADO.nao_apurada;
  const impediu = revisao.sinais_ausentes.filter((s) => s.impede_prova);

  return (
    <section className={cn('max-w-[80ch]', className)} aria-labelledby="revisao-titulo">
      <p className="kicker">a que funil esta campanha pertence</p>
      <h2
        id="revisao-titulo"
        className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
      >
        Revisar correspondência
      </h2>

      <div className="mt-3">
        <Chip
          glifo={estado.glifo}
          palavra={estado.palavra}
          descricao={estado.descricao}
          tom={estado.tom}
        />
      </div>
      <p className="mt-2 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
        {estado.descricao}.
      </p>

      {/* O lado do Google, para o operador comparar com o olho antes de decidir. */}
      {/* Grade de duas colunas a partir de `sm`, empilhada abaixo disso — e
          empilhada por INTEIRO, nunca com um par inline e outro quebrado. Um
          rótulo que às vezes fica ao lado e às vezes acima faz o olho procurar
          a coluna a cada linha. */}
      <dl className="mt-5 grid gap-x-4 gap-y-1.5 border-t border-border pt-4 text-[13px] sm:grid-cols-[minmax(9rem,auto)_1fr]">
        <Fato rotulo="campanha na conta" valor={nomeDaCampanha ?? null} />
        <Fato rotulo="conta de anúncio" valor={contaExterna ?? null} />
        <Fato rotulo="identificador no Google" valor={idExterno ?? null} />
        <Fato rotulo="estado no Google" valor={estadoExterno ?? null} />
        <Fato rotulo="página de destino" valor={revisao.url_da_campanha} />
      </dl>

      {revisao.estado === 'associada' && revisao.vinculo && (
        <JaAssociada
          opportunityId={revisao.vinculo.opportunity_id}
          runId={revisao.vinculo.run_id}
          ocupado={desfazer.isPending}
          erro={desfazer.isError}
          aoDesfazer={(motivo) =>
            desfazer.mutate({
              vinculoId: revisao.vinculo!.vinculo_id,
              motivo,
              volcCampaignId,
            })
          }
        />
      )}

      {impediu.length > 0 && (
        <div className="mt-5 rounded-md border border-warning/40 bg-warning/[0.06] p-3">
          <p className="font-display text-[12px] font-semibold">
            O que impediu de comparar
          </p>
          <ul className="mt-1.5 space-y-1 text-[12px] leading-relaxed text-muted-foreground" role="list">
            {impediu.map((s) => (
              <li key={`${s.regra}-${s.motivo}`}>{s.motivo}.</li>
            ))}
          </ul>
        </div>
      )}

      {revisao.correspondencias.length > 0 && (
        <div className="mt-6">
          <p className="font-display text-[13px] font-semibold">
            {revisao.correspondencias.length === 1
              ? 'O funil que casa'
              : `Os ${revisao.correspondencias.length} funis que casam`}
          </p>
          <p className="mt-1 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
            Confirme só se você reconhece a operação. A associação registra quem
            confirmou, quando e qual regra casou — e pode ser desfeita, mas não
            corrigida.
          </p>

          <ul className="mt-3 space-y-2" role="list">
            {revisao.correspondencias.map((c) => (
              <CartaoDeCandidata
                key={chaveDaCorrespondencia(c)}
                candidata={c}
                escolhida={escolhida === chaveDaCorrespondencia(c)}
                aoEscolher={() => {
                  setEscolhida(chaveDaCorrespondencia(c));
                  setRecusada(false);
                }}
              />
            ))}
          </ul>

          <Acoes
            // ⚠️ `!confirmar.isSuccess` — depois de gravado, não há o que
            // confirmar de novo. Sem isto o botão continuava clicável e um
            // segundo clique disparava um SEGUNDO pedido: o servidor recusa com
            // 409 pela unicidade, mas a tela mostrava um erro logo depois de um
            // sucesso, e o operador não tem como saber qual das duas respostas
            // vale. A releitura invalidada traz o estado `associada` em
            // seguida, e é ela quem passa a mandar na tela.
            podeConfirmar={escolhida != null && !recusada && !confirmar.isSuccess}
            ocupado={confirmar.isPending}
            erro={confirmar.isError && !confirmar.isSuccess ? confirmar.error : null}
            recusada={recusada}
            aoConfirmar={() => {
              const alvo = revisao.correspondencias.find(
                (c) => chaveDaCorrespondencia(c) === escolhida,
              );
              if (!alvo) return;
              confirmar.mutate({
                volcCampaignId,
                correspondencia: alvo,
                vinculoAnterior: revisao.vinculo?.vinculo_id,
              });
            }}
            aoRecusar={() => {
              setRecusada(true);
              setEscolhida(null);
            }}
            aoDeixarPendente={() => {
              setRecusada(false);
              setEscolhida(null);
            }}
            confirmado={confirmar.isSuccess}
          />
        </div>
      )}

      {revisao.estado === 'sem_correspondencia' && (
        <p className="mt-5 max-w-[70ch] rounded-md border border-border bg-muted/40 p-3 text-[12px] leading-relaxed text-muted-foreground">
          Nenhum funil publicado desta conta aponta para a mesma página que esta
          campanha. Isso acontece quando a campanha foi criada fora do VOLC, ou
          quando o funil dela ainda não foi publicado.{' '}
          <strong className="font-medium text-foreground">
            Nada precisa ser feito agora
          </strong>{' '}
          — a comparação roda de novo a cada leitura da conta.
        </p>
      )}
    </section>
  );
};

// ── as peças ────────────────────────────────────────────────────────────────

const Fato: React.FC<{ rotulo: string; valor: string | null }> = ({ rotulo, valor }) => (
  <>
    <dt className="text-muted-foreground">{rotulo}</dt>
    <dd className="tabular mb-1.5 min-w-0 break-all font-medium sm:mb-0">{valor ?? AUSENTE}</dd>
  </>
);

const CartaoDeCandidata: React.FC<{
  candidata: Correspondencia;
  escolhida: boolean;
  aoEscolher: () => void;
}> = ({ candidata, escolhida, aoEscolher }) => {
  const forca = FORCA[candidata.forca_maxima] ?? FORCA.historica;
  return (
    <li>
      <button
        type="button"
        aria-pressed={escolhida}
        onClick={aoEscolher}
        className={cn(
          'flex w-full flex-col gap-2 rounded-md border p-3 text-left',
          'transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
          escolhida
            ? 'border-foreground/40 bg-foreground/[0.05]'
            : 'border-border hover:border-foreground/25 hover:bg-muted/40',
        )}
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-display text-[13px] font-semibold">
            funil {candidata.opportunity_id}
            {candidata.run_id != null && (
              <span className="font-normal text-muted-foreground">
                {' '}
                · versão {candidata.run_id}
              </span>
            )}
          </span>
          <Chip
            glifo={forca.glifo}
            palavra={forca.palavra}
            descricao={forca.explica}
            tom={forca.tom}
          />
          {/* ⚠️ "já decidido" e "disputado" são fatos diferentes, e o
              vínculo é por CAMPANHA no banco — nada impede duas campanhas de
              apontarem para o mesmo funil, e o resultado seria receita
              atribuída em dobro. Quando alguém já respondeu esta pergunta para
              outra campanha, o operador precisa saber ANTES de confirmar. */}
          {candidata.estado_do_funil === 'vinculada' ? (
            <Chip
              glifo={Link2}
              palavra="já associado a outra campanha"
              descricao="uma pessoa já confirmou que este funil pertence a outra campanha — associar aqui também faria a receita dele ser contada duas vezes"
              tom="atencao"
            />
          ) : (
            candidata.outras_campanhas_presentes > 0 && (
              <Chip
                glifo={TriangleAlert}
                palavra={`disputado por +${candidata.outras_campanhas_presentes}`}
                descricao="outra campanha no ar também aponta para este funil — confirme só se souber qual é qual"
                tom="atencao"
              />
            )
          )}
        </span>

        <span className="block text-[12px] leading-relaxed text-muted-foreground">
          {forca.explica}.
        </span>

        <ul className="space-y-0.5 text-[12px] leading-relaxed" role="list">
          {candidata.sinais.map((s) => (
            <li key={s.regra} className="flex gap-1.5">
              <span aria-hidden className="text-muted-foreground">
                ·
              </span>
              <span>{regraLegivel(s.regra)}</span>
            </li>
          ))}
        </ul>

        {candidata.destinos.length > 0 && (
          <span className="block break-all text-[11px] leading-relaxed text-muted-foreground">
            páginas deste funil: {candidata.destinos.join(' · ')}
          </span>
        )}
      </button>
    </li>
  );
};

const Acoes: React.FC<{
  podeConfirmar: boolean;
  ocupado: boolean;
  erro: unknown;
  recusada: boolean;
  confirmado: boolean;
  aoConfirmar: () => void;
  aoRecusar: () => void;
  aoDeixarPendente: () => void;
}> = ({
  podeConfirmar,
  ocupado,
  erro,
  recusada,
  confirmado,
  aoConfirmar,
  aoRecusar,
  aoDeixarPendente,
}) => (
  <div className="mt-4 border-t border-border pt-4">
    <div className="flex flex-wrap items-center gap-2">
      {/* ⚠️ Só vira ação primária quando há o que confirmar.
          `disabled:opacity-50` sobre a cor de destaque continua parecendo um
          botão vivo no tema escuro — medido na captura de 27/08/2026 —, e um
          botão que grita "clique" sem poder ser clicado é falsa affordance
          justamente na decisão que contamina atribuição de receita. */}
      <Button
        type="button"
        size="sm"
        variant={podeConfirmar ? 'default' : 'outline'}
        className="h-11 md:h-9"
        disabled={!podeConfirmar || ocupado}
        aria-busy={ocupado || undefined}
        onClick={aoConfirmar}
      >
        {ocupado && (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />
        )}
        Confirmar associação
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-11 md:h-9"
        disabled={ocupado}
        onClick={aoRecusar}
      >
        Nenhum destes corresponde
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-11 md:h-9"
        disabled={ocupado}
        onClick={aoDeixarPendente}
      >
        Deixar pendente
      </Button>
    </div>

    {/* O que cada botão faz, dito antes do clique — porque esta decisão é
        reversível mas não corrigível, e o operador precisa saber disso agora. */}
    <p className="mt-2 max-w-[70ch] text-[11px] leading-relaxed text-muted-foreground">
      Confirmar grava a associação no VOLC com o seu nome e a regra que casou.
      Não cria, não altera e não pausa nada na conta do Google.
    </p>

    {!podeConfirmar && !recusada && !confirmado && (
      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground" role="status">
        Escolha um funil acima para poder confirmar. Nada vem marcado de
        propósito — a escolha é a decisão.
      </p>
    )}

    {recusada && (
      <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed" role="status">
        Anotado nesta sessão: nenhum destes corresponde.{' '}
        <span className="text-muted-foreground">
          Esta recusa ainda não é registrada no servidor — a campanha continua
          como associação pendente e volta a ser oferecida na próxima leitura.
        </span>
      </p>
    )}

    {confirmado && (
      <p className="mt-2 text-[12px] leading-relaxed text-success" role="status">
        Associação registrada.
      </p>
    )}

    {/* ⚠️ A mensagem crua do servidor NÃO vem para cá — ela cita rota, status e
        biblioteca. O que chega é o que o operador pode fazer a respeito. */}
    {erro != null && (
      <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed" role="alert">
        A associação não foi gravada, e nada mudou.{' '}
        <span className="text-muted-foreground">
          Se esta campanha já tiver uma associação viva, desfaça a atual antes de
          confirmar outra.
        </span>
      </p>
    )}
  </div>
);

const JaAssociada: React.FC<{
  opportunityId: number | null;
  runId: number | null;
  ocupado: boolean;
  erro: boolean;
  aoDesfazer: (motivo: string) => void;
}> = ({ opportunityId, runId, ocupado, erro, aoDesfazer }) => (
  <div className="mt-5 rounded-md border border-border bg-muted/40 p-3">
    <p className="text-[13px] leading-relaxed">
      Esta campanha está associada ao{' '}
      <strong className="font-medium">funil {opportunityId ?? '—'}</strong>
      {runId != null && <span className="text-muted-foreground"> · versão {runId}</span>}.
    </p>
    <p className="mt-1.5 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
      Desfazer não apaga o registro: ele guarda quem associou, quando e por quê
      foi desfeito. Uma campanha sem rastro de associação é indistinguível de
      uma que nunca teve.
    </p>
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="mt-3 h-11 md:h-9"
      disabled={ocupado}
      aria-busy={ocupado || undefined}
      onClick={() => aoDesfazer('revisão manual pelo operador')}
    >
      {ocupado && (
        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />
      )}
      Desfazer associação
    </Button>
    {erro && (
      <p className="mt-2 text-[12px] leading-relaxed" role="alert">
        A associação não foi desfeita, e ela continua valendo.
      </p>
    )}
  </div>
);

export default RevisarCorrespondencia;
