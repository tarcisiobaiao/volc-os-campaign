/**
 * A ignição — o momento em que a campanha sai da tela e entra na conta.
 *
 * ## Por que uma tela cheia e não um botão que muda de texto
 *
 * O clímax do módulo era um retângulo cinza escrito "trava fechada" numa coluna
 * de 320px. Aqui a escada ocupa a tela porque é a única coisa que importa
 * enquanto roda, e porque cada degrau tem um veredito que o operador precisa
 * ler — não um spinner que termina em "ok".
 *
 * ## Cada degrau é uma chamada de verdade
 *
 * Não há animação fingindo etapa. `prova` é `POST /provar` (o `validate_only`
 * contra a conta real, a chamada mais lenta do fluxo) e `escrita` é
 * `POST /subir`. A copy já foi escrita no estágio 3 e entra acesa, com os
 * números dela.
 *
 * ⚠️ `/provar` roda o `validate_only` e `/subir` roda DE NOVO por dentro. É
 * deliberado — o `Selo` é do payload e não da sessão, e reprovar antes de
 * escrever fecha a janela entre as duas. O preço é a chamada lenta duas vezes.
 *
 * ## O laranja só acende com recurso persistido
 *
 * `--aurora-orange` é a cor da "Primeira Faísca" do login. Aqui ela é reservada
 * ao recibo: nem a prova aprovada acende. Aprovar é preflight; existir é outra
 * coisa, e a tela não pode ensinar que são a mesma.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Loader2, Lock, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PautadorApiError, pautadorApi } from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type {
  EstadoDaTrava, PedidoDeProvaSearch, Preparo, RespostaDaProva,
} from '@/types/trafego';

type Estado = 'provando' | 'reprovada' | 'aguardando_escrita' | 'escrevendo'
  | 'criada' | 'travada' | 'fora_do_canario' | 'indeterminado' | 'erro';

interface Props {
  pedido: PedidoDeProvaSearch;
  trava: EstadoDaTrava | null;
  titulo: string;
  /** Resumo do estágio 3, já feito. A escada não escreve copy — ela mostra o
   *  que foi escrito e lido antes de alguém clicar em lançar. */
  resumoDaCopy: string;
  onFechar: () => void;
  /** O id da campanha recém-criada, tirado do recibo. É o que permite à página
   *  ler o veredito de política sem o operador copiar id à mão — e enquanto
   *  `campaigns` não é gravada no `/subir`, o recibo é a única fonte dele. */
  onCriada?: (campaignId: string) => void;
}

