/**
 * BiaWidget — conversa de consulta com a Bia, dentro do Layout autenticado.
 *
 * Apresentação apenas: o estado vem de `useBia`, a autorização é do servidor.
 * Texto do usuário e da Bia é renderizado como TEXTO (nunca HTML, nunca
 * Markdown com HTML): a resposta é de um modelo e pode conter qualquer coisa.
 *
 * Acessibilidade: o lançador é um botão com nome; o painel é um diálogo
 * rotulado (modal no celular, onde cobre a tela); o foco entra no campo ao
 * abrir e volta ao lançador ao fechar; Esc fecha; o histórico é uma região
 * `log` com `aria-live="polite"`; erros vão para `role="alert"` com texto, não
 * só cor; alvos de toque ≥ 44px.
 */
import React, { useEffect, useId, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { Textarea } from '@/components/ui/textarea';
import { useIsMobile } from '@/hooks/useIsMobile';
import { ICONES } from '@/lib/icones';
import { cn } from '@/lib/utils';

import type { BiaApi } from './api';
import type { EstadoDaExecucao, ExecucaoDaBia, JanelaDeContexto } from './tipos';
import { useBia } from './useBia';

export const AVISO_MODO_CONSULTA = 'Bia em modo de consulta — nenhuma ação operacional será executada.';
/** A mesma Bia do Telegram (profile `default`), em sessão separada. */
export const AVISO_MEMORIA_COMPARTILHADA =
  'É a mesma Bia do Telegram: mesma identidade e memória longa. Esta conversa é uma sessão separada; o que for dito aqui pode ser lembrado lá.';

const ROTULO_DO_ESTADO: Record<EstadoDaExecucao, string> = {
  queued: 'Na fila',
  running: 'Processando',
  succeeded: 'Respondida',
  failed: 'Falhou',
  uncertain: 'Resultado incerto',
  cancelled: 'Cancelada',
};

const COR_DO_ESTADO: Record<EstadoDaExecucao, string> = {
  queued: 'text-muted-foreground',
  running: 'text-muted-foreground',
  succeeded: 'text-muted-foreground',
  failed: 'text-destructive',
  uncertain: 'text-amber-700 dark:text-amber-400',
  cancelled: 'text-muted-foreground',
};

const PADRAO_REF = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;

interface Props {
  userId: string;
  /** Só para testes: troca o cliente HTTP. */
  api?: BiaApi;
}

const Turno: React.FC<{ e: ExecucaoDaBia; onVerificar: (id: string) => void }> = ({ e, onVerificar }) => (
  <li className="space-y-2">
    <div className="ml-8 rounded-lg bg-muted px-3 py-2">
      <p className="sr-only">Você:</p>
      <p className="whitespace-pre-wrap break-words text-sm text-foreground">{e.entrada}</p>
      {e.contexto ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Contexto: campanha {e.contexto.campaign_ref} · {e.contexto.janela.replace(/_/g, ' ')}
        </p>
      ) : null}
    </div>
    <div className="mr-8 rounded-lg border border-border bg-card px-3 py-2">
      <p className="sr-only">Bia:</p>
      {e.resposta ? (
        <p className="whitespace-pre-wrap break-words text-sm text-foreground">{e.resposta}</p>
      ) : null}
      <p className={cn('text-xs', COR_DO_ESTADO[e.estado])}>
        <span className="font-medium">{ROTULO_DO_ESTADO[e.estado]}</span>
        {e.erro?.mensagem ? <> · {e.erro.mensagem}</> : null}
      </p>
      {e.estado === 'uncertain' ? (
        <div className="mt-2 space-y-1">
          <p className="text-xs text-muted-foreground">
            Nada é reenviado automaticamente. Verifique se a resposta chegou ao Hermes ou abra uma
            nova conversa.
          </p>
          <Button type="button" variant="outline" size="sm" className="min-h-11"
                  onClick={() => onVerificar(e.id)}>
            Verificar resposta
          </Button>
        </div>
      ) : null}
    </div>
  </li>
);

