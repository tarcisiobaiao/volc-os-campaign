import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Ban, CalendarClock, CheckCircle2, CircleAlert, CircleDashed, Clock3, ExternalLink,
  Loader2, LockKeyhole, PlugZap, RefreshCw, Send, ShieldCheck, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';
import * as api from './publicacaoOrganicaApi';
import {
  MODO_CONSEQUENCIA, MODO_ROTULO, MODOS,
  aguardaODestino, classeDoTom, ehTerminal, hashAbreviado, horarioLocalLegivel,
  horarioLocalValido, idAbreviado, incertoSeguro, instanteLegivel,
  plataformaLegivel, proximaAcaoDe, revisaoLegivel, rotuloDe, tomSeguro,
  versaoDaPeca, ESTADO_EXTERNO_ROTULO,
  type DestinoOrganico, type JobOrganico, type RascunhoDoFormulario,
} from './contract';

/**
 * A tela operacional da publicação orgânica.
 *
 * ## A pergunta que ela responde
 *
 * "Esta peça, nesta revisão, aprovada por quem e quando, vai para qual conta,
 * em que horário e em que fuso — e o que sabemos que já aconteecu com ela?"
 * Tudo o que está aqui existe para responder essa frase sem jargão. Nada de
 * `job_id` sozinho num cartão, nada de `estado: publicacao_solicitada` cru.
 *
 * ## Os estados que não são dado, e por que nenhum é redundante
 *
 *   carregando      ainda não sei
 *   indisponível    503: a publicação não respondeu — diferente de vazio
 *   sem permissão   403: a identidade vale, o papel não
 *   sem sessão      401: entre de novo (é outra ação, não a mesma)
 *   vazio           a API respondeu, e não há job — um FATO
 *   com dado        a fila
 *
 * Colapsar "indisponível" em "vazio" é o defeito clássico de painel: uma lista
 * em branco afirma "você não tem nenhuma publicação" com a mesma cara com que
 * afirmaria "você tem trinta". Não existe fixture neste módulo, e a ausência
 * dela é a garantia: quando a API cai, não há retrato plausível para mostrar.
 *
 * ## ⚠️ CONTRAPROVA M — o verde não é decisão desta tela
 *
 * A cor vem de `leitura.tom`, decidido em `dominio.leitura_do_estado`. Este
 * arquivo NUNCA lê o nome do estado para escolher cor; ele chama
 * `classeDoTom(job)`, que aplica a escada de veto de `contract.ts` e só sabe
 * TIRAR o verde. `em_voo`, `publicacao_solicitada`, `publicado` (que é o
 * control plane declarando, não a prova fechada) e `indeterminado` não são
 * sucesso — e um estado que este contrato não conhece também não é.
 *
 * ## Por que dois diálogos diferentes, e não um com um parâmetro
 *
 * Agendar entrega o post ao destino com hora marcada: é reversível enquanto o
 * horário não chega, e uma confirmação humana simples basta. Publicar agora
 * torna o post visível e não tem desfazer que devolva quem já viu. As duas
 * confirmações são SEPARADAS de propósito — o consentimento de publicação
 * imediata é um campo próprio (`confirmo_publicacao_imediata`), exigido pelo
 * domínio e pelo banco, e ele só entra no corpo quando a caixa foi marcada.
 * Um diálogo único com um booleano faria a diferença virar configuração.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Estados que não são dado
// ─────────────────────────────────────────────────────────────────────────────

function Moldura({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-7xl p-4 sm:p-6">{children}</div>;
}

function Carregando({ rotulo }: { rotulo: string }) {
  return (
    <div className="space-y-3" role="status" aria-label={rotulo}>
      <div className="h-20 animate-pulse rounded-lg border border-border bg-muted/40" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-24 animate-pulse rounded-md border border-border bg-muted/30" />
      ))}
      <p className="text-xs text-muted-foreground">{rotulo}…</p>
    </div>
  );
}

interface AvisoProps {
  titulo: string;
  texto: string;
  tom?: 'erro' | 'atencao' | 'neutro';
  icone: typeof ShieldCheck;
  acao?: { rotulo: string; aoClicar: () => void };
  codigo?: string;
}

function Aviso({ titulo, texto, tom = 'neutro', icone: Icone, acao, codigo }: AvisoProps) {
  const borda = tom === 'erro' ? 'border-destructive/35'
    : tom === 'atencao' ? 'border-warning/35' : 'border-border';
  const fundo = tom === 'erro' ? 'bg-destructive/10 text-destructive'
    : tom === 'atencao' ? 'bg-warning/10 text-warning' : 'bg-muted text-muted-foreground';
  return (
    <section className={cn('rounded-lg border bg-card px-5 py-10 text-center', borda)} role="alert">
      <span className={cn('mx-auto flex h-11 w-11 items-center justify-center rounded-full', fundo)}>
        <Icone aria-hidden="true" className="h-5 w-5" />
      </span>
      <h2 className="mt-4 text-lg font-semibold">{titulo}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{texto}</p>
      {acao ? (
        <button
          type="button"
          onClick={acao.aoClicar}
          className="mt-4 inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {acao.rotulo}
        </button>
      ) : null}
      {/* O código é para quem for investigar, não para quem está operando. */}
      {codigo ? (
        <p className="mt-3 text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
          código {codigo}
        </p>
      ) : null}
    </section>
  );
}

/**
 * A falha traduzida em tela — uma por motivo, nunca uma genérica para todos.
 *
 * ⚠️ Devolve `null` quando não há erro, para que quem chama possa escrever
 * `falhaEmTela(erro) ?? <Lista/>` sem inverter a leitura.
 */