export const Lancamento: React.FC<Props> = ({
  pedido, trava, titulo, resumoDaCopy, onFechar, onCriada,
}) => {
  const [estado, setEstado] = useState<Estado>('provando');
  const [prova, setProva] = useState<RespostaDaProva | null>(null);
  const [preparoDaRecusa, setPreparoDaRecusa] = useState<Preparo | null>(null);
  const [recibo, setRecibo] = useState<Record<string, unknown> | null>(null);
  const [erro, setErro] = useState<string>('');
  const [motivo, setMotivo] = useState(`lançamento de "${titulo}"`);
  const [confirmouPausada, setConfirmouPausada] = useState(false);
  const [segundos, setSegundos] = useState(0);

  const painel = useRef<HTMLDivElement>(null);

  // Fechar no meio da PROVA é seguro — `validate_only` não cria nada em desfecho
  // nenhum. Fechar no meio da ESCRITA não é, e por isso ali não há saída.
  const podeFechar = estado !== 'escrevendo';

  useEffect(() => {
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [estado]);

  useEffect(() => { setSegundos(0); }, [estado]);

  // Foco no painel ao abrir: sem isso o leitor de tela continua no botão que
  // ficou atrás do overlay, e o Esc não chega aqui.
  useEffect(() => { painel.current?.focus(); }, []);

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && podeFechar) onFechar();
    };
    window.addEventListener('keydown', aoTeclar);
    return () => window.removeEventListener('keydown', aoTeclar);
  }, [podeFechar, onFechar]);

  const provar = useCallback(async () => {
    setEstado('provando');
    setErro('');
    try {
      const r = await pautadorApi.provarCampanha(pedido);
      setProva(r);
      if (!r.preparo.aprovado) {
        setPreparoDaRecusa(r.preparo);
        setEstado('reprovada');
        return;
      }
      if (!r.autorizacao.alvo_canario || !r.autorizacao.elegivel
          || !r.autorizacao.plano_impressao) {
        setEstado('fora_do_canario');
        return;
      }
      // ⚠️ `escrita_permitida` NÃO responde "posso tentar?".
      //
      // `modo.escrita_permitida()` é `_destravado_no_codigo AND env` — e
      // `_destravado_no_codigo` só é verdadeiro DENTRO do `with destravar()`,
      // que acontece lá dentro do `subir()`. Em repouso ele é sempre falso,
      // mesmo com a chave posta. Medido em 19/08/2026: o operador subiu o
      // backend com `FORGE_PERMITIR_ESCRITA=1`, o `/trava` devolveu
      // `env_presente: true, escrita_permitida: false`, e esta linha concluiu
      // "travada" — a escrita nunca seria tentada, com a chave na fechadura.
      //
      // Quem responde "o operador autorizou escrita neste processo?" é
      // `env_presente`. Quem decide de fato é o servidor, no `/subir`: se a
      // trava estiver mesmo fechada ele devolve 409 com a mensagem exata.
      setEstado(trava?.env_presente ? 'aguardando_escrita' : 'travada');
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'A prova falhou.');
      setEstado('erro');
    }
  }, [pedido, trava]);

  useEffect(() => { void provar(); }, [provar]);

  const escrever = async () => {
    const impressao = prova?.autorizacao.plano_impressao;
    if (!prova?.autorizacao.alvo_canario || !prova.autorizacao.elegivel
        || !impressao || !confirmouPausada) return;
    setEstado('escrevendo');
    try {
      const r = await pautadorApi.subirCampanha({
        ...pedido,
        carimbo_nome: prova.autorizacao.carimbo_nome,
        motivo,
        plano_impressao: impressao,
        confirmar_criacao_pausada: true,
      });
      setRecibo(r.recibo);
      // O recibo carrega o id devolvido pela API. Sem isto, o veredito exigiria
      // o operador copiar o id do JSON à mão.
      const id = (r.recibo as Record<string, unknown>)?.campaign_id
              ?? (r.recibo as Record<string, unknown>)?.campanha_id;
      if (id) onCriada?.(String(id));
      setEstado('criada');
    } catch (e) {
      // O 409 de `/subir` carrega `{mensagem, preparo}` — é o que permite dizer
      // QUAL juiz reprovou sem repetir `/provar`, que acabou de rodar.
      if (e instanceof PautadorApiError && e.corpo) {
        const c = e.corpo as { preparo?: Preparo };
        if (c.preparo) {
          setPreparoDaRecusa(c.preparo);
          setEstado('reprovada');
          return;
        }
      }
      // Status zero significa que o navegador não recebeu uma resposta. A
      // chamada pode ter chegado ao Google: oferecer reenvio aqui seria a
      // forma mais fácil de criar a campanha duas vezes.
      if (e instanceof PautadorApiError && e.status === 0) {
        setErro(e.message);
        setEstado('indeterminado');
        return;
      }
      setErro(e instanceof Error ? e.message : 'A escrita falhou.');
      setEstado('erro');
    }
  };

  const avanco = AVANCO[estado];
  const p = prova?.preparo;

  return (
    <div className="ignicao" data-estado={estado} role="dialog" aria-modal="true"
         aria-label={`Lançamento de ${titulo}`}>
      <div className="ignicao-horizonte" aria-hidden>
        <div className="ignicao-hz ignicao-hz-1" style={{ ['--avanco' as string]: avanco }} />
        <div className="ignicao-hz ignicao-hz-2" style={{ ['--avanco' as string]: avanco }} />
        <div className="ignicao-hz ignicao-hz-3" style={{ ['--avanco' as string]: avanco }} />
        <div className="ignicao-fogo" />
      </div>

      <div ref={painel} tabIndex={-1}
           className="relative z-10 mx-auto flex w-full max-w-2xl flex-col justify-center px-6 outline-none">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="kicker text-white/50">lançando</div>
            <h2 className="font-display text-2xl font-bold tracking-tight text-white md:text-3xl">
              {titulo}
            </h2>
          </div>
          {podeFechar && (
            <button type="button" onClick={onFechar} aria-label="Fechar o lançamento"
                    className="rounded-md p-2 text-white/50 transition-colors hover:bg-white/10 hover:text-white">
              <X className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>

        <div className="mt-8 space-y-1">
          <Degrau nome="copy" estado="ok" detalhe={resumoDaCopy} indice={0} />

          <Degrau
            nome="prova"
            estado={estado === 'provando' ? 'correndo'
              : estado === 'reprovada' ? 'falhou'
              : estado === 'erro' && !prova ? 'falhou' : 'ok'}
            detalhe={estado === 'provando'
              ? `validate_only contra a conta real · ${segundos}s`
              : p
                ? `${p.n_operacoes} operações · nada foi criado`
                : erro || '—'}
            indice={1}
          >
            {/* ⚠️ A AUTOCORREÇÃO APARECE MESMO QUANDO A PROVA PASSA.
                O motor tira keywords e pede isenção sozinho — e é justamente
                no SUCESSO que a mudança silenciosa engana: o operador aprovaria
                a campanha sem saber que uma keyword saiu e outra foi isentada.
                Medido no card 65 em 19/08/2026: 114 → 113 operações. */}
            {!!p?.autocorrecao?.length && (
              <ul className="mt-2 space-y-1 border-l-2 border-warning/60 pl-3">
                {p.autocorrecao.map((linha, i) => (
                  <li key={i} className="text-[11px] leading-relaxed text-white/60">
                    {linha}
                  </li>
                ))}
              </ul>
            )}
            {/* ⚠️ OS AVISOS TAMBÉM APARECEM COM A PROVA PASSANDO, e pela
                mesma razão. "a negativa 'saque' anula a keyword 'saque anual
                fgts'" não barra o lançamento — quem decide é quem revisa — e
                por isso ele só existe aqui. Sem este bloco o achado chegava no
                JSON e morria antes da tela. */}
            {!!p?.avisos_locais?.length && (
              <ul className="mt-2 space-y-1 border-l-2 border-warning/60 pl-3">
                {p.avisos_locais.map((linha, i) => (
                  <li key={i} className="text-[11px] leading-relaxed text-white/60">
                    {linha}
                  </li>
                ))}
              </ul>
            )}
            {p && (
              <div className="mt-2 space-y-1.5 border-l border-white/15 pl-3">
                {/* ⚠️ O MOTIVO VEM DE `resumo`, NÃO DA CONTAGEM DE ACHADOS.
                    `recusa_local` chega como TEXTO (`volc_ads/subir.py` monta
                    a string), então `achados` é sempre vazio e este rótulo
                    dizia "0 achado(s)" — um veredito de reprovação sem uma
                    linha do que consertar. Medido no card 65 em 19/08/2026: a
                    recusa real era "Exige certificacao_servicos_oficiais
                    (política 15332527)", e o operador via um zero. */}
                <Juiz nome="forma" ok={!p.recusa_local || p.recusa_local.ok}
                      detalhe={p.recusa_local && !p.recusa_local.ok
                        ? (p.recusa_local.achados.length
                            ? `${p.recusa_local.achados.length} achado(s)`
                            : 'veja o motivo abaixo')
                        : 'determinístico, local'} />
                {/* ⚠️ NÃO EXISTE JUIZ QUE PASSA SEM TER SIDO CHAMADO.
                    `falha_validacao` é `null` em DOIS casos opostos: o Google
                    aprovou, ou a prova parou antes e ele nunca foi consultado.
                    Tratar os dois como "passou" pintava de verde um juiz que
                    não rodou — foi o que a tela fez no card 65, mostrando
                    "google · passou" numa prova de ZERO operações, onde não
                    havia payload para validar. */}
                <Juiz nome="google"
                      ok={!p.falha_validacao && p.n_operacoes > 0}
                      detalhe={p.falha_validacao
                        ? p.falha_validacao.classe ?? 'recusado'
                        : p.n_operacoes > 0
                          ? 'o payload passou'
                          : 'não foi consultado — a forma reprovou antes'} />
              </div>
            )}
            {/* O texto da recusa local, por extenso. É ele que diz o que
                consertar, e sem ele a tela só sabe dizer que reprovou. */}
            {p?.recusa_local && !p.recusa_local.ok && p.recusa_local.resumo && (
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words
                              border-l-2 border-destructive/60 pl-3 text-[11px]
                              leading-relaxed text-white/70">
                {p.recusa_local.resumo}
              </pre>
            )}
          </Degrau>

          <Degrau
            nome="escrita"
            estado={estado === 'criada' ? 'ok'
              : estado === 'escrevendo' ? 'correndo'
              : estado === 'travada' ? 'travado'
              : estado === 'fora_do_canario' ? 'travado'
              : estado === 'indeterminado' ? 'travado'
              : estado === 'reprovada' || estado === 'erro' ? 'parado' : 'espera'}
            detalhe={
              estado === 'criada' ? 'a campanha existe, pausada'
              : estado === 'escrevendo' ? `mutate atômico · ${segundos}s`
              : estado === 'travada' ? 'trava de escrita fechada'
              : estado === 'fora_do_canario' ? 'fora da janela do canário'
              : estado === 'indeterminado' ? 'sem resposta — não reenviar'
              : estado === 'reprovada' ? 'não chegou aqui — nada foi enviado'
              : 'nasce PAUSADA'
            }
            indice={2}
          />
        </div>

        <div className="mt-8">
          {estado === 'reprovada' && preparoDaRecusa && (
            <Recusa p={preparoDaRecusa} />
          )}

          {estado === 'travada' && (
            <Aviso icone={<Lock className="h-4 w-4" aria-hidden />}
                   titulo="O payload passou. A trava de escrita está fechada.">
              {trava?.explicacao ?? 'A trava é de dois fatores, de propósito.'}
              {' '}Nada foi criado, e nada será até alguém abri-la no servidor.
            </Aviso>
          )}

          {estado === 'fora_do_canario' && prova && (
            <Aviso icone={<Lock className="h-4 w-4" aria-hidden />}
                   titulo="A prova passou, mas o pedido está fora da janela do canário.">
              A primeira criação real está restrita a{' '}
              <strong>{prova.autorizacao.politica.customer_label}</strong>{' '}
              ({prova.autorizacao.politica.customer_id_formatado}). Nada foi criado.
              {!prova.autorizacao.elegivel && (
                <> Motivo: {prova.autorizacao.motivo_elegibilidade}</>
              )}
            </Aviso>
          )}

          {estado === 'aguardando_escrita' && (
            <div className="rounded-lg border border-white/15 bg-white/[0.04] p-4">
              <div className="mb-4 rounded-md border border-white/10 bg-black/20 p-3 text-[11px] text-white/65">
                <div className="kicker text-white/45">canário autorizado</div>
                <p className="mt-1 text-sm font-medium text-white">
                  {prova?.autorizacao.politica.customer_label} ·{' '}
                  {prova?.autorizacao.politica.customer_id_formatado}
                </p>
                <p className="mt-1">
                  Search · orçamento R$ {Number(prova?.autorizacao.budget_diario ?? 0).toFixed(2)} / dia
                  {' '}· CPC R$ {Number(prova?.autorizacao.cpc_inicial ?? 0).toFixed(2)}
                </p>
                <p className="mt-1 font-medium text-white">
                  Cria PAUSADA. Esta autorização não ativa nem começa a gastar.
                </p>
              </div>
              <label className="block">
                <span className="kicker text-white/60">por que está subindo</span>
                <Input value={motivo} onChange={(e) => setMotivo(e.target.value)}
                       className="mt-1.5 h-9 border-white/20 bg-white/5 text-sm text-white" />
              </label>
              {/* O motivo vai para o RECIBO. `subir()` recusa menos de 10
                  caracteres, e a razão está no cabeçalho dele: recibo sem
                  motivo é um gasto que ninguém sabe explicar depois. */}
              <p className="mt-1.5 text-[11px] leading-relaxed text-white/45">
                Vai no recibo. É o que responde "por que gastamos isto?" daqui a
                três meses.
              </p>
              <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-md border border-white/10 p-3 text-[11px] leading-relaxed text-white/70">
                <input type="checkbox" checked={confirmouPausada}
                       onChange={(e) => setConfirmouPausada(e.target.checked)}
                       className="mt-0.5 h-4 w-4 accent-white" />
                <span>
                  Confirmo o plano acima e autorizo somente a criação PAUSADA
                  na conta-laboratório. Ativação será uma decisão separada.
                </span>
              </label>
              <Button onClick={escrever}
                      disabled={motivo.trim().length < 10 || !confirmouPausada}
                      className="mt-3 w-full">
                Criar campanha pausada
              </Button>
            </div>
          )}

          {estado === 'criada' && recibo && <Recibo r={recibo} />}

          {estado === 'erro' && (
            <Aviso icone={<AlertTriangle className="h-4 w-4" aria-hidden />}
                   titulo="Não deu para concluir">
              {erro}
            </Aviso>
          )}

          {estado === 'indeterminado' && (
            <Aviso icone={<AlertTriangle className="h-4 w-4" aria-hidden />}
                   titulo="A resposta se perdeu. Não reenvie.">
              A campanha pode ter sido criada. Atualize o inventário da conta
              Portal Mundo Mais e procure a marca VOLC-CANARY antes de decidir
              qualquer nova tentativa. {erro}
            </Aviso>
          )}
        </div>

        {(estado === 'reprovada' || estado === 'erro' || estado === 'fora_do_canario') && (
          <Button variant="outline" onClick={onFechar}
                  className="mt-4 w-full border-white/20 bg-transparent text-white hover:bg-white/10">
            Voltar e ajustar
          </Button>
        )}
      </div>

      <p className="relative z-10 pb-6 text-center text-[11px] text-white/35">
        {estado === 'escrevendo'
          ? 'não feche esta tela — a escrita está em curso'
          : 'esc fecha'}
      </p>
    </div>
  );
};

/** Quanto o horizonte já subiu. Estado, não tempo: um degrau resolvido acende
 *  mais que um degrau demorando. */
const AVANCO: Record<Estado, number> = {
  provando: 0.15,
  reprovada: 0.1,
  travada: 0.55,
  fora_do_canario: 0.55,
  aguardando_escrita: 0.7,
  escrevendo: 0.85,
  criada: 1,
  indeterminado: 0.85,
  erro: 0.1,
};

type EstadoDoDegrau = 'espera' | 'correndo' | 'ok' | 'falhou' | 'travado' | 'parado';

const Degrau: React.FC<{
  nome: string; estado: EstadoDoDegrau; detalhe: string; indice: number;
  children?: React.ReactNode;
}> = ({ nome, estado, detalhe, indice, children }) => (
  <div className="reveal flex items-start gap-3 py-2" style={{ ['--i' as string]: indice }}>
    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden>
      {estado === 'ok' && <Check className="h-4 w-4 text-white" />}
      {estado === 'correndo' && <Loader2 className="h-4 w-4 animate-spin text-white" />}
      {estado === 'falhou' && <X className="h-4 w-4 text-destructive" />}
      {estado === 'travado' && <Lock className="h-3.5 w-3.5 text-white/70" />}
      {(estado === 'espera' || estado === 'parado') && (
        <span className="h-1.5 w-1.5 rounded-full bg-white/25" />
      )}
    </span>
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-baseline gap-x-3">
        {/* Estado por PALAVRA e por glifo, nunca só por cor. */}
        <span className={cn('text-sm font-medium',
                            estado === 'espera' || estado === 'parado'
                              ? 'text-white/40' : 'text-white')}>
          {nome}
        </span>
        <span className="text-[11px] text-white/45">{detalhe}</span>
      </div>
      {children}
    </div>
  </div>
);

const Juiz: React.FC<{ nome: string; ok: boolean; detalhe: string }> = ({ nome, ok, detalhe }) => (
  <div className="flex items-baseline gap-2 text-[11px]">
    {ok ? <Check className="h-3 w-3 shrink-0 text-white/70" aria-hidden />
        : <X className="h-3 w-3 shrink-0 text-destructive" aria-hidden />}
    <span className="kicker text-white/55">{nome}</span>
    <span className={ok ? 'text-white/70' : 'text-destructive'}>
      {ok ? 'passou' : 'reprovou'}
    </span>
    <span className="text-white/40">{detalhe}</span>
  </div>
);

/** O valor está em QUAL juiz reprovou e no quê. "Não foi possível" obrigaria o
 *  operador a adivinhar o que consertar — o defeito do flow n8n de volta. */
const Recusa: React.FC<{ p: Preparo }> = ({ p }) => (
  <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
    <p className="text-sm font-medium text-white">Nada foi enviado.</p>
    <ul className="mt-2 space-y-1.5">
      {p.recusa_local?.achados?.slice(0, 6).map((a, i) => (
        <li key={`l${i}`} className="text-[11px] leading-relaxed text-white/70">
          <span className="kicker text-destructive">{a.campo}</span> {a.motivo}
        </li>
      ))}
      {/* ⚠️ A MENSAGEM DO GOOGLE NÃO DIZ NADA — o detalhe é que diz.
          "A policy was violated. See PolicyViolationDetails for more detail."
          é o texto genérico da API, e ela mesma manda olhar o detalhe. Medido
          no card 65 em 19/08/2026: a tela repetiu essa frase DUAS vezes,
          enquanto o payload trazia `NON_FAMILY_SAFE('como sacar o fgts na
          caixa')` e `PERSONAL_LOANS('saldo bloqueado fgts empréstimo como
          desbloquear')` — as duas com `isentavel=true`.

          O que importa aqui é o GATILHO (o texto exato que violou) e se há
          caminho de volta. Sem os dois, "reprovado" é um beco. */}
      {p.falha_validacao?.erros?.slice(0, 6).map((e, i) => (
        <li key={`g${i}`} className="text-[11px] leading-relaxed text-white/70">
          <span className="kicker text-destructive">
            {e.politica?.chave?.policy_name || e.codigo}
          </span>{' '}
          {e.gatilho
            ? <span className="text-white">“{e.gatilho}”</span>
            : e.mensagem}
          {/* O índice diz QUAL das ~114 operações violou. Sem ele, sabe-se que
              algo violou e não o quê. */}
          {e.indice != null && (
            <span className="tabular text-white/40"> · operação [{e.indice}]</span>
          )}
          {e.politica?.isentavel === true && (
            <span className="text-white/50"> · comporta pedido de isenção</span>
          )}
          {e.politica?.isentavel === false && (
            <span className="text-white/50"> · não é isentável — tem de sair</span>
          )}
          {e.caminho && (
            <div className="mt-0.5 break-all font-mono text-[10px] text-white/30">
              {e.caminho}
            </div>
          )}
        </li>
      ))}
    </ul>
  </div>
);

const Recibo: React.FC<{ r: Record<string, unknown> }> = ({ r }) => {
  const criados = (r.criados as { tipo: string; resource_name: string }[]) ?? [];
  return (
    <div className="rounded-lg border border-white/20 bg-white/[0.06] p-4">
      <p className="font-display text-lg font-bold text-white">
        A campanha existe, e está pausada.
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-white/60">
        Nascer pausada é o que faz o primeiro disparo custar zero e ainda assim
        produzir o veredito real de política do Google sobre recurso persistido —
        a única coisa que o <span className="font-mono">validate_only</span> não dá.
      </p>
      <dl className="mt-3 space-y-1 text-[11px]">
        <Linha rotulo="campanha" valor={String(r.nome_campanha ?? '—')} />
        <Linha rotulo="conta" valor={String(r.customer_id ?? '—')} />
        <Linha rotulo="recursos criados" valor={String(criados.length || r.n_operacoes || '—')} />
        <Linha rotulo="request id" valor={String(r.request_id ?? '—')} />
      </dl>
    </div>
  );
};

const Linha: React.FC<{ rotulo: string; valor: string }> = ({ rotulo, valor }) => (
  <div className="flex justify-between gap-4">
    <dt className="kicker text-white/45">{rotulo}</dt>
    <dd className="tabular truncate text-white/80">{valor}</dd>
  </div>
);

const Aviso: React.FC<{ icone: React.ReactNode; titulo: string; children: React.ReactNode }> =
  ({ icone, titulo, children }) => (
  <div className="flex items-start gap-3 rounded-lg border border-white/20 bg-white/[0.04] p-4">
    <span className="mt-0.5 shrink-0 text-white/60">{icone}</span>
    <div className="min-w-0">
      <p className="text-sm font-medium text-white">{titulo}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-white/55">{children}</p>
    </div>
  </div>
);
