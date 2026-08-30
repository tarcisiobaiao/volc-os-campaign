/**
 * O texto escrito, renderizado como o leitor vai ver — e em segurança.
 *
 * ## Duas coisas que a primeira versão errou
 *
 * **Removia `style`.** Blocos `wp:html` do WordPress não podem usar CSS
 * externo: todo o visual deles mora em atributo inline. Sem ele, o "Roteador de
 * Elegibilidade" da página 3 desabava numa lista de texto solto que parecia
 * página quebrada, e os botões perdiam cor e largura. O `style` volta — e vem
 * com uma varredura de CSS PRÓPRIA, porque o DOMPurify não faz essa parte (ver
 * o comentário sobre `CSS_PERIGOSO` abaixo, que corrige uma afirmação errada
 * que eu tinha escrito aqui).
 *
 * **Misturava o widget com o artigo.** O widget é um bloco de UI com fundo
 * branco e tipografia própria, escrito para viver dentro do tema do site. Solto
 * no meio da prosa e sobre o nosso fundo, ele lê como defeito. Aqui ele ganha
 * moldura e rótulo — e o aviso de que o script foi removido fica NELE, não no
 * topo da página, que é onde ninguém liga o aviso ao bloco.
 *
 * ## O que continua barrado, e por quê
 *
 * O conteúdo é escrito por um modelo. `<script>` dele executaria na NOSSA
 * origem com a sessão do operador. O widget é verificado no rascunho do
 * WordPress, que é onde ele deve rodar.
 */
import React, { useMemo } from 'react';
import DOMPurify from 'dompurify';
import { ShieldAlert } from 'lucide-react';

const LIMPEZA = {
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'link', 'base'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus',
                'onanimationstart', 'onanimationend', 'ontoggle', 'srcdoc'],
};