function falhaEmTela(erro: unknown, aoTentarDeNovo: () => void): React.ReactNode {
  if (!(erro instanceof api.ErroDaPublicacao)) {
    if (!erro) return null;
    return (
      <Aviso
        icone={CircleAlert}
        tom="erro"
        titulo="Algo saiu do previsto"
        texto={erro instanceof Error ? erro.message : 'A tela não conseguiu ler esta resposta.'}
        acao={{ rotulo: 'Tentar de novo', aoClicar: aoTentarDeNovo }}
      />
    );
  }
  if (erro.semSessao) {
    return (
      <Aviso
        icone={LockKeyhole}
        tom="atencao"
        titulo="Sua sessão expirou"
        texto="Entre novamente para continuar. Nenhuma publicação foi afetada por isso."
        codigo={erro.codigo}
      />
    );
  }
  if (erro.semPermissao) {
    return (
      <Aviso
        icone={ShieldCheck}
        tom="atencao"
        titulo="Acesso restrito"
        texto="Sua identidade vale; o papel é que não permite operar a publicação orgânica. Peça a um administrador."
        codigo={erro.codigo}
      />
    );
  }
  if (erro.indisponivel) {
    return (
      <Aviso
        icone={PlugZap}
        tom="erro"
        titulo="A publicação não respondeu"
        texto={`${erro.message} Vazio e indisponível são fatos diferentes: esta tela não mostra uma fila em branco no lugar de uma falha, porque isso afirmaria que você não tem nada agendado.`}
        acao={{ rotulo: 'Tentar de novo', aoClicar: aoTentarDeNovo }}
        codigo={erro.codigo}
      />
    );
  }
  return (
    <Aviso
      icone={CircleAlert}
      tom="erro"
      titulo="A publicação recusou esta leitura"
      texto={erro.message}
      acao={{ rotulo: 'Tentar de novo', aoClicar: aoTentarDeNovo }}
      codigo={erro.codigo}
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// O selo de estado — o único lugar onde a cor é escolhida
// ─────────────────────────────────────────────────────────────────────────────

function iconeDoTom(tom: string) {
  if (tom === 'sucesso') return CheckCircle2;
  if (tom === 'falha') return Ban;
  if (tom === 'aguardando') return Clock3;
  if (tom === 'atencao') return CircleAlert;
  return CircleDashed;
}

/**
 * O selo. `data-tom` e `data-incerto` existem para o teste da contraprova
 * conseguir varrer todos os estados sem depender de texto traduzido.
 *
 * ⚠️ `data-incerto` publica a incerteza EFETIVA (`incertoSeguro`), não o valor
 * cru de `leitura.incerto`. O atributo cru mentia por omissão: um `em_voo` sem
 * o campo (backend antigo, proxy que cortou o JSON) saía `false`, e a varredura
 * do DOM — que filtra justamente por este atributo — deixava de olhar a linha
 * que o piso `ESTADOS_INCERTOS` existe para proteger. O que o servidor afirmou
 * continua visível em `data-incerto-servidor` e `data-tom-servidor`, para que a
 * diferença entre o que ele disse e o que a tela concluiu seja auditável em vez
 * de invisível — é por esses dois que o teste encontra, no DOM, as linhas em que
 * o veto precisou disparar. Sem eles a varredura não sabe distinguir um selo
 * legitimamente cinza de um selo que o servidor pediu verde e a tela recusou.
 */
function SeloDeEstado({ job }: { job: Pick<JobOrganico, 'estado' | 'leitura'> }) {
  const tom = tomSeguro(job);
  const Icone = iconeDoTom(tom);
  const pulsante = tom !== 'sucesso' && tom !== 'falha' && tom !== 'neutro';
  const declarado = job.leitura?.incerto;
  return (
    <span
      data-estado={String(job.estado)}
      data-tom={tom}
      data-tom-servidor={typeof job.leitura?.tom === 'string' ? job.leitura.tom : 'ausente'}
      data-incerto={String(incertoSeguro(job))}
      data-incerto-servidor={typeof declarado === 'boolean' ? String(declarado) : 'ausente'}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]',
        classeDoTom(job),
      )}
    >
      <Icone aria-hidden="true" className={cn('h-3.5 w-3.5', pulsante && tom === 'aguardando' && 'animate-pulse')} />
      {rotuloDe(job)}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Diálogo de confirmação — foco, teclado e o texto do que vai acontecer
// ─────────────────────────────────────────────────────────────────────────────

const FOCAVEIS = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]';

interface DialogoProps {
  titulo: string;
  /** O que vai acontecer, em prosa. Nunca "tem certeza?". */
  consequencia: React.ReactNode;
  rotuloConfirmar: string;
  /** `true` para o diálogo forte: destaque destrutivo e caixa obrigatória. */
  forte?: boolean;
  /** A caixa que o humano precisa marcar. Só existe no diálogo forte. */
  marcacao?: { id: string; rotulo: string };
  ocupado?: boolean;
  /** Confirmar bloqueado por falta de dado — diferente de estar ocupado. */
  impedido?: boolean;
  aoConfirmar: (marcado: boolean) => void;
  aoCancelar: () => void;
  children?: React.ReactNode;
}

