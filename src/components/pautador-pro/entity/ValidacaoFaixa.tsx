import React from 'react';
import { cn } from '@/lib/utils';
import { alvoDeOuro, FORMATO_PAGINA, VEREDITO_PORTAO,
         type ValidacaoResumo } from '@/types/pautadorValidacao';

/**
 * A marca do card no kanban — **uma só**, no máximo duas.
 *
 * A versão anterior desenhava os dez eixos como glifos de proveniência. Custava
 * mais do que entregava: card de kanban tem um segundo, não trinta, e
 * proveniência por eixo é informação de AUDITORIA — o lugar dela é o drawer,
 * onde a barra já a resolve com trilho, cor e glifo.
 *
 * ## O que mudou, e por quê
 *
 * Antes o card ficava CALADO em três dos cinco perfis: medido, sem portão e sem
 * ouro devolvia `null`. A intenção era boa — impedir que a coluna virasse
 * ranking por medalha —, mas ela errou o alvo. `audiencia_pobre` e
 * `mercado_rico_sem_leitura` **não são melhor e pior**: são AÇÕES OPOSTAS.
 *
 *     LÊ · NÃO PAGA     ela lê, e ninguém paga por essa atenção
 *     PAGA · NÃO LÊ     paga bem, e não pagina
 *
 * Um manda desistir do tema; o outro manda mudar o formato. Esconder os dois
 * não evitava ranking — obrigava a abrir trinta cards um a um para saber o que
 * havia na coluna.
 *
 * A disciplina fica de outro jeito: os três perfis do meio usam a MESMA tinta
 * neutra e o mesmo peso. Eles se distinguem pelo texto, não por hierarquia
 * visual, e por isso continuam sendo classe e não nota. Só o ouro e o portão
 * têm cor, porque só eles mudam a decisão.
 *
 *     🎯  alvo de ouro          ⛔  portão
 *     ◑   limítrofe             ○   não medido
 *     LÊ E PAGA · LÊ · NÃO PAGA · PAGA · NÃO LÊ · INCOMPLETO
 */

const OURO = `
.val-ouro { border-color:#b8860b59; background:#b8860b1a; color:#8a6508; }
.dark .val-ouro { border-color:#d4a53a59; background:#d4a53a1f; color:#e3bd63; }
`;

/** Os perfis do quadrante, em três palavras e um GLIFO.
 *
 * O glifo entrou depois de o operador dizer que não achava esses estados na
 * tela — e ele estava certo. A regra da casa é "cor é proveniência, nunca
 * valor", e eu a apliquei demais: neutralizei a cor E a forma, e neutro demais
 * virou invisível ao lado de um ◑ laranja e de um 🎯.
 *
 * A correção separa as duas linguagens, e cada uma passa a dizer uma coisa só:
 *
 *     COR   = a decisão muda?   só o portão (vermelho) e o ouro têm.
 *     FORMA = que categoria é?  todo estado tem, e nenhuma forma é "melhor".
 *
 * Os glifos são um par de opostos legível a 8px — `◐` e `◑` são a mesma meia-lua
 * espelhada, e é exatamente essa a relação entre "lê e não paga" e "paga e não
 * lê". `◆` cheio para os dois lados altos, `◇` vazio para o incompleto. */
const PERFIL_CURTO: Record<string, { glifo: string; texto: string; ajuda: string }> = {
  alvo: {
    glifo: '◆',
    texto: 'lê e paga',
    ajuda: 'Demanda humana e mercado, os dois acima do corte. Não chegou a ouro — abra para ver o que faltou.',
  },
  audiencia_pobre: {
    glifo: '◐',
    texto: 'lê · não paga',
    ajuda: 'A pessoa lê, e o mercado não paga por essa atenção. O tema sustenta página e não sustenta leilão.',
  },
  mercado_rico_sem_leitura: {
    glifo: '◑',
    texto: 'paga · não lê',
    ajuda: 'Paga bem, e como ARTIGO não paginaria. Não é veto: é indicação de formato — a página precisa segurar atenção (calculadora, simulador, comparador) em vez de entregar o dado e acabar.',
  },
  indefinido: {
    glifo: '◇',
    texto: 'incompleto',
    ajuda: 'Faltam eixos de uma das famílias para cruzar leitura × mercado. Meça de novo.',
  },
};

/**
 * A PLANTA, em um bloco por pergunta.
 *
 * Ela só aparece quando há **pelo menos uma ferramenta**, e essa restrição é o
 * desenho, não uma economia. O card já carrega tier, vertical, perfil e às
 * vezes portão; mais um elemento permanente seria ruído. O que muda a decisão
 * de PEGAR o card é uma coisa só: "este exige widget", porque isso é pergunta
 * de capacidade do mês, não de mérito do tema.
 *
 * Quando não há ferramenta, o card não diz nada de formato — a planta inteira
 * está no drawer, que é onde se executa.
 */