// ⚠️ O DOMPurify NÃO sanitiza o conteúdo do `style`. Medido em Chromium de
// verdade (não no jsdom), com a configuração acima, os quatro passam intactos:
//
//   style="background:url(javascript:alert(1))"   → passa
//   style="width:expression(alert(1))"            → passa
//   style="-moz-binding:url(http://mau/x.xml)"    → passa
//   style="behavior:url(#default#time2)"          → passa
//
// Ele filtra NOME de atributo e URI de `href`/`src`; CSS não está no escopo.
// Escrevi num comentário que ele derrubava esses vetores — não derruba, e um
// teste pegou a afirmação falsa.
//
// Nenhum deles executa em navegador moderno: são heranças de IE e do XBL antigo
// do Firefox. Mas o conteúdo aqui é escrito por um modelo e renderizado na
// NOSSA origem, e o custo de varrer é uma função de dez linhas.
//
// A varredura remove só a DECLARAÇÃO suspeita, não o atributo inteiro: derrubar
// o `style` todo por causa de um `url()` estranho apagaria o visual do widget —
// que é exatamente o defeito que manter o `style` veio consertar.
const CSS_PERIGOSO = /(^|[\s:(])(javascript|vbscript|livescript)\s*:|expression\s*\(|-moz-binding|behavior\s*:/i;

function limparEstilo(valor: string): string {
  return valor
    .split(';')
    .filter((d) => d.trim() && !CSS_PERIGOSO.test(d))
    .join(';');
}

// Um hook só para o processo, e idempotente: `addHook` empilha, então registrar
// a cada render vazaria memória e rodaria a varredura N vezes por atributo.
let hookInstalado = false;
if (!hookInstalado && typeof DOMPurify.addHook === 'function') {
  DOMPurify.addHook('afterSanitizeAttributes', (no) => {
    const el = no as Element;
    if (!el.getAttribute) return;
    const estilo = el.getAttribute('style');
    if (!estilo) return;
    const limpo = limparEstilo(estilo);
    if (limpo !== estilo) {
      if (limpo.trim()) el.setAttribute('style', limpo);
      else el.removeAttribute('style');
    }
  });
  hookInstalado = true;
}

export { limparEstilo };

/** Tipografia da prosa. Fica aqui e não numa folha global porque só o conteúdo
 *  do motor usa — e ele é HTML de terceiro, sem classes nossas para agarrar. */
export const PROSA = 'max-w-[68ch] text-[15px] leading-[1.75] '
  + '[&_a]:underline [&_a]:underline-offset-4 [&_a]:decoration-muted-foreground/50 '
  + '[&_h2]:mb-3 [&_h2]:mt-10 [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-bold [&_h2]:tracking-tight '
  + '[&_h3]:mb-2 [&_h3]:mt-7 [&_h3]:font-display [&_h3]:text-base [&_h3]:font-bold '
  + '[&_p]:mb-4 [&_li]:mb-1.5 [&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-5 '
  + '[&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-5 [&_blockquote]:border-l [&_blockquote]:border-border '
  + '[&_blockquote]:pl-4 [&_blockquote]:italic [&_table]:my-4 [&_table]:w-full [&_table]:text-sm '
  + '[&_td]:border [&_td]:border-border [&_td]:p-2 [&_th]:border [&_th]:border-border [&_th]:p-2 '
  + '[&_th]:text-left [&_img]:my-4 [&_img]:max-w-full';

interface Pedaco { tipo: 'prosa' | 'widget'; html: string; scripts: number }

/** Fatia o conteúdo nos blocos `wp:html`.
 *
 * Tem de acontecer ANTES de tirar os comentários do WordPress: são eles que
 * marcam onde o widget começa e acaba. Removê-los primeiro apagaria a fronteira
 * e o widget viraria prosa. */
export function fatiar(bruto: string): Pedaco[] {
  const partes: Pedaco[] = [];
  const RE = /<!--\s*wp:html\s*-->([\s\S]*?)<!--\s*\/wp:html\s*-->/g;
  let ultimo = 0;
  let m: RegExpExecArray | null;

  const limpar = (s: string) => s.replace(/<!--\s*\/?wp:[^>]*-->/g, '').trim();
  const contarScripts = (s: string) => (s.match(/<script/gi) || []).length;

  while ((m = RE.exec(bruto)) !== null) {
    const antes = limpar(bruto.slice(ultimo, m.index));
    if (antes) partes.push({ tipo: 'prosa', html: antes, scripts: 0 });
    partes.push({ tipo: 'widget', html: limpar(m[1]), scripts: contarScripts(m[1]) });
    ultimo = m.index + m[0].length;
  }
  const resto = limpar(bruto.slice(ultimo));
  if (resto) partes.push({ tipo: 'prosa', html: resto, scripts: 0 });
  return partes.length ? partes : [{ tipo: 'prosa', html: limpar(bruto), scripts: 0 }];
}

const Widget: React.FC<{ p: Pedaco }> = ({ p }) => {
  const limpo = useMemo(() => DOMPurify.sanitize(p.html, LIMPEZA), [p.html]);
  return (
    <figure className="my-8 max-w-[68ch]">
      <figcaption className="flex flex-wrap items-center justify-between gap-2 border border-b-0 border-border px-3 py-2">
        <span className="kicker">widget interativo</span>
        {p.scripts > 0 && (
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <ShieldAlert className="h-3 w-3" aria-hidden />
            comportamento desligado nesta prévia
          </span>
        )}
      </figcaption>
      {/* Fundo claro fixo: o widget foi escrito com estilo inline assumindo
          página branca do tema. Deixá-lo herdar o tema escuro produziria texto
          escuro sobre fundo escuro — ilegível, e por culpa da moldura, não do
          widget. */}
      <div className="overflow-x-auto border border-border bg-[#ffffff] p-1 text-[#1e293b]">
        {/* eslint-disable-next-line react/no-danger — sanitizado acima */}
        <div dangerouslySetInnerHTML={{ __html: limpo }} />
      </div>
      {p.scripts > 0 && (
        <p className="mt-2 max-w-[68ch] text-[11px] leading-relaxed text-muted-foreground">
          O código que faz este bloco responder foi removido daqui: é código
          executável escrito por IA, e o lugar de verificá-lo funcionando é o
          rascunho do WordPress.
        </p>
      )}
    </figure>
  );
};

const Prosa: React.FC<{ html: string }> = ({ html }) => {
  const limpo = useMemo(() => DOMPurify.sanitize(html, LIMPEZA), [html]);
  {/* eslint-disable-next-line react/no-danger — sanitizado acima */}
  return <div className={PROSA} dangerouslySetInnerHTML={{ __html: limpo }} />;
};

export const ProsaDaPagina: React.FC<{ bruto: string }> = ({ bruto }) => {
  const pedacos = useMemo(() => fatiar(bruto), [bruto]);
  return (
    <div>
      {pedacos.map((p, i) => (
        p.tipo === 'widget'
          ? <Widget key={i} p={p} />
          : <Prosa key={i} html={p.html} />
      ))}
    </div>
  );
};

/** A LP não é prosa: é um JSON de slots que o tema monta. Renderizá-la como
 *  artigo seria mentira sobre a estrutura; despejar o JSON cru seria ilegível.
 *  Cada slot aparece nomeado, na ordem em que o tema os usa. */
export const LpEmSlots: React.FC<{ bruto: string }> = ({ bruto }) => {
  const dados = useMemo(() => {
    try { return JSON.parse(bruto) as Record<string, unknown>; } catch { return null; }
  }, [bruto]);

  if (!dados) {
    return <pre className="max-w-[68ch] overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{bruto}</pre>;
  }

  const conteudo = (v: unknown): React.ReactNode => {
    if (Array.isArray(v)) {
      return (
        <ul className="space-y-3">
          {v.map((item, i) => (
            <li key={i} className="text-[15px] leading-relaxed">
              {typeof item === 'object' && item !== null
                ? Object.entries(item as Record<string, unknown>).map(([k, vv]) => (
                    <div key={k} className="mb-1">
                      <span className="kicker mr-2 text-muted-foreground">{k}</span>
                      <span>{String(vv)}</span>
                    </div>
                  ))
                : String(item)}
            </li>
          ))}
        </ul>
      );
    }
    if (typeof v === 'object' && v !== null) {
      return (
        <div className="space-y-1">
          {Object.entries(v as Record<string, unknown>).map(([k, vv]) => (
            <div key={k} className="text-[15px]">
              <span className="kicker mr-2 text-muted-foreground">{k}</span>{String(vv)}
            </div>
          ))}
        </div>
      );
    }
    return <p className="text-[15px] leading-relaxed">{String(v)}</p>;
  };

  return (
    <div className="max-w-[68ch] divide-y divide-border">
      {Object.entries(dados).map(([k, v]) => (
        v == null || v === '' ? null : (
          <section key={k} className="py-5 first:pt-0">
            <div className="kicker mb-2 text-muted-foreground">{k.replace(/_/g, ' ')}</div>
            {conteudo(v)}
          </section>
        )
      ))}
    </div>
  );
};
