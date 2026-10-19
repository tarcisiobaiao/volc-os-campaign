/**
 * Markdown da Bia, sanitizado por construção.
 *
 * A resposta vem de um modelo e pode conter qualquer coisa. Por isso:
 * - `skipHtml`: HTML cru é descartado (nunca vira DOM); não há
 *   `dangerouslySetInnerHTML` em lugar nenhum;
 * - links só `http(s)` e `mailto`; abrem em nova aba sem `opener` nem
 *   `referrer`, e o domínio aparece quando o texto do link não o mostra —
 *   quem lê sabe para onde vai antes de clicar;
 * - imagens NÃO são carregadas (seria o navegador buscando URL arbitrária
 *   escolhida pelo modelo): viram um link identificado;
 * - código e tabelas rolam na horizontal dentro da própria caixa, nunca a
 *   página.
 */
import React from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Icone } from '@/components/ui/icone';

import { ICONES_BIA } from '../icones';

const PROTOCOLOS = new Set(['http:', 'https:', 'mailto:']);

export function urlSegura(url: string | undefined | null): URL | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return PROTOCOLOS.has(u.protocol) ? u : null;
  } catch {
    return null;
  }
}

const textoDe = (no: React.ReactNode): string =>
  typeof no === 'string' || typeof no === 'number'
    ? String(no)
    : Array.isArray(no)
      ? no.map(textoDe).join('')
      : React.isValidElement<{ children?: React.ReactNode }>(no)
        ? textoDe(no.props.children)
        : '';

const LinkExterno: React.FC<{ href?: string; children?: React.ReactNode }> = ({ href, children }) => {
  const u = urlSegura(href);
  if (!u) return <span>{children}</span>;
  const dominio = u.protocol === 'mailto:' ? u.pathname : u.hostname.replace(/^www\./, '');
  const mostraDominio = !textoDe(children).toLowerCase().includes(dominio.toLowerCase());
  return (
    <a
      href={u.href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      title={u.href}
      className="rounded-sm font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70"
    >
      {children}
      {mostraDominio ? <span className="font-normal text-muted-foreground"> ({dominio})</span> : null}
      <Icone icon={ICONES_BIA.linkExterno} tamanho="sm" className="ml-0.5 inline-block align-[-2px]" />
      <span className="sr-only"> (abre em nova aba)</span>
    </a>
  );
};

const COMPONENTES: Components = {
  a: ({ href, children }) => <LinkExterno href={href}>{children}</LinkExterno>,
  img: ({ src, alt }) => {
    const u = urlSegura(typeof src === 'string' ? src : null);
    const rotulo = `Imagem${alt ? `: ${alt}` : ''}`;
    return u ? <LinkExterno href={u.href}>{rotulo}</LinkExterno> : <span>[{rotulo}]</span>;
  },
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  h1: ({ children }) => <p className="mb-1 mt-3 font-display text-base font-semibold">{children}</p>,
  h2: ({ children }) => <p className="mb-1 mt-3 font-display text-[0.95rem] font-semibold">{children}</p>,
  h3: ({ children }) => <p className="mb-1 mt-3 font-semibold">{children}</p>,
  h4: ({ children }) => <p className="mb-1 mt-2 font-semibold">{children}</p>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>
  ),
  hr: () => <hr className="my-3 border-border" />,
  pre: ({ children }) => (
    <pre className="my-2 max-w-full overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 font-data text-denso">
      {children}
    </pre>
  ),
  code: ({ className, children }) =>
    className?.startsWith('language-') ? (
      <code className="font-data">{children}</code>
    ) : (
      <code className="break-words rounded bg-muted px-1 py-px font-data text-[0.85em]">{children}</code>
    ),
  table: ({ children }) => (
    <div className="my-2 max-w-full overflow-x-auto rounded-md border border-border">
      {/* `[display:table]` vence o `table { display: block }` global do celular (index.css); quem rola é a caixa. */}
      <table className="w-full border-collapse text-denso [display:table]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th scope="col" className="border-b border-border bg-muted px-2 py-1.5 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-border px-2 py-1.5 align-top">{children}</td>,
};

export const MarkdownDaBia: React.FC<{ texto: string }> = ({ texto }) => (
  <div className="break-words text-sm leading-relaxed text-foreground [overflow-wrap:anywhere]">
    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={COMPONENTES}>
      {texto}
    </ReactMarkdown>
  </div>
);