/* O hue do MEDIDO, com a variante de dark mode. Ele vive aqui e não em `.val`
   porque o card do kanban está fora do escopo do painel — usar o valor claro
   fixo daria azul escuro sobre card escuro, que some. */
const PLANTA = `
.val-planta { --p: oklch(.55 .152 253); }
.dark .val-planta { --p: oklch(.74 .132 214); }
.val-planta { border-color: color-mix(in oklch, var(--p) 32%, transparent);
              background: color-mix(in oklch, var(--p) 7%, transparent); }
.val-planta-f { color: var(--p); }
`;

const Planta: React.FC<{ validacao: ValidacaoResumo }> = ({ validacao }) => {
  const fmts = validacao.portao?.formatos;
  const perguntas = validacao.ficha?.perguntas ?? [];
  if (!fmts?.n_ferramenta || !perguntas.length) return null;

  return (
    <>
    <style>{PLANTA}</style>
    <span
      className="val-planta text-[8px] rounded px-1 py-0.5 border leading-none shrink-0
                 inline-flex items-center gap-[3px] tabular"
      title={`Esta entidade rende ${fmts.n_artigo ?? 0} página(s) de artigo e `
        + `${fmts.n_ferramenta} com ferramenta`
        + ((fmts.n_nao_produzir ?? 0) > 0 ? `, e ${fmts.n_nao_produzir} fora.` : '.')
        + '\n\nFerramenta = a página precisa de entrada manipulável (calculadora, '
        + 'simulador ou filtro). Abra o card para ver os campos, que já vêm nomeados.'}
    >
      {perguntas.map((q, i) => {
        const fmt = q.formato
          ?? (q.engajamento === 'dado_unico' ? 'nao_produzir' : 'artigo');
        return (
          <span key={i} aria-hidden
                className={cn('leading-none',
                  fmt === 'artigo_com_ferramenta' ? 'val-planta-f'
                    : fmt === 'artigo' ? 'text-foreground/40' : 'text-muted-foreground/30')}>
            {FORMATO_PAGINA[fmt]?.glifo ?? '·'}
          </span>
        );
      })}
      <span className="ml-[1px] text-muted-foreground">
        {fmts.n_ferramenta}&nbsp;ferramenta{fmts.n_ferramenta > 1 ? 's' : ''}
      </span>
    </span>
    </>
  );
};

export const ValidacaoMarca: React.FC<{ validacao?: ValidacaoResumo | null }> = ({ validacao }) => {
  if (!validacao) {
    return (
      <span className="text-[8px] rounded px-1 py-0.5 border border-border bg-muted/40 text-muted-foreground/70 leading-none shrink-0"
            title="Ainda não medido. Arraste para Em validação — ou meça a coluna inteira, que é mais barato.">
        ○ não medido
      </span>
    );
  }

  const veredito = validacao.portao?.veredito;
  if (veredito === 'portao' || veredito === 'limitrofe') {
    const v = VEREDITO_PORTAO[veredito];
    return (
      <>
      <span
        className={cn('text-[8px] rounded px-1 py-0.5 border leading-none shrink-0',
          veredito === 'portao'
            ? 'border-destructive/30 bg-destructive/10 text-destructive'
            : 'border-warning/30 bg-warning/10 text-warning')}
        title={`${v.corpo}\n${v.rodape}`}
      >
        {v.simbolo} {veredito === 'portao' ? 'portão' : 'limítrofe'}
      </span>
      <Planta validacao={validacao} />
      </>
    );
  }

  const ouro = alvoDeOuro(validacao);
  if (ouro.e) {
    return (
      <>
        <style>{OURO}</style>
        <span
          className="val-ouro text-[8px] rounded px-1 py-0.5 border leading-none shrink-0"
          title={`Alvo de ouro — ${ouro.motivo}`}
        >
          🎯 alvo de ouro
        </span>
        <Planta validacao={validacao} />
      </>
    );
  }

  // ── os quatro do meio: GLIFO para achar, tinta neutra para não ranquear ──
  //
  // Preenchimento leve e borda de 1px, no `label-tech` do design da VOLC (caixa
  // alta, tracking largo). O glifo dá o alvo para o olho; a ausência de cor
  // impede que ele compita com o portão e com o ouro, que são os dois únicos
  // estados que mudam a decisão.
  const p = PERFIL_CURTO[validacao.perfil ?? 'indefinido'];
  if (!p) return <Planta validacao={validacao} />;

  return (
    <>
    <span
      className="text-[8px] rounded px-1 py-0.5 border border-border bg-muted/30 leading-none shrink-0
                 uppercase tracking-[.09em] text-muted-foreground
                 inline-flex items-center gap-1"
      title={`${p.ajuda}${ouro.motivo ? `\n\nPara ouro faltou: ${ouro.motivo}` : ''}`}
    >
      <span aria-hidden className="text-[9px] leading-none text-foreground/55">{p.glifo}</span>
      {p.texto}
    </span>
    <Planta validacao={validacao} />
    </>
  );
};
