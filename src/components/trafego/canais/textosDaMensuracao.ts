/**
 * As frases da mensuração que não são componente.
 *
 * ## Por que elas saíram do `PainelDaMensuracao.tsx`
 *
 * Elas eram os dois únicos exports não-componentes daquele arquivo, e o eslint
 * cobrava exatamente isso (`react-refresh/only-export-components`, duas
 * advertências, as únicas do módulo). Traduzir estado do servidor em frase é
 * lógica pura, testável sem DOM, e não pertence a um arquivo de JSX.
 *
 * ⚠️ `PainelDaMensuracao.tsx` continua re-exportando as duas: quem as consome
 * hoje (`__tests__/painel-da-mensuracao.test.tsx:41-45`) importa de lá, e
 * quebrar o caminho de import só para arrumar a casa trocaria um problema de
 * organização por um de compatibilidade.
 */
import type { PlanoDeMensuracao } from '@/lib/trafego/canais';

/**
 * Quando chegou a última conversão — em três frases que não se confundem.
 *
 * ⚠️ `conversoes_na_janela === 0` com `vazio_confirmado` é um zero MEDIDO: a
 * ação existe, a janela foi consultada e nada chegou. É um fato caro, e escrevê-lo
 * como "sem dados" jogaria fora justamente a informação que custou a consulta.
 */
export function textoDoUltimoMomento(plano: PlanoDeMensuracao): string {
  const f = plano.frescor;
  if (f.estado === 'vazio_confirmado') {
    return 'nenhuma conversão — zero MEDIDO, não ausência de leitura';
  }
  if (f.estado === 'falhou') return 'a leitura do frescor falhou';
  if (f.estado === 'nao_coletado') return 'ninguém leu o frescor desta conta';
  if (f.estado === 'inelegivel') return 'a pergunta não cabe nesta conta';
  if (f.estado === 'nao_suportado') return 'a API não suporta esta leitura aqui';
  if (!f.ultima_conversao_em) return 'leitura parcial: sem data da última conversão';
  const dias =
    // ⚠️ `null` NUNCA vira um número grande. "Faz muito tempo" e "não sei" são
    // coisas diferentes, e um `999` viraria um gráfico com cara de dado.
    f.dias_desde_a_ultima === null
      ? 'há quantos dias, não se sabe'
      : `há ${f.dias_desde_a_ultima} d`;
  return `${f.ultima_conversao_em} (${dias})`;
}

/**
 * A meta é da conta ou da campanha? E foi LIDA ou INFERIDA?
 *
 * ⚠️ As duas perguntas viajam juntas porque a resposta honesta muda com as
 * duas. Antes do nascimento o nível é INFERIDO pela herança documentada — a
 * campanha não existe e o recurso não pode ser consultado —, e chamar isso de
 * "lido" afirmaria uma consulta que ninguém fez.
 */
export function textoDaProcedenciaDaMeta(plano: PlanoDeMensuracao): string {
  const m = plano.meta_efetiva;
  if (m.usa_meta_customizada) {
    return 'meta CUSTOMIZADA: ela não respeita primary_for_goal e este sistema não lê o recurso dela';
  }
  if (!m.nivel_decidido) {
    return 'não se sabe qual nível manda';
  }
  const onde = m.nivel === 'CAMPAIGN' ? 'da campanha' : 'herdada da conta';
  return m.nivel_herdado
    ? `${onde} — INFERIDA pela herança documentada, não lida do recurso`
    : `${onde} — lida do recurso`;
}
