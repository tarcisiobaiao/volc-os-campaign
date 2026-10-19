/**
 * BiaWidget — o chat da Bia dentro do Layout autenticado.
 *
 * Apresentação apenas: o estado vem de `useBia`/`useAnexos`/`useComandos`; a
 * autorização é do servidor.
 *
 * Forma: no desktop, painel ancorado à direita, NÃO modal (a página continua
 * usável e a rolagem dela não muda); minimizar esconde sem desmontar, então
 * conversa, rascunho, anexos e posição de leitura voltam como estavam. No
 * celular, tela cheia modal, com áreas seguras e altura do viewport visual
 * (o teclado não cobre o compositor).
 *
 * Acessibilidade: o lançador é um botão com nome; ao abrir, o foco vai ao
 * compositor; ao minimizar, volta ao lançador; Esc fecha a camada certa
 * (paleta → lista de conversas → painel); o histórico é `role="log"`; mudanças
 * de estado do envio vão para uma região `status` própria, curta, sem
 * reanunciar a conversa.
 */
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { Skeleton } from '@/components/ui/skeleton';
import { useIsMobile } from '@/hooks/useIsMobile';
import { cn } from '@/lib/utils';

import { biaApi, type BiaApi } from './api';
import { Compositor } from './componentes/Compositor';
import { ListaDeConversas } from './componentes/Conversas';
import { Nota, Turno } from './componentes/Historico';
import { ICONES_BIA } from './icones';
import type { ExecucaoDaBia } from './tipos';
import { useAnexos } from './useAnexos';
import { useBia, type NotaLocal } from './useBia';
import { useComandos } from './useComandos';

export const AVISO_MODO_CONSULTA = 'Bia em modo de consulta — nenhuma ação operacional será executada.';
/** A mesma Bia do Telegram (profile `default`), em sessão separada. */
export const AVISO_MEMORIA_COMPARTILHADA =
  'É a mesma Bia do Telegram: mesma identidade e memória longa. Esta conversa é uma sessão separada; o que for dito aqui pode ser lembrado lá.';
/** Versão de uma linha, para a faixa fixa; a frase inteira aparece no estado vazio. */
export const AVISO_MEMORIA_CURTO = 'Mesma Bia e memória do Telegram, em sessão separada.';

const SUGESTOES = [
  'O que você consegue fazer por aqui?',
  'Resuma os pontos principais do arquivo que vou anexar.',
  'Compare os criativos destas imagens e diga qual é mais claro.',
];

interface Props {
  userId: string;
  /** Só para testes: troca o cliente HTTP. */
  api?: BiaApi;
}

type Item = { tipo: 'turno'; t: number; e: ExecucaoDaBia } | { tipo: 'nota'; t: number; n: NotaLocal };

/** Altura e topo do viewport visual (celular com teclado aberto). */
function useViewportVisual(ativo: boolean) {
  const [vv, setVv] = useState<{ altura: number; topo: number } | null>(null);
  useEffect(() => {
    const v = typeof window !== 'undefined' ? window.visualViewport : null;
    if (!ativo || !v) {
      setVv(null);
      return;
    }
    const medir = () => setVv({ altura: v.height, topo: v.offsetTop });
    medir();
    v.addEventListener('resize', medir);
    v.addEventListener('scroll', medir);
    return () => {
      v.removeEventListener('resize', medir);
      v.removeEventListener('scroll', medir);
    };
  }, [ativo]);
  return vv;
}

