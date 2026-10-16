/**
 * Histórico da conversa: turnos (operador → Bia), notas locais e estados.
 *
 * O estado de cada envio aparece PRESO à mensagem a que pertence. O texto
 * parcial só existe quando o servidor mandou deltas reais; sem eles, a Bia
 * está "preparando a resposta", nunca "digitando". A bolha em streaming fica
 * `aria-busy` para o leitor de tela anunciar a resposta uma vez, ao final.
 */
import React, { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { cn } from '@/lib/utils';

import type { BiaApi } from '../api';
import { ICONES_BIA } from '../icones';
import type { AnexoReferencia, ExecucaoDaBia } from '../tipos';
import { formatarTamanho } from '../useAnexos';
import type { NotaLocal } from '../useBia';

import { CartaoDeCaptura } from './CartaoDeCaptura';
import { MarkdownDaBia } from './Markdown';

export const hora = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const Tempo: React.FC<{ iso: string }> = ({ iso }) => (
  <time dateTime={iso} className="text-micro font-normal tracking-normal text-muted-foreground">
    {hora(iso)}
  </time>
);

/** Três pontos de atividade: opacidade apenas; parados com movimento reduzido. */
export const Pontos: React.FC = () => (
  <span aria-hidden="true" className="inline-flex items-center gap-1">
    {[0, 160, 320].map((atraso) => (
      <span
        key={atraso}
        style={{ animationDelay: `${atraso}ms` }}
        className="h-1.5 w-1.5 rounded-full bg-muted-foreground motion-safe:animate-pulse"
      />
    ))}
  </span>
);

const JANELAS: Record<string, string> = {
  ultimos_7_dias: '7 dias',
  ultimos_14_dias: '14 dias',
  ultimos_30_dias: '30 dias',
};

export const iconeDoAnexo = (familia: string, tipo: string) =>
  familia === 'imagem' ? ICONES_BIA.imagem : tipo === 'pdf' ? ICONES_BIA.pdf : ICONES_BIA.documento;

const Miniatura: React.FC<{ anexo: AnexoReferencia; api: BiaApi }> = ({ anexo, api }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [falhou, setFalhou] = useState(false);
  useEffect(() => {
    let ativo = true;
    let criada: string | null = null;
    api.urlDoAnexo(anexo.id)
      .then((u) => {
        criada = u;
        if (ativo) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => ativo && setFalhou(true));
    return () => {
      ativo = false;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [anexo.id, api]);
  if (falhou) {
    return (
      <span className="flex h-16 w-16 items-center justify-center rounded-md border border-dashed border-border text-center text-micro text-muted-foreground">
        expirada
      </span>
    );
  }
  return url ? (
    <img src={url} alt={`Imagem anexada: ${anexo.nome}`} className="h-16 w-16 rounded-md border border-border object-cover" />
  ) : (
    <span aria-hidden="true" className="h-16 w-16 rounded-md bg-muted" />
  );
};

const AnexosDoTurno: React.FC<{ anexos: AnexoReferencia[]; api: BiaApi }> = ({ anexos, api }) => {
  const imagens = anexos.filter((a) => a.familia === 'imagem');
  const documentos = anexos.filter((a) => a.familia !== 'imagem');
  return (
    <div className="mt-2 space-y-2">
      {imagens.length ? (
        <ul aria-label="Imagens anexadas" className="flex flex-wrap justify-end gap-2">
          {imagens.map((a) => (
            <li key={a.id}><Miniatura anexo={a} api={api} /></li>
          ))}
        </ul>
      ) : null}
      {documentos.length ? (
        <ul aria-label="Arquivos anexados" className="flex flex-col items-end gap-1">
          {documentos.map((a) => (
            <li key={a.id} className="flex max-w-full items-center gap-2 rounded-md border border-border bg-card px-2 py-1">
              <Icone icon={iconeDoAnexo(a.familia, a.tipo)} tamanho="sm" className="text-muted-foreground" />
              <span className="min-w-0 truncate text-denso text-foreground">{a.nome}</span>
              <span className="shrink-0 text-micro font-normal tracking-normal text-muted-foreground">
                {a.tipo.toUpperCase()} · {formatarTamanho(a.tamanho)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

export const BotaoCopiar: React.FC<{ texto: string; rotulo?: string }> = ({ texto, rotulo = 'Copiar resposta' }) => {
  const [copiado, setCopiado] = useState(false);
  useEffect(() => {
    if (!copiado) return;
    const t = setTimeout(() => setCopiado(false), 1800);
    return () => clearTimeout(t);
  }, [copiado]);
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="touch-target h-8 gap-1.5 px-2 text-micro font-medium tracking-normal text-muted-foreground"
      onClick={() => {
        void navigator.clipboard?.writeText(texto).then(() => setCopiado(true), () => undefined);
      }}
    >
      <Icone icon={copiado ? ICONES_BIA.copiado : ICONES_BIA.copiar} tamanho="sm" />
      <span aria-live="polite">{copiado ? 'Copiado' : 'Copiar'}</span>
      <span className="sr-only"> — {rotulo}</span>
    </Button>
  );
};

const PROXIMO_PASSO: Record<string, string> = {
  hermes_usou_ferramenta: 'Reformule como pergunta de consulta, sem pedir ações.',
  anexo_indisponivel: 'Anexe o arquivo de novo e envie outra mensagem.',
  hermes_indisponivel: 'Tente de novo em alguns minutos.',
  hermes_erro_no_turno: 'Tente de novo; se repetir, abra uma nova conversa.',
};

interface PropsTurno {
  e: ExecucaoDaBia;
  parcial?: string;
  api: BiaApi;
  onVerificar: (id: string) => void;
  onNovaConversa: () => void;
  onReusar: (texto: string) => void;
}

export const Turno: React.FC<PropsTurno> = ({ e, parcial, api, onVerificar, onNovaConversa, onReusar }) => {
  const anexos = e.contexto?.anexos ?? [];
  const campanha = e.contexto?.campanha ?? null;
  const emCurso = e.estado === 'queued' || e.estado === 'running';
  const digitando = e.estado === 'running' && !!parcial;
  return (
    <li className="space-y-3" data-estado={e.estado}>
      {/* Operador */}
      <div className="flex flex-col items-end">
        <p className="mb-1 flex items-center gap-2 text-micro font-medium tracking-normal text-muted-foreground">
          <span>Você</span>
          <Tempo iso={e.criada_em} />
        </p>
        {e.entrada ? (
          <div className="max-w-[85%] rounded-[10px] rounded-tr-sm bg-muted px-3 py-2">
            <p className="whitespace-pre-wrap break-words text-sm text-foreground [overflow-wrap:anywhere]">{e.entrada}</p>
          </div>
        ) : null}
        {campanha ? (
          <p className="mt-1 text-micro font-normal tracking-normal text-muted-foreground">
            Contexto: campanha {campanha.campaign_ref} · {JANELAS[campanha.janela] ?? campanha.janela}
          </p>
        ) : null}
        {anexos.length ? <AnexosDoTurno anexos={anexos} api={api} /> : null}
        {e.estado === 'queued' ? (
          <p className="mt-1 flex items-center gap-2 text-micro font-normal tracking-normal text-muted-foreground">
            <Pontos /> Mensagem na fila
          </p>
        ) : null}
      </div>

      {/* Bia */}
      {e.estado === 'queued' ? null : (
        <div className="flex flex-col items-start">
          <p className="mb-1 flex items-center gap-2 text-micro font-medium tracking-normal text-muted-foreground">
            <span className="font-display font-semibold text-foreground">Bia</span>
            {e.terminada_em ? <Tempo iso={e.terminada_em} /> : null}
          </p>
          <div className="w-full max-w-full" aria-busy={emCurso || undefined}>
            {e.estado === 'succeeded' && e.resposta && e.contexto?.intencao === 'rascunho_cerebro' ? (
              <CartaoDeCaptura e={e} api={api} />
            ) : e.estado === 'succeeded' && e.resposta ? (
              <>
                <MarkdownDaBia texto={e.resposta} />
                <div className="-ml-2 mt-0.5">
                  <BotaoCopiar texto={e.resposta} />
                </div>
              </>
            ) : digitando ? (
              <>
                <MarkdownDaBia texto={parcial!} />
                <p className="mt-2 flex items-center gap-2 text-micro font-normal tracking-normal text-muted-foreground">
                  <Pontos /> Bia está digitando…
                </p>
              </>
            ) : e.estado === 'running' ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Pontos /> Bia está preparando a resposta…
              </p>
            ) : e.estado === 'uncertain' ? (
              <div className="w-full rounded-[10px] border border-warning/40 bg-warning/10 px-3 py-2.5">
                <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="text-warning" />
                  Resultado incerto
                </p>
                <p className="mt-1 text-denso text-foreground">
                  A conexão caiu antes da confirmação. Não sabemos se a Bia recebeu a mensagem, e
                  <strong> nada será reenviado automaticamente</strong>.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button type="button" variant="outline" size="sm" className="touch-target" onClick={() => onVerificar(e.id)}>
                    Verificar resposta
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="touch-target" onClick={onNovaConversa}>
                    Nova conversa
                  </Button>
                </div>
              </div>
            ) : e.estado === 'failed' || e.estado === 'cancelled' ? (
              <div className="w-full rounded-[10px] border border-destructive/40 bg-destructive/5 px-3 py-2.5">
                <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="text-destructive" />
                  {e.estado === 'cancelled' ? 'Envio cancelado' : 'A Bia não conseguiu responder'}
                </p>
                {e.erro?.mensagem ? <p className="mt-1 text-denso text-foreground">{e.erro.mensagem}</p> : null}
                <p className="mt-1 text-denso text-muted-foreground">
                  {(e.erro && PROXIMO_PASSO[e.erro.codigo]) || 'Nada foi reenviado. Você pode reaproveitar o texto e enviar de novo.'}
                </p>
                {e.entrada ? (
                  <Button type="button" variant="outline" size="sm" className="touch-target mt-2" onClick={() => onReusar(e.entrada)}>
                    Reaproveitar o texto
                  </Button>
                ) : null}
              </div>
            ) : e.estado === 'succeeded' ? (
              <p className="text-sm text-muted-foreground">A Bia respondeu sem texto.</p>
            ) : null}
          </div>
        </div>
      )}
    </li>
  );
};

/* ------------------------------------------------------------- notas locais */

interface PropsNota {
  nota: NotaLocal;
  comandosWeb: { nome: string; descricao: string; args: string }[];
}

export const Nota: React.FC<PropsNota> = ({ nota, comandosWeb }) => {
  const base = 'w-full rounded-[10px] border px-3 py-2.5 text-denso';
  if (nota.tipo === 'ajuda') {
    return (
      <li className={cn(base, 'border-border bg-card')}>
        <p className="kicker mb-1">Comandos nesta conversa</p>
        <dl className="space-y-1">
          {comandosWeb.map((c) => (
            <div key={c.nome} className="flex flex-wrap gap-x-2">
              <dt className="font-data text-foreground">/{c.nome}{c.args ? ` ${c.args}` : ''}</dt>
              <dd className="text-muted-foreground">{c.descricao}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-muted-foreground">
          Comandos do Telegram que usam ferramentas ou mudam algo fora daqui não rodam na web. Digite
          <span className="font-data"> / </span> para ver todos, com o motivo.
        </p>
      </li>
    );
  }
  if (nota.tipo === 'status') {
    const r = nota.resultado;
    const linhas: [string, string][] = [];
    if (r.conversa) {
      linhas.push(['Mensagens nesta conversa', String(r.conversa.mensagens)]);
      const pend = (r.conversa.por_estado.queued ?? 0) + (r.conversa.por_estado.running ?? 0);
      if (pend) linhas.push(['Em andamento', String(pend)]);
      if (r.conversa.por_estado.uncertain) linhas.push(['Incertas', String(r.conversa.por_estado.uncertain)]);
      if (r.conversa.por_estado.failed) linhas.push(['Com falha', String(r.conversa.por_estado.failed)]);
    }
    if (r.hermes) linhas.push(['Bia (Hermes)', r.hermes.gateway === 'running' ? `no ar · v${r.hermes.versao ?? '?'}` : 'sem resposta']);
    if (r.sessao_web?.tokens_entrada != null) {
      linhas.push(['Tokens desta conversa', `${r.sessao_web.tokens_entrada.toLocaleString('pt-BR')} entrada · ${(r.sessao_web.tokens_saida ?? 0).toLocaleString('pt-BR')} saída`]);
    }
    if (r.sessao_web?.ferramentas_usadas != null) linhas.push(['Ferramentas usadas', String(r.sessao_web.ferramentas_usadas)]);
    return (
      <li className={cn(base, 'border-border bg-card')}>
        <p className="kicker mb-1">/status · somente leitura</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          {linhas.map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="numero text-foreground">{v}</dd>
            </React.Fragment>
          ))}
        </dl>
        {r.avisos.map((a) => <p key={a} className="mt-1.5 text-muted-foreground">{a}</p>)}
      </li>
    );
  }
  if (nota.tipo === 'cerebro') {
    const NOMES = { volc: 'VOLC', arbitragem: 'Arbitragem', pessoal: 'Pessoal' } as const;
    return (
      <li className={cn(base, 'border-border bg-card')}>
        <p className="kicker mb-1">/cerebro · somente leitura</p>
        <div className="max-w-full overflow-x-auto">
          <table className="w-full border-collapse text-denso [display:table]">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th scope="col" className="py-1 pr-3 font-medium">Cérebro</th>
                <th scope="col" className="py-1 pr-3 font-medium">Commit</th>
                <th scope="col" className="py-1 pr-3 font-medium">Alterações</th>
                <th scope="col" className="py-1 font-medium">Capturas web</th>
              </tr>
            </thead>
            <tbody>
              {nota.resultado.repos.map((r) => (
                <tr key={r.cerebro} className="border-t border-border">
                  <td className="py-1 pr-3 text-foreground">{NOMES[r.cerebro] ?? r.cerebro}</td>
                  <td className="numero py-1 pr-3 text-foreground">
                    {r.ok ? `${r.commit ?? '—'}${r.atras ? ` · ${r.atras} atrás` : ''}${r.a_frente ? ` · ${r.a_frente} à frente` : ''}` : 'sem leitura'}
                  </td>
                  <td className="numero py-1 pr-3 text-foreground">{r.alteracoes ?? '—'}</td>
                  <td className="numero py-1 text-foreground">{r.capturas_web_pendentes ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-1.5 text-muted-foreground">
          Nada foi sincronizado. Puxar do GitHub, commit e push continuam com /cerebro e /salve no Telegram.
        </p>
      </li>
    );
  }
  if (nota.tipo === 'recusa') {
    return (
      <li className={cn(base, 'border-dashed border-border bg-card')}>
        <p className="flex items-center gap-1.5 font-data text-foreground">
          <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="text-muted-foreground" />
          {nota.titulo}
        </p>
        <p className="mt-0.5 text-muted-foreground">{nota.texto}</p>
      </li>
    );
  }
  return (
    <li className={cn(base, 'border-transparent bg-transparent px-0 py-0 text-muted-foreground')}>{nota.texto}</li>
  );
};