export const BiaWidget: React.FC<Props> = ({ userId, api }) => {
  const isMobile = useIsMobile();
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState('');
  const [comContexto, setComContexto] = useState(false);
  const [campanha, setCampanha] = useState('');
  const [janela, setJanela] = useState<JanelaDeContexto>('ultimos_7_dias');
  const lancador = useRef<HTMLButtonElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);
  const fimDoLog = useRef<HTMLLIElement>(null);
  const ids = { titulo: useId(), aviso: useId(), campo: useId(), contador: useId(), campanha: useId(), janela: useId() };
  const bia = useBia(userId, api);

  const limite = bia.servico?.limites.max_caracteres ?? 4000;
  const refValida = !comContexto || PADRAO_REF.test(campanha.trim());
  const podeEnviar =
    !!bia.conversaId && !bia.enviando && !bia.bloqueada && !bia.emAndamento &&
    texto.trim().length > 0 && texto.length <= limite && refValida;

  useEffect(() => {
    if (aberto) campo.current?.focus();
  }, [aberto]);

  useEffect(() => {
    fimDoLog.current?.scrollIntoView?.({ block: 'end' });
  }, [bia.execucoes.length, aberto]);

  const fechar = () => {
    setAberto(false);
    // Devolve o foco a quem abriu: sem isso, quem navega por teclado cai no topo da página.
    requestAnimationFrame(() => lancador.current?.focus());
  };

  const enviar = async () => {
    if (!podeEnviar) return;
    const contexto = comContexto ? { campaign_ref: campanha.trim(), janela } : undefined;
    const ok = await bia.enviar(texto, contexto);
    if (ok) setTexto('');
  };

  const aoTeclar = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void enviar();
    }
  };

  return (
    <>
      {!aberto ? (
        <Button
          ref={lancador}
          type="button"
          onClick={() => setAberto(true)}
          aria-haspopup="dialog"
          className="fixed bottom-4 right-4 z-[40] min-h-11 rounded-full px-5 shadow-card motion-safe:transition-transform motion-safe:hover:-translate-y-0.5"
        >
          Bia
        </Button>
      ) : null}

      {aberto ? (
        <section
          role="dialog"
          aria-modal={isMobile ? true : undefined}
          aria-labelledby={ids.titulo}
          aria-describedby={ids.aviso}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.stopPropagation();
              fechar();
            }
          }}
          className={cn(
            'fixed z-[50] flex flex-col border border-border bg-background shadow-card',
            isMobile
              ? 'inset-0'
              : 'bottom-4 right-4 h-[min(640px,calc(100vh-2rem))] w-[400px] rounded-xl',
          )}
        >
          <header className="flex items-center gap-2 border-b border-border px-4 py-3">
            <h2 id={ids.titulo} className="flex-1 text-base font-semibold text-foreground">
              Bia
            </h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11"
              onClick={() => void bia.novaConversa()}
              disabled={bia.enviando || bia.emAndamento}
            >
              Nova conversa
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-11 w-11 p-0"
              onClick={fechar}
              aria-label="Fechar a Bia"
            >
              <Icone icon={ICONES.fecharMenu} />
            </Button>
          </header>

          <p
            id={ids.aviso}
            className="border-b border-border bg-muted px-4 py-2 text-xs font-medium text-foreground"
          >
            {AVISO_MODO_CONSULTA}
            <span className="mt-1 block font-normal text-muted-foreground">
              {bia.servico?.memoria?.aviso ?? AVISO_MEMORIA_COMPARTILHADA}
            </span>
          </p>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {bia.carregando ? (
              <p role="status" className="text-sm text-muted-foreground">Carregando a conversa…</p>
            ) : !bia.conversaId ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Nenhuma conversa aberta. Cada conversa é isolada e fica salva no seu usuário.
                </p>
                <Button type="button" className="min-h-11" onClick={() => void bia.novaConversa()}>
                  Começar conversa
                </Button>
              </div>
            ) : (
              <ol role="log" aria-live="polite" aria-label="Conversa com a Bia" className="space-y-4">
                {bia.execucoes.length === 0 ? (
                  <li className="text-sm text-muted-foreground">Conversa nova. Pergunte algo.</li>
                ) : null}
                {bia.execucoes.map((e) => (
                  <Turno key={e.id} e={e} onVerificar={(id) => void bia.verificar(id)} />
                ))}
                <li ref={fimDoLog} aria-hidden="true" />
              </ol>
            )}
          </div>

          {bia.erro ? (
            <p role="alert" className="mx-4 mb-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-foreground">
              <span className="font-medium">Erro: </span>
              {bia.erro}
            </p>
          ) : null}
          {bia.servico && !bia.servico.motor_configurado ? (
            <p role="status" className="mx-4 mb-2 text-xs text-muted-foreground">
              O Hermes ainda não está configurado neste servidor: o histórico funciona, o envio não.
            </p>
          ) : null}

          <form
            className="space-y-2 border-t border-border px-4 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              void enviar();
            }}
          >
            <label className="flex min-h-11 items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                className="h-5 w-5"
                checked={comContexto}
                onChange={(e) => setComContexto(e.target.checked)}
              />
              Incluir contexto de uma campanha (somente leitura)
            </label>
            {comContexto ? (
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <div>
                  <label htmlFor={ids.campanha} className="mb-1 block text-xs font-medium text-foreground">
                    Campanha (id VOLC)
                  </label>
                  <input
                    id={ids.campanha}
                    value={campanha}
                    onChange={(e) => setCampanha(e.target.value)}
                    aria-invalid={!refValida}
                    autoComplete="off"
                    spellCheck={false}
                    className="min-h-11 w-full rounded-md border border-input bg-background px-3 text-sm"
                  />
                </div>
                <div>
                  <label htmlFor={ids.janela} className="mb-1 block text-xs font-medium text-foreground">
                    Janela
                  </label>
                  <select
                    id={ids.janela}
                    value={janela}
                    onChange={(e) => setJanela(e.target.value as JanelaDeContexto)}
                    className="min-h-11 rounded-md border border-input bg-background px-2 text-sm"
                  >
                    <option value="ultimos_7_dias">7 dias</option>
                    <option value="ultimos_14_dias">14 dias</option>
                    <option value="ultimos_30_dias">30 dias</option>
                  </select>
                </div>
                {!refValida ? (
                  <p className="col-span-2 text-xs text-destructive">
                    Id de campanha inválido: use o id VOLC (letras, números, ponto, hífen, dois-pontos).
                  </p>
                ) : null}
              </div>
            ) : null}
            <label htmlFor={ids.campo} className="sr-only">
              Mensagem para a Bia
            </label>
            <Textarea
              id={ids.campo}
              ref={campo}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={aoTeclar}
              rows={3}
              aria-describedby={ids.contador}
              disabled={!bia.conversaId || bia.bloqueada}
              className="resize-none"
            />
            <div className="flex items-center gap-2">
              <p id={ids.contador} className={cn('flex-1 text-xs', texto.length > limite ? 'text-destructive' : 'text-muted-foreground')}>
                {texto.length}/{limite} · Enter envia, Shift+Enter quebra a linha
              </p>
              <Button type="submit" className="min-h-11" disabled={!podeEnviar}>
                {bia.enviando || bia.emAndamento ? 'Aguardando…' : 'Enviar'}
              </Button>
            </div>
            {bia.bloqueada ? (
              <p className="text-xs text-muted-foreground">
                Esta conversa tem um envio de resultado incerto. Verifique a resposta ou abra uma nova
                conversa.
              </p>
            ) : null}
          </form>
        </section>
      ) : null}
    </>
  );
};

export default BiaWidget;
