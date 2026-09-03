/**
 * Harness de validação visual — dev only, fora do roteamento do app.
 *
 * A página real (`/pautador-pro`) está atrás de `ProtectedRoute` e exige o
 * Supabase oficial, que esta missão está proibida de tocar. Este harness
 * renderiza os MESMOS componentes com fixtures, em todos os estados que a
 * missão manda validar, para produzir um recibo reproduzível.
 *
 * Ele não é importado por `App.tsx` e não entra no bundle de produção.
 *
 *     ./node_modules/.bin/vite --port 5199
 *     abrir http://localhost:5199/harness.html
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { TeseDaOportunidade } from '@/components/pautador-pro/entity/TeseDaOportunidade';
import { ComparadorDeOportunidades } from '@/components/pautador-pro/entity/ComparadorDeOportunidades';
import type { TeseDeOportunidade, TesesResposta } from '@/types/pautadorOportunidade';
import '@/index.css';

const base = (o: Partial<TeseDeOportunidade> = {}): TeseDeOportunidade => ({
  opportunity_id: 1,
  tema: 'Saque-aniversário',
  decisao: 'aprofundar',
  porque: 'Ramifica de verdade: até 3 caminhos que levam a ações diferentes e até 3 condições pessoais que mudam a resposta. É isso que uma página só não resolve.',
  versao_do_contrato: 'oportunidade/1',
  formato_de_funil: 'ferramenta_de_elegibilidade',
  observaveis_do_formato: ['max condicoes_pessoais 3', 'max ramos_de_acao 3', 'decisao_apos_resposta em 3 de 4 perguntas'],
  fatos: [
    'volume (demanda medida): alto — medido por sensor',
    'engajamento (a resposta esgota ou sustenta): sustenta — contado pelo modelo, derivado em Python',
    'perguntas lidas: 4',
    'oficial_fecha_sozinho em 1 de 4 perguntas',
  ],
  hipoteses: [],
  desconhecidos: [],
  contradicoes: [],
  proximo_experimento: null,
  indice_citado: 0.724,
  cobertura: 1.0,
  perfil_citado: 'alvo',
  comparavel: true,
  motivo_incomparavel: null,
  ...o,
});

const ESTADOS: { titulo: string; nota: string; no: React.ReactNode }[] = [
  {
    titulo: 'PRONTO · aprofundar',
    nota: 'Tudo medido. Zero desconhecidos, zero hipóteses, zero contradições.',
    no: <TeseDaOportunidade tese={base()} />,
  },
  {
    titulo: 'AUSENTE · experimentar com buraco declarado',
    nota: 'Um sensor faltou. Vira desconhecido e propõe o experimento — nunca zero.',
    no: <TeseDaOportunidade tese={base({
      decisao: 'experimentar',
      porque: 'Ramifica de verdade: até 3 caminhos e até 3 condições pessoais. Faltam 2 observáveis — feche o barato primeiro.',
      fatos: ['engajamento: sustenta — contado pelo modelo, derivado em Python', 'perguntas lidas: 4'],
      desconhecidos: [
        'volume (demanda medida): não medido — sem_credencial_dataforseo',
        'vacuo (espaço editorial): não medido — sem_trafego',
      ],
      proximo_experimento: 'Medir volume: é o observável ausente mais barato de fechar e o que mais muda a leitura deste card.',
      cobertura: 0.75, indice_citado: 0.681,
    })} />,
  },
  {
    titulo: 'BLOQUEADO · o balcão oficial já resolve',
    nota: 'Veto do roteador. Sem formato, e o motivo é o observável, não falta de dado.',
    no: <TeseDaOportunidade tese={base({
      tema: 'Consulta de CPF',
      decisao: 'inadequado',
      porque: 'O canal oficial fecha todas as 4 perguntas sozinho. Uma página aqui repete o balcão sem acrescentar nada — não há funil a construir.',
      formato_de_funil: null, observaveis_do_formato: [],
      fatos: ['oficial_fecha_sozinho em 4 de 4 perguntas', 'perguntas lidas: 4'],
      indice_citado: 0.0, perfil_citado: 'descartar',
    })} />,
  },
  {
    titulo: 'CONTRADIÇÃO · dois sinais discordam',
    nota: 'Ninguém resolveu em silêncio. O bloco aparece primeiro, destacado.',
    no: <TeseDaOportunidade tese={base({
      decisao: 'insuficiente',
      contradicoes: [
        'o resumo diz apto=true mas há portão disparado: engajamento',
        'portão disparado (engajamento) com índice 0.72 acima de zero',
      ],
      hipoteses: ['[prior webgo/ramificacao-cosmetica · confiança media · controle parcial] Rótulo de escolha não é ramo. No corpus, a mediana é 3 rótulos por página contra 1 destino real.'],
      desconhecidos: ['opacidade (quão clara é a regra oficial): não medido — ficha_invalida'],
      proximo_experimento: 'Medir opacidade: é o observável ausente mais barato de fechar.',
    })} />,
  },
  {
    titulo: 'RETIDO · sem base para comparar',
    nota: 'Cobertura abaixo do mínimo. Não entra no ranking e diz por quê.',
    no: <TeseDaOportunidade tese={base({
      tema: 'Tema recém-descoberto',
      decisao: 'retido',
      porque: 'Cobertura de 30% — abaixo de 50%, a média fala de meia dúzia de eixos e chama isso de retrato do tema. Medir antes de comparar.',
      cobertura: 0.3, indice_citado: 0.91,
      comparavel: false, motivo_incomparavel: 'cobertura 0.3 abaixo do mínimo 0.5',
      // Disjunção: o que está em `desconhecidos` NÃO pode estar em `fatos`.
      // O backend garante isso por construção (CP#13); a fixture respeita.
      fatos: ['engajamento (a resposta esgota ou sustenta): sustenta — contado pelo modelo, derivado em Python',
              'perguntas lidas: 4'],
      desconhecidos: ['volume (demanda medida): não medido — nao_medido',
                      'reposicao (renovação do público): não medido — nao_medido',
                      'vacuo (espaço editorial): não medido — nao_medido',
                      'densidade (setores que falariam com essa audiência): não medido — nao_medido'],
      proximo_experimento: 'Medir volume: é o observável ausente mais barato de fechar.',
    })} />,
  },
  {
    titulo: 'SEM VALIDAÇÃO · card legado',
    nota: 'Lacuna declarada, não veredito. Índice e cobertura mostram "—", nunca 0.',
    no: <TeseDaOportunidade tese={base({
      tema: 'Card de antes da medição',
      decisao: 'sem_validacao',
      porque: 'Este card não passou pela coluna de validação, ou passou numa versão anterior do motor. Não é um veredito sobre o tema.',
      formato_de_funil: null, observaveis_do_formato: [],
      fatos: [], indice_citado: null, cobertura: null, perfil_citado: null,
      comparavel: false, motivo_incomparavel: 'sem medição registrada',
    })} />,
  },
];

const RESPOSTA: TesesResposta = {
  total: 5, teses: [],
  ranking: [
    base({ opportunity_id: 1, tema: 'Saque-aniversário', decisao: 'aprofundar', indice_citado: 0.724, cobertura: 1.0 }),
    base({ opportunity_id: 2, tema: 'Auxílio-doença', decisao: 'aprofundar', indice_citado: 0.688, cobertura: 0.875,
           formato_de_funil: 'comparador_de_caminhos' }),
    base({ opportunity_id: 3, tema: 'Seguro-desemprego', decisao: 'experimentar', indice_citado: 0.641, cobertura: 0.75,
           desconhecidos: ['volume: não medido'] }),
    base({ opportunity_id: 4, tema: 'Consulta de CPF', decisao: 'inadequado', indice_citado: 0.0,
           formato_de_funil: null, cobertura: 1.0 }),
  ],
  fora_do_ranking: [
    base({ opportunity_id: 5, tema: 'Tema recém-descoberto', decisao: 'retido', comparavel: false,
           cobertura: 0.3, motivo_incomparavel: 'cobertura 0.3 abaixo do mínimo 0.5' }),
    base({ opportunity_id: 6, tema: 'Card de antes da medição', decisao: 'sem_validacao', comparavel: false,
           cobertura: null, indice_citado: null, motivo_incomparavel: 'sem medição registrada' }),
  ],
};

function Secao({ titulo, nota, children }: { titulo: string; nota: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={{ font: '600 11px/1.2 Inter, system-ui', letterSpacing: '.1em',
                   textTransform: 'uppercase', color: 'hsl(var(--muted-foreground))', margin: '0 0 2px' }}>
        {titulo}
      </h2>
      <p style={{ font: '400 11px/1.4 Inter, system-ui', color: 'hsl(var(--muted-foreground))',
                  margin: '0 0 8px', maxWidth: '70ch' }}>{nota}</p>
      {children}
    </section>
  );
}

function App() {
  // `?so=comparador` isola a comparação para captura; `?so=tese` isola a tese.
  const q = new URLSearchParams(location.search);
  const so = q.get('so');
  const mostraTese = so !== 'comparador';
  const mostraComparador = so !== 'tese';
  // `?w=390` fixa a LARGURA DO CONTAINER. O headless do Chrome no macOS tem
  // piso de 500px de viewport, então medir mobile pelo tamanho da janela mede
  // o recorte da imagem, não o layout. Constranger o container mede o
  // componente, que é o que precisa responder.
  const largura = q.get('w') ? Number(q.get('w')) : undefined;
  return (
    <div style={{ padding: 20, maxWidth: largura ?? 880, width: largura, margin: '0 auto',
                  outline: largura ? '1px dashed hsl(var(--border))' : undefined }}>
      <h1 style={{ font: '700 24px/1.1 "Space Grotesk", Inter, system-ui',
                   letterSpacing: '-0.02em', margin: '0 0 4px' }}>
        Harness · tese e comparação
      </h1>
      <p style={{ font: '400 12px/1.5 Inter, system-ui', color: 'hsl(var(--muted-foreground))',
                  margin: '0 0 24px', maxWidth: '70ch' }}>
        Componentes reais, dados de fixture. Fora do roteamento do app.
      </p>
      {mostraTese && ESTADOS.map((e) => <Secao key={e.titulo} titulo={e.titulo} nota={e.nota}>{e.no}</Secao>)}

      {mostraComparador && <>
      <Secao titulo="COMPARAÇÃO · pronto" nota="Tabela, não grade. O incomparável aparece embaixo com o motivo.">
        <ComparadorDeOportunidades dados={RESPOSTA} selecionadaId={2} onSelecionar={() => {}} />
      </Secao>
      <Secao titulo="COMPARAÇÃO · carregando" nota="Esqueleto que preserva o layout, não spinner no meio do conteúdo.">
        <ComparadorDeOportunidades carregando />
      </Secao>
      <Secao titulo="COMPARAÇÃO · falha" nota="Não apaga o que estava na tela sem explicar a idade do dado.">
        <ComparadorDeOportunidades erro="tempo esgotado ao ler as teses" />
      </Secao>
      <Secao titulo="COMPARAÇÃO · vazio" nota="Ensina a interface em vez de dizer 'nada aqui'.">
        <ComparadorDeOportunidades dados={{ teses: [], ranking: [], fora_do_ranking: [], total: 0 }} />
      </Secao>
      </>}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

/**
 * DIAGNÓSTICO DE OVERFLOW — o recibo mede em vez de eu olhar o screenshot.
 *
 * O contrato de design exige que conteúdo largo role dentro do PRÓPRIO
 * container (`overflow-x-auto`) e que o body NUNCA role na horizontal.
 * Isto imprime os dois números no canto e nomeia o primeiro elemento que
 * estoura, se houver.
 */