/** Atraso antes de mostrar o esqueleto: carga rápida não pisca. */
function useAtrasado(valor: boolean, ms = 300) {
  const [mostrar, setMostrar] = useState(false);
  useEffect(() => {
    if (!valor) {
      setMostrar(false);
      return;
    }
    const t = setTimeout(() => setMostrar(true), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return mostrar;
}

export const BiaWidget: React.FC<Props> = ({ userId, api }) => {
  const isMobile = useIsMobile();
  const [aberto, setAberto] = useState(false);
  const [jaAbriu, setJaAbriu] = useState(false);
  const [vista, setVista] = useState<'chat' | 'conversas'>('chat');
  const [arrastando, setArrastando] = useState(false);
  const [noFim, setNoFim] = useState(true);
  const lancador = useRef<HTMLButtonElement>(null);
  const painel = useRef<HTMLElement>(null);
  const rolagem = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);
  const montadoEm = useRef(Date.now());
  const ids = { titulo: useId(), aviso: useId() };

  const bia = useBia(userId, api);
  const anexos = useAnexos(api);
  const comandos = useComandos(api);
  const vv = useViewportVisual(aberto && isMobile);
  const mostrarEsqueleto = useAtrasado(bia.carregando);

  // Sugestão ou "reaproveitar o texto": vai para o compositor, nunca direto ao envio.
  const [preenchimento, setPreenchimento] = useState<{ texto: string; n: number } | null>(null);
  const preencher = (texto: string) => setPreenchimento((p) => ({ texto, n: (p?.n ?? 0) + 1 }));

  const abrir = () => {
    setAberto(true);
    setJaAbriu(true);
  };

  const fechar = useCallback(() => {
    setAberto(false);
    setVista('chat');
    // Devolve o foco a quem abriu: sem isso, quem navega por teclado cai no topo da página.
    requestAnimationFrame(() => lancador.current?.focus());
  }, []);

  // Foco no compositor ao abrir (e ao voltar da lista de conversas).
  useEffect(() => {
    if (!aberto || vista !== 'chat') return;
    requestAnimationFrame(() => {
      const el = campo.current;
      if (!el) return;
      el.focus();
      // Rascunho restaurado: o cursor vai para o fim, não para o começo.
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [aberto, vista]);

  // Celular: o painel é modal; a página atrás não rola.
  useEffect(() => {
    if (!aberto || !isMobile) return;
    const anterior = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    return () => {
      document.documentElement.style.overflow = anterior;
    };
  }, [aberto, isMobile]);

  const itens = useMemo<Item[]>(() => {
    const lista: Item[] = [
      ...bia.execucoes.map((e) => ({ tipo: 'turno' as const, t: Date.parse(e.criada_em) || 0, e })),
      ...bia.notas.map((n) => ({ tipo: 'nota' as const, t: Date.parse(n.criada_em) || 0, n })),
    ];
    return lista.sort((a, b) => a.t - b.t);
  }, [bia.execucoes, bia.notas]);

  // Rolagem presa ao fim só enquanto o operador está no fim (não puxa quem está relendo).
  const tamanhoDoConteudo = itens.length + Object.values(bia.parciais).reduce((s, p) => s + p.length, 0);
  const noFimRef = useRef(true);
  noFimRef.current = noFim;
  useEffect(() => {
    const el = rolagem.current;
    if (el && noFim) el.scrollTop = el.scrollHeight;
  }, [tamanhoDoConteudo, noFim, aberto, vista]);
  // Conteúdo que cresce depois de renderizar (miniatura, fonte, tabela) também mantém o fim à vista.
  useEffect(() => {
    const el = rolagem.current;
    const conteudo = el?.firstElementChild;
    if (!el || !conteudo || typeof ResizeObserver === 'undefined') return;
    const obs = new ResizeObserver(() => {
      if (noFimRef.current) el.scrollTop = el.scrollHeight;
    });
    obs.observe(conteudo);
    obs.observe(el); // o compositor cresce (anexos, texto longo) e a área visível encolhe
    return () => obs.disconnect();
  }, [aberto, vista, bia.carregando, itens.length === 0]);

  const aoRolar = () => {
    const el = rolagem.current;
    if (el) setNoFim(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
  };

  const irParaOFim = () => {
    const el = rolagem.current;
    if (el) el.scrollTop = el.scrollHeight;
    setNoFim(true);
  };

  const abrirConversas = () => {
    setVista('conversas');
    void bia.carregarConversas();
  };

  const novaConversa = async () => {
    setVista('chat');
    setNoFim(true);
    await bia.novaConversa();
  };

  // Estado anunciado: só o envio mais recente, e só se nasceu nesta visita.
  const ultima = bia.execucoes[bia.execucoes.length - 1];
  const anuncio = (() => {
    if (!ultima || (Date.parse(ultima.criada_em) || 0) < montadoEm.current - 5000) return '';
    switch (ultima.estado) {
      case 'queued': return 'Mensagem na fila.';
      case 'running': return bia.parciais[ultima.id] ? 'Bia está digitando.' : 'Bia está preparando a resposta.';
      case 'succeeded': return 'Resposta da Bia recebida.';
      case 'failed': return 'A Bia não conseguiu responder.';
      case 'uncertain': return 'Resultado incerto. Nada será reenviado.';
      default: return '';
    }
  })();

  const rotuloDoEstado = !bia.online
    ? 'Sem conexão'
    : ultima?.estado === 'queued'
      ? 'Mensagem na fila'
      : ultima?.estado === 'running'
        ? bia.parciais[ultima.id] ? 'Digitando…' : 'Preparando a resposta…'
        : bia.servico && !bia.servico.motor_configurado
          ? 'Hermes não configurado'
          : bia.servico
            ? 'Modo consulta'
            : bia.erro
              ? 'Indisponível'
              : 'Conectando…';
  const ocupada = bia.emAndamento;

  const aoTeclarNoPainel = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      if (vista === 'conversas') setVista('chat');
      else fechar();
      return;
    }
    // Celular: modal de verdade — o Tab não sai do painel.
    if (e.key === 'Tab' && isMobile && painel.current) {
      const focaveis = Array.from(
        painel.current.querySelectorAll<HTMLElement>('button:not([disabled]), textarea, select, a[href], [tabindex="0"]'),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (!focaveis.length) return;
      const primeiro = focaveis[0];
      const ultimo = focaveis[focaveis.length - 1];
      if (e.shiftKey && document.activeElement === primeiro) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && document.activeElement === ultimo) {
        e.preventDefault();
        primeiro.focus();
      }
    }
  };

  const temArquivos = (e: React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files');

  return (
    <>
      {!aberto ? (
        <Button
          ref={lancador}
          type="button"
          onClick={abrir}
          aria-haspopup="dialog"
          aria-label={ocupada ? 'Abrir a Bia (respondendo)' : 'Abrir a Bia'}
          className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-[40] h-11 gap-2 rounded-full pl-3.5 pr-4 shadow-elevated"
        >
          <Icone icon={ICONES_BIA.lancador} />
          <span className="font-display">Bia</span>
          {ocupada ? <span aria-hidden="true" className="h-2 w-2 rounded-full bg-white/90" /> : null}
        </Button>
      ) : null}

      {jaAbriu ? (
        <section
          ref={painel}
          role="dialog"
          aria-modal={isMobile ? true : undefined}
          aria-labelledby={ids.titulo}
          aria-describedby={ids.aviso}
          hidden={!aberto}
          onKeyDown={aoTeclarNoPainel}
          onDragEnter={(e) => {
            if (temArquivos(e)) {
              e.preventDefault();
              setArrastando(true);
            }
          }}
          onDragOver={(e) => {
            if (temArquivos(e)) {
              e.preventDefault();
              e.dataTransfer.dropEffect = 'copy';
            }
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setArrastando(false);
          }}
          onDrop={(e) => {
            if (!temArquivos(e)) return;
            e.preventDefault();
            setArrastando(false);
            setVista('chat');
            anexos.adicionar(Array.from(e.dataTransfer.files));
          }}
          style={{
            display: aberto ? undefined : 'none',
            ...(isMobile && vv ? { height: vv.altura, top: vv.topo } : {}),
          }}
          className={cn(
            'fixed z-[50] flex flex-col overflow-hidden bg-card text-foreground',
            'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-200',
            isMobile
              ? 'inset-x-0 top-0 h-[100dvh] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] pt-[env(safe-area-inset-top)]'
              : 'bottom-4 right-4 h-[min(720px,calc(100dvh-2rem))] w-[min(440px,calc(100vw-2rem))] rounded-[14px] border border-border shadow-modal motion-safe:slide-in-from-bottom-2',
          )}
        >
          {/* Cabeçalho */}
          <header className="flex items-center gap-1 border-b border-border py-2 pl-4 pr-2">
            {vista === 'conversas' ? (
              <Button type="button" variant="ghost" size="icon" className="touch-target -ml-2 h-10 w-10" onClick={() => setVista('chat')}>
                <Icone icon={ICONES_BIA.voltar} rotulo="Voltar para a conversa" />
              </Button>
            ) : null}
            <div className="min-w-0 flex-1">
              <h2 id={ids.titulo} className="font-display text-base font-semibold leading-tight text-foreground">
                {vista === 'conversas' ? 'Conversas' : 'Bia'}
              </h2>
              {vista === 'chat' ? (
                <p className="flex items-center gap-1.5 truncate text-micro font-normal tracking-normal text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className={cn(
                      'h-1.5 w-1.5 shrink-0 rounded-full',
                      !bia.online || (bia.erro && !bia.servico) ? 'bg-destructive' : ocupada ? 'bg-primary' : 'bg-success',
                    )}
                  />
                  {rotuloDoEstado}
                </p>
              ) : null}
            </div>
            {vista === 'chat' ? (
              <Button type="button" variant="ghost" size="icon" className="touch-target h-10 w-10" onClick={abrirConversas}>
                <Icone icon={ICONES_BIA.conversas} rotulo="Conversas recentes" />
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="touch-target h-10 w-10"
              onClick={() => void novaConversa()}
              disabled={bia.enviando}
            >
              <Icone icon={ICONES_BIA.novaConversa} rotulo="Nova conversa" />
            </Button>
            <Button type="button" variant="ghost" size="icon" className="touch-target h-10 w-10" onClick={fechar}>
              <Icone
                icon={isMobile ? ICONES_BIA.fechar : ICONES_BIA.minimizar}
                rotulo={isMobile ? 'Fechar a Bia' : 'Minimizar a Bia'}
              />
            </Button>
          </header>

          {/* Aviso de modo — curto, sempre visível, sem tomar a conversa */}
          <div id={ids.aviso} className="border-b border-border bg-muted/60 px-4 py-1.5 text-micro font-normal tracking-normal text-muted-foreground">
            <p>
              <span className="font-medium text-foreground">{AVISO_MODO_CONSULTA}</span>{' '}
              <span>{AVISO_MEMORIA_CURTO}</span>
            </p>
          </div>

          {vista === 'conversas' ? (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <ListaDeConversas
                conversas={bia.conversas}
                atual={bia.conversaId}
                onAbrir={(id) => {
                  setVista('chat');
                  setNoFim(true);
                  void bia.trocarConversa(id);
                }}
              />
            </div>
          ) : (
            <>
              <div className="relative min-h-0 flex-1">
                <div ref={rolagem} onScroll={aoRolar} className="h-full overflow-y-auto overscroll-contain px-4 py-4">
                  {bia.carregando ? (
                    mostrarEsqueleto ? (
                      <div role="status" aria-label="Carregando a conversa" className="space-y-5">
                        <Skeleton className="ml-auto h-10 w-2/3 rounded-[10px]" />
                        <div className="space-y-2">
                          <Skeleton className="h-3 w-16" />
                          <Skeleton className="h-4 w-full" />
                          <Skeleton className="h-4 w-5/6" />
                        </div>
                        <Skeleton className="ml-auto h-10 w-1/2 rounded-[10px]" />
                      </div>
                    ) : null
                  ) : itens.length === 0 ? (
                    <div className="flex h-full flex-col justify-end gap-4 pb-2">
                      <div>
                        <p className="font-display text-lg font-semibold text-foreground">Converse com a Bia</p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Pergunte, anexe imagens ou documentos (PDF, TXT, CSV, DOCX) e use
                          <span className="font-data text-foreground"> / </span>para comandos. Ela lê e responde;
                          não executa ações.
                        </p>
                        <p className="mt-2 text-denso text-muted-foreground">
                          {bia.servico?.memoria?.aviso ?? AVISO_MEMORIA_COMPARTILHADA}
                        </p>
                      </div>
                      <ul aria-label="Sugestões" className="flex flex-col items-start gap-1.5">
                        {SUGESTOES.map((s) => (
                          <li key={s}>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-auto min-h-11 whitespace-normal rounded-[10px] py-2 text-left font-normal"
                              onClick={() => preencher(s)}
                            >
                              {s}
                            </Button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <ol role="log" aria-label="Conversa com a Bia" aria-relevant="additions" className="space-y-5">
                      {itens.map((it) =>
                        it.tipo === 'turno' ? (
                          <Turno
                            key={it.e.id}
                            e={it.e}
                            parcial={bia.parciais[it.e.id]}
                            api={api ?? biaApi}
                            onVerificar={(id) => void bia.verificar(id)}
                            onNovaConversa={() => void novaConversa()}
                            onReusar={preencher}
                          />
                        ) : (
                          <Nota
                            key={it.n.id}
                            nota={it.n}
                            comandosWeb={(comandos.catalogo ?? []).filter((c) => c.origem === 'volc')}
                          />
                        ),
                      )}
                    </ol>
                  )}
                </div>
                {!noFim && itens.length ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={irParaOFim}
                    className="absolute bottom-3 left-1/2 h-9 -translate-x-1/2 gap-1.5 rounded-full shadow-card"
                  >
                    <Icone icon={ICONES_BIA.irParaOFim} tamanho="sm" />
                    Ir para o fim
                  </Button>
                ) : null}
              </div>

              {bia.erro ? (
                <div role="alert" className="mx-3 mb-2 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
                  <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="mt-0.5 text-destructive" />
                  <p className="flex-1 text-denso text-foreground">{bia.erro}</p>
                  <Button type="button" variant="ghost" size="icon" className="touch-target -my-1 h-8 w-8" onClick={bia.limparErro}>
                    <Icone icon={ICONES_BIA.fechar} tamanho="sm" rotulo="Dispensar aviso de erro" />
                  </Button>
                </div>
              ) : null}

              <Compositor
                userId={userId}
                bia={bia}
                anexos={anexos}
                comandos={comandos}
                campo={campo}
                preenchimento={preenchimento}
                onAbrirConversas={abrirConversas}
              />
            </>
          )}

          {arrastando ? (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-2 z-[2] flex items-center justify-center rounded-[10px] border-2 border-dashed border-primary bg-card/95 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150"
            >
              <p className="flex items-center gap-2 font-display text-sm font-semibold text-foreground">
                <Icone icon={ICONES_BIA.anexar} />
                Solte para anexar
              </p>
            </div>
          ) : null}

          <p role="status" aria-live="polite" className="sr-only">{anuncio}</p>
        </section>
      ) : null}
    </>
  );
};

export default BiaWidget;
