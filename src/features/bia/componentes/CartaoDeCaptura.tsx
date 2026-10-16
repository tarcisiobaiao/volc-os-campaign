/**
 * Prévia da captura para o cérebro: o rascunho da Bia vira formulário editável.
 *
 * Dois cliques: "Salvar no cérebro" (atalho) → a Bia redige → "Salvar no
 * cérebro" aqui. Quem grava é o servidor (executor tipado no VPS), nunca a Bia:
 * UM arquivo novo na estação `inbox/bia-web/`, sem commit/push. A tela separa
 * "salvo no servidor" (arquivo escrito e conferido por sha256) de
 * "sincronizado com o GitHub" (que continua no Telegram).
 *
 * O request_id do salvamento nasce uma vez por rascunho e fica guardado: um
 * segundo clique, ou o mesmo clique depois de cair a rede, devolve o MESMO
 * arquivo.
 */
import React, { useEffect, useId, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { ErroDeApi } from '@/lib/secureApi';
import { cn } from '@/lib/utils';

import type { BiaApi } from '../api';
import { ICONES_BIA } from '../icones';
import type {
  CapturaGravada,
  DestinoDoCerebro,
  ExecucaoDaBia,
  RascunhoDoCerebro,
  TipoDeCaptura,
} from '../tipos';
import { mensagemDe } from '../useBia';

import { BotaoCopiar } from './Historico';
import { MarkdownDaBia } from './Markdown';

const DESTINOS: { valor: DestinoDoCerebro; rotulo: string }[] = [
  { valor: 'volc', rotulo: 'VOLC (operação)' },
  { valor: 'arbitragem', rotulo: 'Arbitragem (publisher)' },
  { valor: 'pessoal', rotulo: 'Pessoal (estratégia)' },
];
const TIPOS: { valor: TipoDeCaptura; rotulo: string }[] = [
  { valor: 'decisao', rotulo: 'Decisão' },
  { valor: 'captura', rotulo: 'Captura' },
  { valor: 'pendencia', rotulo: 'Pendência' },
  { valor: 'referencia', rotulo: 'Referência' },
  { valor: 'nota', rotulo: 'Nota' },
];

const lista = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && !!x.trim()).map((x) => x.trim()) : [];

/** Lê o JSON do rascunho (bloco ```json ou o primeiro objeto). Formato errado = null. */
export function lerRascunho(resposta: string): RascunhoDoCerebro | null {
  const bloco = resposta.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1] ?? resposta.match(/\{[\s\S]*\}/)?.[0];
  if (!bloco) return null;
  try {
    const j = JSON.parse(bloco) as Record<string, unknown>;
    const destino = DESTINOS.some((d) => d.valor === j.destino) ? (j.destino as DestinoDoCerebro) : 'volc';
    const tipo = TIPOS.some((t) => t.valor === j.tipo) ? (j.tipo as TipoDeCaptura) : 'captura';
    const titulo = typeof j.titulo === 'string' ? j.titulo.trim().slice(0, 120) : '';
    if (!titulo) return null;
    return {
      destino, tipo, titulo,
      resumo: typeof j.resumo === 'string' ? j.resumo.trim() : '',
      decisoes: lista(j.decisoes), aprendizados: lista(j.aprendizados),
      pendencias: lista(j.pendencias), hipoteses: lista(j.hipoteses), tags: lista(j.tags).slice(0, 8),
    };
  } catch {
    return null;
  }
}

export function montarConteudo(r: RascunhoDoCerebro, hoje = new Date()): string {
  const data = hoje.toISOString().slice(0, 10);
  const secao = (titulo: string, itens: string[], fmt: (s: string) => string) =>
    itens.length ? `## ${titulo}\n\n${itens.map(fmt).join('\n')}\n` : '';
  return [
    r.resumo ? `${r.resumo}\n` : '',
    secao('Decisões', r.decisoes, (s) => `- ${s}`),
    secao('Aprendizados', r.aprendizados, (s) => `- ${s}`),
    secao('Pendências', r.pendencias, (s) => `- [ ] ${data}: ${s}`),
    secao('Hipóteses (não confirmadas)', r.hipoteses, (s) => `- ${s}`),
    `Fonte: conversa com a Bia no VOLC O.S. (${data}).`,
  ].filter(Boolean).join('\n');
}

