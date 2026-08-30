/**
 * O que a tela pode oferecer num canal — derivado do MANIFESTO, e só dele.
 *
 * ## Por que nunca de uma lista de canais
 *
 * Uma lista de canais no cliente responde "quais canais existem", que é outra
 * pergunta. Quatro canais na lista viram quatro botões de "criar" quando existe
 * um único construtor, e o operador descobre a ausência depois de montar o
 * pedido inteiro. O manifesto responde a pergunta certa: o que ESTE canal sabe
 * fazer, declarado pelo backend.
 *
 * ## As três respostas, que são três fatos diferentes
 *
 *  - `manifesto: null` — o Hub NÃO OPERA este canal. Vídeo e Shopping aparecem
 *    no inventário e não têm construtor. É afirmação, não falta de dado.
 *  - manifesto com `capacidades: []` — o Hub opera o canal e não pode nada nele.
 *  - manifesto com capacidades — o que dá para fazer, item a item.
 *
 * Um manifesto vazio renderizado como "não operado" apagaria a diferença entre
 * "não é conosco" e "é conosco e está tudo travado", que levam a lugares
 * diferentes: a primeira ao painel do Google, a segunda a quem cuida do Hub.
 *
 * Módulo puro. Sem React, sem HTTP, sem Google Ads.
 */
import type { CapacidadeDeAcao, ManifestoDeCanal } from '@/types/trafego';
import type { CapacidadeDoCanal } from '@/types/diagnostico';

/** A capacidade em linguagem de operação. Vocabulário fechado do contrato. */
export const PALAVRA_DA_CAPACIDADE: Record<CapacidadeDeAcao, string> = {
  ler: 'ler a conta e mostrar o que existe',
  propor: 'propor mudança para uma pessoa aprovar',
  escrever: 'escrever na conta de anúncio',
};

export function palavraDaCapacidade(valor: string): string {
  return (
    PALAVRA_DA_CAPACIDADE[valor as CapacidadeDeAcao] ??
    `${valor.toLowerCase()} (capacidade não reconhecida)`
  );
}

export function capacidadesDoCanal(manifesto: ManifestoDeCanal | null): CapacidadeDoCanal {
  if (manifesto == null) {
    return {
      tipo: 'nao_operado',
      frase:
        'este canal aparece no inventário e o Hub não o opera. Não há construtor, ' +
        'não há proposta e não há leitura própria — o que existe dele está no ' +
        'painel do Google.',
    };
  }

  if (manifesto.capacidades.length === 0) {
    return {
      tipo: 'sem_capacidade',
      rotulo: manifesto.rotulo,
      frase:
        'o Hub opera este canal e não declara nenhuma capacidade nele agora. É ' +
        'diferente de não operar: aqui há um dono, e ele diz que não pode nada.',
    };
  }

  const sabeProvar = manifesto.sabe_provar ?? manifesto.sabe_criar;
  const recusaDeCriacao = manifesto.indisponibilidades.find((frase) =>
    /criaç|mutação real|\/subir/i.test(frase),
  ) ?? manifesto.indisponibilidades[0];

  return {
    tipo: 'operado',
    rotulo: manifesto.rotulo,
    capacidades: manifesto.capacidades.map(palavraDaCapacidade),
    sabe_criar: manifesto.sabe_criar,
    recusa: manifesto.sabe_criar
      ? null
      : (recusaDeCriacao ??
        'este canal não tem construtor nesta versão do Hub'),
    // ⚠️ Quando o canal SABE criar, `indisponibilidades` deixa de ser o motivo
    // da recusa e passa a ser a lista do que a primeira fatia dele não monta.
    // Enquanto os dois sentidos dividiam o campo `recusa`, `sabe_criar: true`
    // devolvia `null` e as cinco limitações declaradas do Display — sem
    // segmentação, sem placement positivo, sem sitelink, sem lance manual,
    // keywords não viram critério — nunca chegavam a nenhuma tela.
    limites: sabeProvar ? manifesto.indisponibilidades : [],
    provas_obrigatorias: manifesto.provas_obrigatorias,
  };
}

/**
 * Os campos que o construtor deste canal pede.
 *
 * `campos_do_pedido` vazio significa que NÃO HÁ formulário para desenhar. Uma
 * tela que inventasse campos por simetria com Search montaria um pedido que o
 * backend não sabe receber.
 */
export function temFormulario(manifesto: ManifestoDeCanal | null): boolean {
  return manifesto != null && manifesto.campos_do_pedido.length > 0;
}