function Dialogo({
  titulo, consequencia, rotuloConfirmar, forte = false, marcacao,
  ocupado = false, impedido = false, aoConfirmar, aoCancelar, children,
}: DialogoProps) {
  const painel = React.useRef<HTMLDivElement>(null);
  const [marcado, setMarcado] = React.useState(false);
  const tituloId = React.useId();
  const textoId = React.useId();

  // O foco entra no painel para que o leitor de tela leia o título e a
  // consequência antes de qualquer botão. `tabIndex={-1}` deixa o painel
  // focável por programa sem entrar na ordem de tabulação.
  React.useEffect(() => { painel.current?.focus(); }, []);

  /**
   * Escape cancela; Tab circula DENTRO do painel.
   *
   * ⚠️ O ciclo é implementado à mão porque o diálogo não usa portal: sem ele o
   * Tab sairia para a página de trás, e a pessoa continuaria "dentro" de um
   * diálogo que confirma uma publicação enquanto edita o formulário atrás dele.
   */
  function aoTeclar(evento: React.KeyboardEvent<HTMLDivElement>) {
    if (evento.key === 'Escape') {
      evento.preventDefault();
      aoCancelar();
      return;
    }
    if (evento.key !== 'Tab') return;
    const alvos = Array.from(painel.current?.querySelectorAll<HTMLElement>(FOCAVEIS) ?? []);
    if (alvos.length === 0) return;
    const primeiro = alvos[0];
    const ultimo = alvos[alvos.length - 1];
    const atual = document.activeElement as HTMLElement | null;
    if (evento.shiftKey && (atual === primeiro || atual === painel.current)) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && (atual === ultimo || atual === painel.current)) {
      evento.preventDefault();
      primeiro.focus();
    }
  }

  const confirmarBloqueado = ocupado || impedido || (Boolean(marcacao) && !marcado);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4">
      <div
        ref={painel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
        aria-describedby={textoId}
        tabIndex={-1}
        onKeyDown={aoTeclar}
        className={cn(
          'w-full max-w-lg rounded-lg border bg-card p-5 shadow-lg outline-none',
          forte ? 'border-destructive/45' : 'border-border',
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={tituloId} className="text-base font-semibold">{titulo}</h2>
          <button
            type="button"
            onClick={aoCancelar}
            aria-label="Fechar sem confirmar"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>

        <div
          id={textoId}
          className={cn(
            'mt-3 rounded-md border px-3 py-2 text-sm leading-6',
            forte
              ? 'border-destructive/35 bg-destructive/10 text-destructive'
              : 'border-border bg-muted/50 text-muted-foreground',
          )}
        >
          {consequencia}
        </div>

        {children ? <div className="mt-3">{children}</div> : null}

        {marcacao ? (
          <label htmlFor={marcacao.id} className="mt-4 flex items-start gap-2 text-sm">
            <input
              id={marcacao.id}
              name={marcacao.id}
              type="checkbox"
              checked={marcado}
              onChange={(e) => setMarcado(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <span className="leading-6">{marcacao.rotulo}</span>
          </label>
        ) : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={aoCancelar}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={confirmarBloqueado}
            onClick={() => aoConfirmar(marcado)}
            className={cn(
              'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              forte
                ? 'bg-destructive text-destructive-foreground'
                : 'bg-primary text-primary-foreground',
            )}
          >
            {ocupado ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
            {rotuloConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Prontidão do control plane
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A faixa de prontidão.
 *
 * ⚠️ Ela NUNCA fica verde. A API oficial do Postiz não tem endpoint de health
 * (medido em 02/09/2026); `prontidao` usa `GET /integrations` como PROXY, e o
 * backend diz isso no campo `fonte`. Pintar de verde um proxy de saúde seria
 * afirmar uma capacidade que a API não documenta — a faixa mostra a FONTE junto
 * do resultado justamente para que ninguém confunda as duas coisas.
 */
function FaixaDeProntidao({
  dado, erro, carregando,
}: {
  dado?: { pronto: boolean; fonte: string; detalhe: string; canais_visiveis?: number | null };
  erro: unknown;
  carregando: boolean;
}) {
  const desconhecido = carregando || Boolean(erro) || !dado;
  const pronto = Boolean(dado?.pronto);
  const classe = desconhecido || !pronto
    ? 'border-warning/35 bg-warning/10 text-warning'
    : 'border-info/30 bg-info/10 text-info';
  const texto = desconhecido
    ? 'Não sabemos se o control plane está de pé. Enquanto isso, despachar e reconciliar podem falhar.'
    : pronto
      ? `${dado?.detalhe ?? 'control plane respondeu'} — fonte: ${dado?.fonte}. Isto é um proxy de saúde, não um health check oficial.`
      : `${dado?.detalhe ?? 'control plane indisponível'} — fonte: ${dado?.fonte}. Nada pode ser despachado agora.`;

  return (
    <p
      role="status"
      data-prontidao={desconhecido ? 'desconhecida' : pronto ? 'pronta' : 'indisponivel'}
      className={cn('flex items-start gap-2 rounded-md border px-3 py-2 text-xs leading-5', classe)}
    >
      <PlugZap aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        <strong className="font-semibold">Control plane: </strong>
        {texto}
        {typeof dado?.canais_visiveis === 'number'
          ? ` ${dado.canais_visiveis} canal(is) visível(is).`
          : null}
      </span>
    </p>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Formulário do job
// ─────────────────────────────────────────────────────────────────────────────

const ENTRADA = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring';
const AREA = 'min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring';

function Campo({
  id, rotulo, ajuda, children,
}: { id: string; rotulo: string; ajuda?: string; children: React.ReactNode }) {
  return (
    <div className="block">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-foreground">{rotulo}</label>
      {children}
      {ajuda ? (
        <span id={`${id}-ajuda`} className="mt-1 block text-[11px] leading-4 text-muted-foreground">
          {ajuda}
        </span>
      ) : null}
    </div>
  );
}

const FORMULARIO_VAZIO: RascunhoDoFormulario = {
  peca_id: '',
  peca_versao: '1',
  autorizacao_id: '',
  destino_id: '',
  modo: 'draft',
  timezone: 'America/Sao_Paulo',
  horario_local: '',
  texto: '',
};

/**
 * O formulário de criação.
 *
 * ⚠️ Peça, versão e aprovação entram como IDENTIFICADORES, e isso é uma
 * limitação declarada — não um esquecimento. Um seletor de peça aprovada teria
 * de ler a superfície de criativos, que está fora da fronteira desta missão. O
 * que a tela garante é o que o backend garante: a peça citada precisa existir,
 * a aprovação precisa existir e não estar revogada, e o snapshot é montado pelo
 * banco a partir da versão que a aprovação cobre.
 */
function FormularioDeJob({
  destinos, prontoParaEnviar, aoPedirConfirmacao, aoCriarDireto, enviando, erro,
}: {
  destinos: DestinoOrganico[];
  prontoParaEnviar: boolean;
  aoPedirConfirmacao: (rascunho: RascunhoDoFormulario, destino: DestinoOrganico) => void;
  aoCriarDireto: (rascunho: RascunhoDoFormulario) => void;
  enviando: boolean;
  erro: unknown;
}) {
  const [form, setForm] = React.useState<RascunhoDoFormulario>(FORMULARIO_VAZIO);
  const mudar = (campo: keyof RascunhoDoFormulario) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [campo]: e.target.value }));

  const destino = destinos.find((d) => d.destino_id === form.destino_id);

  // O fuso acompanha o destino escolhido: cada canal declara o seu padrão, e
  // deixar o operador digitar um fuso diferente do canal é como o horário certo
  // no lugar errado entra sem ninguém notar.
  React.useEffect(() => {
    if (destino?.timezone_padrao) setForm((f) => ({ ...f, timezone: destino.timezone_padrao }));
  }, [destino?.timezone_padrao]);

  const bloqueadores: string[] = [];
  if (!form.peca_id.trim()) bloqueadores.push('informe o identificador da peça aprovada');
  // ⚠️ A versão é BLOQUEADOR, não um campo que a tela conserta sozinha. Ver o
  // comentário de `versaoDaPeca` em contract.ts: um campo vazio virava `1` na
  // conversão, o diálogo mostrava "versão " e o corpo levava a v1 — a revisão
  // errada carimbada com a aprovação de outra. É preferível não deixar enviar.
  if (versaoDaPeca(form.peca_versao) === null) {
    bloqueadores.push('informe a versão da peça: um número inteiro a partir de 1, '
      + 'porque é a revisão exata que a aprovação cobre');
  }
  if (!form.autorizacao_id.trim()) bloqueadores.push('informe o identificador da aprovação');
  if (!destino) bloqueadores.push('escolha um destino');
  if (destino && !destino.apto) {
    bloqueadores.push(destino.motivo ?? 'este destino não está apto a publicar');
  }
  if (form.modo === 'schedule' && !form.horario_local.trim()) {
    bloqueadores.push('agendar exige o horário local declarado');
  } else if (form.modo === 'schedule' && !horarioLocalValido(form.horario_local)) {
    // ⚠️ A forma é conferida ANTES da confirmação. Sem isto, "amanhã cedo"
    // abria o diálogo, aparecia no lugar do horário e colhia um "sim" humano
    // para um instante que não existe — o 400 `horario_invalido` só chegava
    // depois do consentimento dado.
    bloqueadores.push('o horário local precisa ser AAAA-MM-DD HH:MM, sem fuso no texto, '
      + 'e precisa existir no calendário');
  }
  if (!form.texto.trim()) bloqueadores.push('escreva o texto que vai ao ar');
  if (!prontoParaEnviar) {
    bloqueadores.push('o control plane não está confirmado; o job pode ser criado, mas não despachado');
  }

  // ⚠️ O único bloqueador que NÃO impede criar é a prontidão: criar é registrar
  // a intenção, e a intenção pode ser registrada com o control plane fora do ar.
  const impedidoDeCriar = bloqueadores.some(
    (b) => !b.startsWith('o control plane não está confirmado'),
  );

  function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (impedidoDeCriar || !destino) return;
    // `draft` não sai daqui e não fica público: criar é o ato inteiro, e um
    // diálogo aqui seria cerimônia sem consequência. `schedule` e `now` passam
    // pela confirmação humana, cada um com o seu texto.
    if (form.modo === 'draft') aoCriarDireto(form);
    else aoPedirConfirmacao(form, destino);
  }

  return (
    <form onSubmit={enviar} className="space-y-4 rounded-lg border border-border bg-card p-5" aria-label="Nova publicação orgânica">
      <div>
        <h2 className="text-sm font-semibold">Nova publicação</h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Criar registra a intenção. Nada sai para o destino neste passo — liberar e despachar são
          atos separados, cada um com o seu clique.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Campo id="peca-id" rotulo="Peça aprovada (identificador do master)">
          <input id="peca-id" name="peca-id" className={ENTRADA} value={form.peca_id} onChange={mudar('peca_id')} />
        </Campo>
        <Campo id="peca-versao" rotulo="Versão da peça" ajuda="A revisão exata que a aprovação cobre.">
          <input id="peca-versao" name="peca-versao" type="number" min={1} className={ENTRADA}
            value={form.peca_versao} onChange={mudar('peca_versao')} aria-describedby="peca-versao-ajuda" />
        </Campo>
        <Campo id="autorizacao-id" rotulo="Aprovação (identificador)"
          ajuda="Uma aprovação que já existia. Esta tela não assina a própria autorização.">
          <input id="autorizacao-id" name="autorizacao-id" className={ENTRADA}
            value={form.autorizacao_id} onChange={mudar('autorizacao_id')} aria-describedby="autorizacao-id-ajuda" />
        </Campo>
        <Campo id="destino-id" rotulo="Destino"
          ajuda="Um destino sem adapter apto aparece aqui desabilitado, com o motivo. Ele não é escondido.">
          <select id="destino-id" name="destino-id" className={ENTRADA} value={form.destino_id}
            onChange={mudar('destino_id')} aria-describedby="destino-id-ajuda">
            <option value="">Escolha um destino…</option>
            {destinos.map((d) => (
              <option key={d.destino_id} value={d.destino_id} disabled={!d.apto}>
                {`${d.identidade_logica} · ${plataformaLegivel(d.plataforma)}`}
                {d.apto ? '' : ` — indisponível: ${d.motivo ?? 'sem adapter apto'}`}
              </option>
            ))}
          </select>
        </Campo>
      </div>

      {/* A lista de destinos aparece por extenso porque `<option disabled>` não
          é lida por todo leitor de tela, e o motivo do inapto é justamente o
          que a guarda do ADR exige que fique visível. */}
      <ul className="space-y-1" aria-label="Destinos registrados">
        {destinos.map((d) => (
          <li key={d.destino_id} data-destino={d.destino_id} data-apto={String(d.apto)}
            className={cn('flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs',
              d.apto ? 'border-border bg-background' : 'border-warning/35 bg-warning/10')}>
            <span className="font-medium text-foreground">{d.identidade_logica}</span>
            <span className="text-muted-foreground">{plataformaLegivel(d.plataforma)}</span>
            <span className="text-muted-foreground">· {d.nome}</span>
            <span className="text-muted-foreground">· fuso {d.timezone_padrao}</span>
            {d.apto ? null : (
              <span className="ml-auto font-medium text-warning">
                Indisponível: {d.motivo ?? 'sem adapter apto'}
              </span>
            )}
          </li>
        ))}
      </ul>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-xs font-medium text-foreground">Modo</legend>
        <div className="flex flex-wrap gap-2">
          {MODOS.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={form.modo === m}
              onClick={() => setForm((f) => ({ ...f, modo: m, horario_local: m === 'schedule' ? f.horario_local : '' }))}
              className={cn(
                'rounded-md border px-3 py-2 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                form.modo === m ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-background text-muted-foreground',
              )}
            >
              {MODO_ROTULO[m]}
            </button>
          ))}
        </div>
        <p className="text-[11px] leading-5 text-muted-foreground">{MODO_CONSEQUENCIA[form.modo]}</p>
      </fieldset>

      {form.modo === 'schedule' ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo id="horario-local" rotulo="Horário local"
            ajuda="AAAA-MM-DD HH:MM. Sem fuso no texto — o fuso é o campo ao lado.">
            <input id="horario-local" name="horario-local" className={ENTRADA} placeholder="2026-09-10 09:30"
              value={form.horario_local} onChange={mudar('horario_local')} aria-describedby="horario-local-ajuda" />
          </Campo>
          <Campo id="timezone" rotulo="Fuso declarado (IANA)"
            ajuda="A conversão para instante acontece no banco, uma vez só.">
            <input id="timezone" name="timezone" className={ENTRADA} value={form.timezone}
              onChange={mudar('timezone')} aria-describedby="timezone-ajuda" />
          </Campo>
        </div>
      ) : null}

      <Campo id="texto" rotulo="Texto que vai ao ar"
        ajuda="Esta v1 publica texto. Imagem exige upload no control plane, que não foi exercitado.">
        <textarea id="texto" name="texto" className={AREA} value={form.texto}
          onChange={mudar('texto')} aria-describedby="texto-ajuda" />
      </Campo>

      {bloqueadores.length > 0 ? (
        <div className="rounded-md border border-warning/35 bg-warning/10 px-3 py-2">
          <p className="text-xs font-semibold text-warning">Falta para poder enviar</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-warning">
            {bloqueadores.map((b) => <li key={b}>{b}</li>)}
          </ul>
        </div>
      ) : null}

      {erro ? (
        <p role="alert" className="rounded-md border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {erro instanceof Error ? erro.message : 'Não foi possível criar este job.'}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={impedidoDeCriar || enviando}
        className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {enviando ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
        {form.modo === 'now' ? 'Revisar antes de publicar agora'
          : form.modo === 'schedule' ? 'Revisar antes de agendar' : 'Criar rascunho'}
      </button>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// O cartão do job — a frase inteira, sem jargão
// ─────────────────────────────────────────────────────────────────────────────

function Linha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
      <dt className="min-w-28 font-medium text-muted-foreground">{rotulo}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}

interface AcaoDoJob {
  chave: 'liberar' | 'despachar' | 'reconciliar' | 'cancelar';
  rotulo: string;
  /** Preenchido quando a ação está bloqueada. Sempre acionável, nunca "erro". */
  impedimento?: string;
  forte?: boolean;
}

/**
 * Qual botão este job merece agora.
 *
 * ⚠️ A decisão usa o ESTADO, e isso é legítimo: escolher qual ato é possível é
 * exatamente o que a máquina de estados da v14_01 define. O que a tela nunca faz
 * a partir do estado é escolher COR — essa vem de `leitura.tom`.
 */
function acoesDoJob(
  job: JobOrganico,
  controlPlanePronto: boolean,
): AcaoDoJob[] {
  const estado = String(job.estado);
  const aprovacaoRevogada = Boolean(job.aprovacao?.revogada_em);
  const semControlPlane = controlPlanePronto
    ? undefined
    : 'o control plane não está confirmado; nada pode ser despachado agora';

  if (estado === 'rascunho') {
    return [
      {
        chave: 'liberar',
        rotulo: 'Liberar para despacho',
        impedimento: aprovacaoRevogada
          ? 'a aprovação deste job foi revogada depois da criação; crie um job novo com uma aprovação válida'
          : undefined,
      },
      { chave: 'cancelar', rotulo: 'Cancelar' },
    ];
  }
  if (estado === 'pronto') {
    return [
      {
        chave: 'despachar',
        rotulo: job.modo === 'now' ? 'Publicar agora' : job.modo === 'schedule' ? 'Entregar agendamento' : 'Criar rascunho no destino',
        impedimento: semControlPlane,
        forte: job.modo === 'now',
      },
      { chave: 'cancelar', rotulo: 'Cancelar' },
    ];
  }
  // ⚠️ `em_voo` não tem botão nenhum, e é de propósito: o pedido pode estar
  // chegando ao destino neste instante. Cancelar esconderia um post que existe;
  // reenviar duplicaria. A única coisa certa a fazer é esperar.
  if (estado === 'em_voo') return [];
  if (['rascunho_externo', 'agendado', 'publicacao_solicitada', 'publicado', 'indeterminado'].includes(estado)) {
    return [{ chave: 'reconciliar', rotulo: 'Conferir no destino', impedimento: semControlPlane }];
  }
  return [];
}

/**
 * A frase do rodapé quando nenhum botão é oferecido — e o motivo dela.
 *
 * `motivo` sai no DOM em `data-rodape-sem-acao` para que o teste possa afirmar
 * QUAL ramo respondeu sem depender do texto traduzido.
 *
 * ⚠️ DEFEITO MEDIDO (revisão de 02/09/2026): o rodapé tinha DOIS ramos —
 * terminal e "espere". Um job em `falha` não é terminal (o backend só marca
 * terminal `reconciliado` e `cancelado`, em `aplicacao._com_leitura`) e não tem
 * botão nenhum, então caía no ramo do "espere". O resultado era a tela dando
 * duas ordens opostas com três linhas de distância: o `aria-live` do cabeçalho
 * imprimindo a próxima ação do servidor ("Leia o erro e crie um job novo — este
 * não é rearmado.") e o rodapé mandando "Espere a resposta do destino antes de
 * decidir." Duas ordens contrárias na mesma tela são piores que nenhuma: quem
 * opera escolhe a mais confortável, que aqui é esperar por uma resposta que
 * nunca vem.
 *
 * Agora o rodapé responde à MESMA autoridade do `aria-live` — a `leitura` do
 * servidor, passada pelas escadas de veto do contrato:
 *
 *   terminal        nada acontece sem um job novo (`ehTerminal`, já vetado);
 *   aguardando      o pedido está em trânsito (`aguardaODestino`) — e só aqui
 *                   "espere" é uma instrução verdadeira;
 *   falha           o tom do servidor diz que acabou mal; a saída é um job novo,
 *                   e nenhum botão desta tela rearma o que falhou;
 *   o resto         a tela não inventa ordem: aponta para a próxima ação que já
 *                   está escrita acima.
 */
function rodapeSemAcao(job: JobOrganico): { motivo: string; frase: string } {
  if (ehTerminal(job)) {
    return {
      motivo: 'terminal',
      frase: 'Nada a fazer neste job. Um novo ato exige um job novo.',
    };
  }
  if (aguardaODestino(job)) {
    return {
      motivo: 'aguardando_destino',
      frase: 'Nenhuma ação é segura neste estado: o pedido já saiu e a resposta do destino '
        + 'ainda não chegou. Espere a resposta do destino antes de decidir.',
    };
  }
  if (tomSeguro(job) === 'falha') {
    return {
      motivo: 'falha',
      frase: 'Este job não é rearmado por nenhum botão desta tela. A saída está na próxima '
        + 'ação acima: um job novo, com o que causou a falha corrigido.',
    };
  }
  return {
    motivo: 'sem_acao_nesta_tela',
    frase: 'Nenhum botão desta tela age sobre este estado. Siga a próxima ação descrita '
      + 'acima antes de qualquer coisa.',
  };
}

function CartaoDoJob({
  job, selecionado, aoSelecionar,
}: { job: JobOrganico; selecionado: boolean; aoSelecionar: () => void }) {
  return (
    <button
      type="button"
      onClick={aoSelecionar}
      aria-pressed={selecionado}
      className={cn(
        'w-full rounded-md border px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selecionado ? 'border-primary bg-primary/5' : 'border-border bg-card hover:bg-muted/40',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          {job.destino?.identidade_logica ?? 'destino não identificado'}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {plataformaLegivel(job.destino?.plataforma)}
          </span>
        </span>
        <SeloDeEstado job={job} />
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {MODO_ROTULO[String(job.modo)] ?? job.modo}
        {' · '}
        {job.modo === 'schedule'
          ? horarioLocalLegivel(job.horario_local, job.timezone)
          : `fuso ${job.timezone}`}
        {' · peça '}
        {revisaoLegivel(job.peca)}
      </p>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// O inspetor — a frase completa e o botão seguro
// ─────────────────────────────────────────────────────────────────────────────

function InspetorDoJob({
  job, controlPlanePronto, ocupado, erroDaAcao, aoAgir,
}: {
  job: JobOrganico;
  controlPlanePronto: boolean;
  ocupado: boolean;
  erroDaAcao: unknown;
  aoAgir: (acao: AcaoDoJob, job: JobOrganico) => void;
}) {
  const acoes = acoesDoJob(job, controlPlanePronto);
  const recibo = job.recibo;
  const rodape = rodapeSemAcao(job);

  return (
    <section aria-labelledby="inspetor-titulo" className="rounded-lg border border-border bg-card">
      <header className="border-b border-border p-4">
        <h2 id="inspetor-titulo" className="text-sm font-semibold">
          {job.destino?.identidade_logica ?? 'destino não identificado'}
          {' · '}
          {plataformaLegivel(job.destino?.plataforma)}
        </h2>
        {/*
          ⚠️ A região viva. O estado é a informação que muda sozinha nesta tela —
          um despacho, uma reconciliação — e quem usa leitor de tela precisa ouvir
          a mudança sem varrer a página atrás dela. `polite` e não `assertive`:
          isto informa, não interrompe.
        */}
        <div role="status" aria-live="polite" className="mt-2 space-y-2">
          <SeloDeEstado job={job} />
          <p className="text-xs leading-6 text-muted-foreground">
            <strong className="font-semibold text-foreground">Próxima ação: </strong>
            {proximaAcaoDe(job)}
          </p>
        </div>
      </header>

      <dl className="space-y-2 border-b border-border p-4">
        <Linha rotulo="Peça">{idAbreviado(job.peca?.id)}</Linha>
        <Linha rotulo="Revisão">
          versão {job.peca?.versao ?? '—'} · conteúdo {hashAbreviado(job.peca?.content_hash)}
        </Linha>
        <Linha rotulo="Aprovada por">
          {idAbreviado(job.aprovacao?.ator_id)}
          {job.aprovacao?.decidido_em ? ` em ${instanteLegivel(job.aprovacao.decidido_em)}` : ' (data não registrada)'}
          {job.aprovacao?.finalidade ? ` · finalidade: ${job.aprovacao.finalidade}` : ''}
        </Linha>
        <Linha rotulo="Destino">
          {job.destino?.identidade_logica} · {plataformaLegivel(job.destino?.plataforma)}
        </Linha>
        <Linha rotulo="Modo">{MODO_ROTULO[String(job.modo)] ?? String(job.modo)}</Linha>
        <Linha rotulo="Horário">
          {job.modo === 'schedule'
            ? horarioLocalLegivel(job.horario_local, job.timezone)
            : `sem horário marcado · fuso declarado ${job.timezone}`}
        </Linha>
        {job.instante_utc ? (
          <Linha rotulo="Instante (UTC)">
            {job.instante_utc} · no seu relógio: {instanteLegivel(job.instante_utc)}
          </Linha>
        ) : null}
        <Linha rotulo="Tentativas">{job.tentativas ?? 0}</Linha>
      </dl>

      {job.aprovacao?.revogada_em ? (
        <p className="mx-4 mb-4 rounded-md border border-destructive/35 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          Esta aprovação foi revogada em {instanteLegivel(job.aprovacao.revogada_em)}. O job não pode ser liberado.
        </p>
      ) : null}

      {job.ultimo_erro ? (
        <p className="border-b border-border px-4 py-3 text-xs leading-5 text-destructive">
          <strong className="font-semibold">Último erro registrado: </strong>
          {job.ultimo_erro}
        </p>
      ) : null}

      {recibo?.referencia_externa || recibo?.url_publicada ? (
        <div className="border-b border-border p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Recibo do destino
          </h3>
          <dl className="mt-2 space-y-2">
            <Linha rotulo="Estado no destino">
              {ESTADO_EXTERNO_ROTULO[String(recibo?.estado_externo)] ?? recibo?.estado_externo ?? '—'}
            </Linha>
            <Linha rotulo="Referência">{recibo?.referencia_externa ?? '—'}</Linha>
            <Linha rotulo="Publicado em">{instanteLegivel(recibo?.publicado_em)}</Linha>
            <Linha rotulo="Observado em">{instanteLegivel(recibo?.observado_em)}</Linha>
          </dl>
          {recibo?.url_publicada ? (
            <a
              href={recibo.url_publicada}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
              Abrir a publicação
            </a>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              O destino ainda não devolveu uma URL pública para este post.
            </p>
          )}
        </div>
      ) : null}

      <div className="space-y-2 p-4">
        {erroDaAcao ? (
          <p role="alert" className="rounded-md border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {erroDaAcao instanceof Error ? erroDaAcao.message : 'A operação não foi concluída.'}
          </p>
        ) : null}

        {acoes.length === 0 ? (
          <p data-rodape-sem-acao={rodape.motivo} className="text-xs leading-5 text-muted-foreground">
            {rodape.frase}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {acoes.map((acao) => (
            <span key={acao.chave} className="inline-flex flex-col gap-1">
              <button
                type="button"
                disabled={Boolean(acao.impedimento) || ocupado}
                onClick={() => aoAgir(acao, job)}
                aria-describedby={acao.impedimento ? `impedimento-${acao.chave}` : undefined}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  acao.chave === 'cancelar'
                    ? 'border border-border bg-background hover:bg-muted'
                    : acao.forte
                      ? 'bg-destructive text-destructive-foreground'
                      : 'bg-primary text-primary-foreground',
                )}
              >
                {ocupado ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
                  : acao.chave === 'reconciliar' ? <RefreshCw aria-hidden="true" className="h-4 w-4" />
                    : acao.chave === 'cancelar' ? <Ban aria-hidden="true" className="h-4 w-4" />
                      : acao.chave === 'despachar' ? <Send aria-hidden="true" className="h-4 w-4" />
                        : <CalendarClock aria-hidden="true" className="h-4 w-4" />}
                {acao.rotulo}
              </button>
              {acao.impedimento ? (
                <span id={`impedimento-${acao.chave}`} className="max-w-xs text-[11px] leading-4 text-warning">
                  {acao.impedimento}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// O painel
// ─────────────────────────────────────────────────────────────────────────────

type Confirmacao =
  | { tipo: 'criar'; rascunho: RascunhoDoFormulario; destino: DestinoOrganico }
  | { tipo: 'acao'; acao: AcaoDoJob; job: JobOrganico };

export function PublicacaoOrganicaContent() {
  const { toast } = useToast();
  const clientes = useQueryClient();
  const [selecionado, setSelecionado] = React.useState<string | null>(null);
  const [confirmacao, setConfirmacao] = React.useState<Confirmacao | null>(null);
  const [motivoDoCancelamento, setMotivoDoCancelamento] = React.useState('');

  const configurada = api.publicacaoConfigurada();

  const jobs = useQuery({
    queryKey: ['publicacao-organica', 'jobs'],
    queryFn: () => api.listarJobs({ limite: 50 }),
    // Sem retry: uma publicação que não responde tem de DIZER que não responde,
    // e três tentativas silenciosas só atrasam a frase por alguns segundos.
    retry: false,
    enabled: configurada,
  });

  const destinos = useQuery({
    queryKey: ['publicacao-organica', 'destinos'],
    queryFn: () => api.listarDestinos(),
    retry: false,
    enabled: configurada,
  });

  const prontidao = useQuery({
    queryKey: ['publicacao-organica', 'prontidao'],
    queryFn: () => api.prontidao(),
    retry: false,
    enabled: configurada,
  });

  const controlPlanePronto = Boolean(prontidao.data?.pronto);

  function recarregar() {
    void clientes.invalidateQueries({ queryKey: ['publicacao-organica'] });
  }

  const criar = useMutation({
    mutationFn: (entrada: api.PedidoDeJob) => api.criarJob(entrada),
    onSuccess: (recibo) => {
      toast({
        title: recibo.idempotente ? 'Nada novo foi criado' : 'Job criado',
        description: recibo.idempotente
          ? 'Este pedido é idêntico a um que já existia; o recibo devolvido é o do original.'
          : 'O job nasceu como rascunho. Libere e despache quando quiser que ele saia.',
      });
      setConfirmacao(null);
      recarregar();
    },
  });

  const agir = useMutation({
    mutationFn: async ({ acao, job }: { acao: AcaoDoJob; job: JobOrganico }) => {
      if (acao.chave === 'liberar') return api.liberar(job.job_id);
      if (acao.chave === 'despachar') return api.despachar(job.job_id);
      if (acao.chave === 'reconciliar') return api.reconciliar(job.job_id);
      return api.cancelar(job.job_id, motivoDoCancelamento.trim());
    },
    onSuccess: (recibo) => {
      toast({
        title: recibo.idempotente ? 'Nada novo aconteceu' : 'Operação registrada',
        description: `Estado agora: ${recibo.estado ?? 'inalterado'}.`,
      });
      setConfirmacao(null);
      setMotivoDoCancelamento('');
      recarregar();
    },
  });

  const lista = jobs.data?.jobs ?? [];
  const jobEmFoco = lista.find((j) => j.job_id === selecionado) ?? lista[0] ?? null;

  if (!configurada) {
    return (
      <Moldura>
        <Aviso
          icone={PlugZap}
          tom="atencao"
          titulo="A publicação não está configurada neste ambiente"
          texto="Falta o endereço da API (variável VITE_PAUTADOR_API_URL). Sem ele não há como perguntar nada — e inventar uma resposta seria pior do que não ter."
        />
      </Moldura>
    );
  }

  const falha = falhaEmTela(jobs.error, recarregar);

  return (
    <Moldura>
      <header className="mb-4 space-y-3">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight">Publicação orgânica</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
            Cada linha aqui é uma peça aprovada indo para uma conta específica, num horário
            declarado. Criar não publica; liberar não publica; só despachar fala com o destino.
          </p>
        </div>
        <FaixaDeProntidao
          dado={prontidao.data}
          erro={prontidao.error}
          carregando={prontidao.isLoading}
        />
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="space-y-4">
          {destinos.isLoading ? (
            <Carregando rotulo="Carregando os destinos" />
          ) : destinos.error ? (
            falhaEmTela(destinos.error, recarregar)
          ) : (
            <FormularioDeJob
              destinos={destinos.data?.destinos ?? []}
              prontoParaEnviar={controlPlanePronto}
              enviando={criar.isPending}
              erro={criar.error}
              aoCriarDireto={(rascunho) => criar.mutate(api.paraPedido(rascunho, false))}
              aoPedirConfirmacao={(rascunho, destino) =>
                setConfirmacao({ tipo: 'criar', rascunho, destino })}
            />
          )}
        </div>

        <div className="space-y-4">
          <section aria-labelledby="fila-titulo" className="space-y-2">
            <h2 id="fila-titulo" className="text-sm font-semibold">Fila de publicações</h2>
            {jobs.isLoading ? (
              <Carregando rotulo="Carregando as publicações" />
            ) : falha ? (
              falha
            ) : lista.length === 0 ? (
              <Aviso
                icone={CircleDashed}
                titulo="Nenhuma publicação registrada"
                texto="A publicação respondeu, e não há job nenhum. Isto é um fato, não uma falha: quando a API não responde, esta tela mostra outra coisa."
              />
            ) : (
              <div className="space-y-2">
                {lista.map((job) => (
                  <CartaoDoJob
                    key={job.job_id}
                    job={job}
                    selecionado={jobEmFoco?.job_id === job.job_id}
                    aoSelecionar={() => setSelecionado(job.job_id)}
                  />
                ))}
              </div>
            )}
          </section>

          {jobEmFoco ? (
            <InspetorDoJob
              job={jobEmFoco}
              controlPlanePronto={controlPlanePronto}
              ocupado={agir.isPending}
              erroDaAcao={agir.error}
              aoAgir={(acao, job) => {
                // ⚠️ `liberar` não fala com o mundo: ele muda `rascunho` para
                // `pronto` dentro do banco. Confirmar aqui seria cerimônia; a
                // confirmação existe onde a consequência é externa.
                if (acao.chave === 'liberar') agir.mutate({ acao, job });
                else setConfirmacao({ tipo: 'acao', acao, job });
              }}
            />
          ) : null}
        </div>
      </div>

      {confirmacao ? <DialogoDaVez
        confirmacao={confirmacao}
        ocupado={criar.isPending || agir.isPending}
        motivo={motivoDoCancelamento}
        aoMudarMotivo={setMotivoDoCancelamento}
        aoCancelar={() => setConfirmacao(null)}
        aoConfirmar={(marcado) => {
          if (confirmacao.tipo === 'criar') {
            criar.mutate(api.paraPedido(confirmacao.rascunho, marcado));
          } else {
            agir.mutate({ acao: confirmacao.acao, job: confirmacao.job });
          }
        }}
      /> : null}
    </Moldura>
  );
}

/** Escolhe qual diálogo aparece, e com que força. */
function DialogoDaVez({
  confirmacao, ocupado, motivo, aoMudarMotivo, aoConfirmar, aoCancelar,
}: {
  confirmacao: Confirmacao;
  ocupado: boolean;
  motivo: string;
  aoMudarMotivo: (v: string) => void;
  aoConfirmar: (marcado: boolean) => void;
  aoCancelar: () => void;
}) {
  if (confirmacao.tipo === 'criar') {
    const { rascunho, destino } = confirmacao;
    const agora = rascunho.modo === 'now';
    return (
      <Dialogo
        titulo={agora ? 'Publicar agora, para o público' : 'Confirmar agendamento'}
        forte={agora}
        ocupado={ocupado}
        rotuloConfirmar={agora ? 'Sim, publicar agora' : 'Agendar'}
        marcacao={agora ? {
          id: 'confirmo-publicacao-imediata',
          rotulo: 'Confirmo a publicação imediata desta peça neste canal. Entendo que ela ficará '
            + 'visível para o público e que não há desfazer que devolva quem já viu.',
        } : undefined}
        consequencia={
          <>
            <p>{MODO_CONSEQUENCIA[rascunho.modo]}</p>
            <p className="mt-2">
              <strong>Canal: </strong>
              {destino.identidade_logica} · {plataformaLegivel(destino.plataforma)}
            </p>
            {agora ? null : (
              <p className="mt-1">
                <strong>Quando: </strong>
                {horarioLocalLegivel(rascunho.horario_local, rascunho.timezone)}
              </p>
            )}
            <p className="mt-1">
              <strong>Peça: </strong>
              {idAbreviado(rascunho.peca_id)} · versão {rascunho.peca_versao}
            </p>
          </>
        }
        aoConfirmar={aoConfirmar}
        aoCancelar={aoCancelar}
      />
    );
  }

  const { acao, job } = confirmacao;
  if (acao.chave === 'cancelar') {
    return (
      <Dialogo
        titulo="Cancelar este job"
        ocupado={ocupado}
        // O banco exige motivo com pelo menos três caracteres. Bloquear aqui
        // troca um 400 vindo de constraint por um botão que diz por que não dá.
        impedido={motivo.trim().length < 3}
        rotuloConfirmar="Cancelar o job"
        consequencia={
          <p>
            O job para {job.destino?.identidade_logica} deixa de existir como intenção. Nada é
            apagado do destino — o cancelamento só vale para o que ainda não saiu daqui.
          </p>
        }
        aoConfirmar={() => aoConfirmar(false)}
        aoCancelar={aoCancelar}
      >
        <label htmlFor="motivo-cancelamento" className="block text-xs font-medium">
          Motivo (fica registrado no histórico)
          <input
            id="motivo-cancelamento"
            name="motivo-cancelamento"
            value={motivo}
            onChange={(e) => aoMudarMotivo(e.target.value)}
            className={cn(ENTRADA, 'mt-1')}
          />
        </label>
      </Dialogo>
    );
  }

  const agora = acao.chave === 'despachar' && job.modo === 'now';
  return (
    <Dialogo
      titulo={agora ? 'Publicar agora, para o público' : acao.rotulo}
      forte={agora}
      ocupado={ocupado}
      rotuloConfirmar={agora ? 'Sim, publicar agora' : acao.rotulo}
      // ⚠️ Esta caixa é um PORTÃO DE TELA, não um campo de contrato. O
      // consentimento que o banco exige (`consentimento_agora`) foi dado na
      // criação e está gravado com ator e instante; o despacho não tem campo
      // equivalente na API. Ela existe porque despachar um `now` é o instante em
      // que o post fica público, e um clique único nesse ponto é barato demais.
      marcacao={agora ? {
        id: 'confirmo-despacho-imediato',
        rotulo: 'Confirmo que este post deve ir ao ar agora, neste canal.',
      } : undefined}
      consequencia={
        <>
          <p>
            {acao.chave === 'reconciliar'
              ? 'Pergunta ao destino o que aconteceu com este post. Não publica, não reenvia e não '
                + 'apaga: se o destino não devolver o post, o job continua exatamente onde está.'
              : MODO_CONSEQUENCIA[String(job.modo)] ?? 'Este ato fala com o destino.'}
          </p>
          <p className="mt-2">
            <strong>Canal: </strong>
            {job.destino?.identidade_logica} · {plataformaLegivel(job.destino?.plataforma)}
          </p>
          <p className="mt-1">
            <strong>Peça: </strong>{revisaoLegivel(job.peca)}
          </p>
        </>
      }
      aoConfirmar={aoConfirmar}
      aoCancelar={aoCancelar}
    />
  );
}

export default PublicacaoOrganicaContent;