// ⚠️ `setTimeout`, e NÃO `requestAnimationFrame`.
//
// `createRoot().render()` do React 18 commita de forma assíncrona: um RAF
// disparado logo depois roda ANTES do commit e mede um DOM vazio. A primeira
// versão deste diagnóstico fez exatamente isso e reportou
// `contraste: 0 medidos, 0 abaixo do piso` — que parecia aprovação e era
// medição de nada. Um gate que mede zero elementos não é um gate verde.
setTimeout(() => {
  const vw = document.documentElement.clientWidth;
  const sw = document.documentElement.scrollWidth;
  const estouram: string[] = [];
  document.querySelectorAll<HTMLElement>('#root *').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > vw + 1) {
      const dentroDeScroller = el.closest('.overflow-x-auto');
      if (!dentroDeScroller) {
        estouram.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().slice(0, 40)} right=${Math.round(r.right)}`);
      }
    }
  });
  // ── contraste medido, não estimado ───────────────────────────────────────
  // WCAG 2.2: 4.5:1 para texto normal, 3:1 para texto grande (>=18.66px bold
  // ou >=24px). Mede o que o navegador REALMENTE pintou.
  // ⚠️ COMPOSIÇÃO DE ALFA. Sem ela, `bg-info/[.07]` é lido na força cheia e o
  // contraste de um rótulo `text-info` sobre ele sai 1.00 — o probe acusaria
  // 26 reprovações que são artefato dele mesmo, não do desenho.
  type RGB = [number, number, number];
  const rgb = (c: string): [RGB, number] => {
    const m = (c.match(/[\d.]+/g) || ['0', '0', '0']).map(Number);
    return [[m[0], m[1], m[2]], m.length > 3 ? m[3] : 1];
  };
  const sobre = (frente: RGB, a: number, fundo: RGB): RGB =>
    [0, 1, 2].map((i) => frente[i] * a + fundo[i] * (1 - a)) as RGB;
  const lum = (c: RGB) => {
    const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  /** Pinta as camadas de fundo de baixo para cima, respeitando o alfa. */
  const fundoDe = (el: Element): RGB => {
    const pilha: [RGB, number][] = [];
    let n: Element | null = el;
    while (n) {
      const [c, a] = rgb(getComputedStyle(n).backgroundColor);
      if (a > 0) pilha.push([c, a]);
      n = n.parentElement;
    }
    let base: RGB = [255, 255, 255];
    for (let i = pilha.length - 1; i >= 0; i--) base = sobre(pilha[i][0], pilha[i][1], base);
    return base;
  };
  const razao = (el: Element) => {
    const cs = getComputedStyle(el);
    const fundo = fundoDe(el);
    const [cor, alfa] = rgb(cs.color);
    const a = lum(sobre(cor, alfa, fundo)), b = lum(fundo);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
  const reprovados: string[] = [];
  let medidos = 0;
  const todos = Array.from(document.querySelectorAll<HTMLElement>('#root *'));
  const folhas = todos.filter((el) => el.children.length === 0 && !!el.textContent?.trim());
  folhas.forEach((el) => {
    // WCAG 1.4.3 isenta conteúdo puramente decorativo. Glifo marcado
    // `aria-hidden` não carrega significado — o significado está na palavra ao
    // lado, que É medida. Isentar aqui é seguir a norma, não afrouxar o gate.
    if (el.closest('[aria-hidden="true"]')) return;
    const cs = getComputedStyle(el);
    const px = parseFloat(cs.fontSize);
    const grande = px >= 24 || (px >= 18.66 && Number(cs.fontWeight) >= 700);
    const piso = grande ? 3 : 4.5;
    const r = razao(el);
    medidos++;
    if (r < piso) reprovados.push(`${r.toFixed(2)}<${piso} ${px}px "${el.textContent.trim().slice(0, 34)}"`);
  });

  const box = document.createElement('pre');
  box.id = 'diag';
  box.style.cssText = 'position:fixed;left:0;bottom:0;z-index:9999;margin:0;padding:6px 8px;'
    + 'font:11px/1.35 ui-monospace,monospace;background:#111;color:#0f0;max-width:100%;white-space:pre-wrap';
  box.textContent =
    `viewport=${vw}  scrollWidth=${sw}  body_rola_horizontal=${sw > vw + 1}\n`
    + `elementos_fora_de_scroller_que_estouram=${estouram.length}`
    + (estouram.length ? `\n  ${estouram.slice(0, 5).join('\n  ')}` : '')
    + `\nnos=${todos.length} folhas_com_texto=${folhas.length}`
    + `\ncontraste: ${medidos} medidos, ${reprovados.length} abaixo do piso WCAG`
    + (reprovados.length ? `\n  ${reprovados.slice(0, 8).join('\n  ')}` : '');
  document.body.appendChild(box);
}, 1200);