const chaveLocal = (execucaoId: string) => `volc.bia.captura.${execucaoId}`;

interface Guardado {
  request_id: string;
  recibo?: CapturaGravada;
}

function lerGuardado(execucaoId: string): Guardado | null {
  try {
    const bruto = window.localStorage.getItem(chaveLocal(execucaoId));
    return bruto ? (JSON.parse(bruto) as Guardado) : null;
  } catch {
    return null;
  }
}

function guardar(execucaoId: string, g: Guardado): void {
  try {
    window.localStorage.setItem(chaveLocal(execucaoId), JSON.stringify(g));
  } catch {
    /* sem armazenamento: vale para esta visita */
  }
}

const novoId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

interface Props {
  e: ExecucaoDaBia;
  api: BiaApi;
}

export const CartaoDeCaptura: React.FC<Props> = ({ e, api }) => {
  const rascunho = useMemo(() => (e.resposta ? lerRascunho(e.resposta) : null), [e.resposta]);
  const [destino, setDestino] = useState<DestinoDoCerebro>(rascunho?.destino ?? 'volc');
  const [tipo, setTipo] = useState<TipoDeCaptura>(rascunho?.tipo ?? 'captura');
  const [titulo, setTitulo] = useState(rascunho?.titulo ?? '');
  const [conteudo, setConteudo] = useState(() => (rascunho ? montarConteudo(rascunho) : ''));
  const [recibo, setRecibo] = useState<CapturaGravada | null>(() => lerGuardado(e.id)?.recibo ?? null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<{ texto: string; indisponivel: boolean } | null>(null);
  const base = useId();

  useEffect(() => setErro(null), [destino, tipo, titulo, conteudo]);

  if (!rascunho) {
    return (
      <div className="w-full rounded-[10px] border border-border bg-card px-3 py-2.5 text-denso">
        <p className="font-semibold text-foreground">A Bia não devolveu a captura no formato esperado.</p>
        <p className="mt-1 text-muted-foreground">Nada foi gravado. Peça de novo com /salvar.</p>
        {e.resposta ? <div className="mt-2 border-t border-border pt-2"><MarkdownDaBia texto={e.resposta} /></div> : null}
      </div>
    );
  }

  const salvar = async () => {
    if (salvando) return;
    setSalvando(true);
    setErro(null);
    const g = lerGuardado(e.id) ?? { request_id: novoId() };
    guardar(e.id, g); // o MESMO request_id em toda nova tentativa
    try {
      const { captura } = await api.gravarCaptura({
        request_id: g.request_id, destino, tipo, titulo: titulo.trim(), conteudo: conteudo.trim(),
        tags: rascunho.tags, execucao_id: e.id,
      });
      guardar(e.id, { ...g, recibo: captura });
      setRecibo(captura);
    } catch (err) {
      setErro({ texto: mensagemDe(err), indisponivel: err instanceof ErroDeApi && err.status === 503 });
    } finally {
      setSalvando(false);
    }
  };

  const textoParaCopiar = `# ${titulo}\n\n${conteudo}`;

  if (recibo) {
    return (
      <div className="w-full rounded-[10px] border border-border bg-card px-3 py-2.5 text-denso">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <Icone icon={ICONES_BIA.salvo} tamanho="sm" className="text-success" />
          Salvo no servidor
        </p>
        <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          <dt className="text-muted-foreground">Cérebro</dt>
          <dd className="text-foreground">{recibo.repo}</dd>
          <dt className="text-muted-foreground">Arquivo</dt>
          <dd className="break-all font-data text-micro tracking-normal text-foreground">{recibo.caminho}</dd>
          <dt className="text-muted-foreground">Conferido</dt>
          <dd className="font-data text-micro tracking-normal text-foreground">sha256 {recibo.sha256.slice(0, 12)}…</dd>
        </dl>
        <p className="mt-2 flex items-start gap-2 text-muted-foreground">
          <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="mt-0.5 shrink-0" />
          <span>
            <strong className="font-medium text-foreground">Não sincronizado com o GitHub.</strong> Commit e push
            continuam no Telegram (/salve), com a sua autorização.
          </span>
        </p>
        <div className="-ml-2 mt-1">
          <BotaoCopiar texto={recibo.caminho} rotulo="Copiar caminho do arquivo" />
        </div>
      </div>
    );
  }

  const campo = 'w-full rounded-md border border-input bg-card px-2.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70';
  return (
    <form
      aria-label="Captura para o cérebro"
      className="w-full rounded-[10px] border border-border bg-card px-3 py-3"
      onSubmit={(ev) => {
        ev.preventDefault();
        void salvar();
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="kicker">Captura para o cérebro</p>
        <span className="rounded-full border border-border px-2 text-micro font-medium tracking-normal text-muted-foreground">
          Rascunho — ainda não salvo
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div>
          <label htmlFor={`${base}-destino`} className="mb-1 block text-micro font-medium tracking-normal text-muted-foreground">Cérebro</label>
          <select id={`${base}-destino`} value={destino} onChange={(ev) => setDestino(ev.target.value as DestinoDoCerebro)}
                  className={cn(campo, 'h-10')}>
            {DESTINOS.map((d) => <option key={d.valor} value={d.valor}>{d.rotulo}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${base}-tipo`} className="mb-1 block text-micro font-medium tracking-normal text-muted-foreground">Tipo</label>
          <select id={`${base}-tipo`} value={tipo} onChange={(ev) => setTipo(ev.target.value as TipoDeCaptura)}
                  className={cn(campo, 'h-10')}>
            {TIPOS.map((t) => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}
          </select>
        </div>
      </div>
      <label htmlFor={`${base}-titulo`} className="mb-1 mt-2 block text-micro font-medium tracking-normal text-muted-foreground">Título</label>
      <input id={`${base}-titulo`} value={titulo} maxLength={120} onChange={(ev) => setTitulo(ev.target.value)}
             className={cn(campo, 'h-10')} />
      <label htmlFor={`${base}-conteudo`} className="mb-1 mt-2 block text-micro font-medium tracking-normal text-muted-foreground">
        O que será salvo (pode editar)
      </label>
      <textarea id={`${base}-conteudo`} value={conteudo} rows={8} maxLength={20000}
                onChange={(ev) => setConteudo(ev.target.value)}
                className={cn(campo, 'resize-y py-2 font-data text-denso leading-relaxed')} />
      <p className="mt-1.5 text-micro font-normal tracking-normal text-muted-foreground">
        Vai para a estação <span className="font-data">inbox/bia-web/</span> do cérebro, como arquivo novo. Nada é
        commitado; promover ao canônico continua com a Bia no Telegram.
      </p>
      {erro ? (
        <p role="alert" className="mt-2 flex items-start gap-2 text-denso text-foreground">
          <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="mt-0.5 shrink-0 text-destructive" />
          {erro.texto}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" className="touch-target gap-1.5" disabled={salvando || !titulo.trim() || !conteudo.trim()}>
          <Icone icon={salvando ? ICONES_BIA.enviando : ICONES_BIA.salvar} tamanho="sm"
                 className={salvando ? 'motion-safe:animate-spin' : undefined} />
          {salvando ? 'Salvando…' : 'Salvar no cérebro'}
        </Button>
        <BotaoCopiar texto={textoParaCopiar} rotulo="Copiar a captura" />
        {erro?.indisponivel ? (
          <span className="text-micro font-normal tracking-normal text-muted-foreground">Copie e use /salve no Telegram.</span>
        ) : null}
      </div>
    </form>
  );
};
