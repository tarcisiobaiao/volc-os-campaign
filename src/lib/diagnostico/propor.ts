/**
 * Da escada para a caixa: o que a evidência sustenta propor.
 *
 * ## A regra que governa este arquivo
 *
 * Só um degrau APURADO gera proposta. Um degrau `nao_apurado` não produz
 * recomendação nenhuma — propor mudança a partir de uma leitura que falhou é a
 * forma mais direta de esta ferramenta gastar dinheiro por engano.
 *
 * E só o degrau que o veredito alcança gera proposta: com a campanha pausada, a
 * proposta é ligar, e não subir a verba de uma campanha que não está no leilão.
 * A escada é causal, e a caixa herda a causalidade.
 *
 * ## Toda proposta nasce bloqueada
 *
 * `bloqueio` é preenchido com a dependência real: não existe endereço seguro
 * para aplicar mudança na conta de anúncio a partir desta tela. Quando existir,
 * é aqui que a condição muda — em um lugar, não em cada componente.
 *
 * Módulo puro: sem React, sem HTTP, sem Google Ads.
 */
import type {
  CaixaDePropostas,
  DegrauDeEntrega,
  DependenciaDeAplicacao,
  DiagnosticoDeEntrega,
  Proposta,
} from '@/types/diagnostico';
import { dinheiro } from '@/components/trafego/inventario/formato';

import { vereditoDaEscada } from './escada';

/**
 * A dependência de hoje. Uma constante, e não uma frase repetida: quando o
 * endereço existir, some daqui e some de todas as propostas de uma vez.
 */
export const SEM_ENDERECO_SEGURO: DependenciaDeAplicacao = {
  dependencia:
    'aplicar esta mudança na conta de anúncio passa por um endereço privilegiado que ainda não está ligado. Esta tela abre a revisão e para aí.',
  destrava: 'endpoint',
};

function semAprovacao() {
  return {
    estado: 'nao_submetida' as const,
    por: null,
    em: null,
    impressao: null,
    motivo: null,
    vale_ate: null,
  };
}

function valorDaEvidencia(degrau: DegrauDeEntrega, campo: string): string | null {
  return degrau.evidencias.find((e) => e.campo === campo)?.valor ?? null;
}

/**
 * Propõe o que a escada sustenta.
 *
 * `leitura` acompanha o diagnóstico: caixa sem leitura é caixa que não foi
 * apurada, e não caixa vazia.
 */
export function proporMudancas(diagnostico: DiagnosticoDeEntrega): CaixaDePropostas {
  const veredito = vereditoDaEscada(diagnostico.degraus);
  const propostas: Proposta[] = [];

  // Sem veredito apurado não há proposta nenhuma. É o ponto do arquivo.
  if (veredito.tipo === 'nao_apurado') {
    return {
      versao: diagnostico.versao,
      volc_campaign_id: diagnostico.volc_campaign_id,
      propostas: [],
      leitura: diagnostico.leitura,
    };
  }

  const porEixo = new Map(diagnostico.degraus.map((d) => [d.eixo, d]));

  if (veredito.tipo === 'bloqueada' && veredito.eixo === 'campanha') {
    const d = porEixo.get('campanha');
    if (d && d.palavra === 'pausada') {
      propostas.push({
        id: 'ligar-campanha',
        alvo: 'status',
        titulo: 'Ligar a campanha',
        frase:
          'a campanha está pausada e tudo abaixo dela foi apurado sem impedimento. ' +
          'Ligar é o que a coloca no leilão — e é o que a faz gastar.',
        eixo: 'campanha',
        evidencias: d.evidencias,
        confianca: 'alta',
        amostra: {
          n: null,
          unidade: 'estado observado na conta',
          janela: 'leitura atual',
          insuficiente: false,
        },
        diff: {
          linhas: [
            {
              rotulo: 'estado da campanha',
              antes: valorDaEvidencia(d, 'campaign.status'),
              depois: 'ENABLED',
              delta: null,
            },
          ],
          inalterado: ['orçamento', 'lance', 'keywords', 'anúncios'],
          gasto_diario: null,
        },
        aprovacao: semAprovacao(),
        bloqueio: SEM_ENDERECO_SEGURO,
      });
    }
  }

  if (veredito.tipo === 'limitada') {
    const orcamento = porEixo.get('orcamento');
    if (orcamento?.estado === 'limita') {
      const atual = valorDaEvidencia(orcamento, 'campaign_budget.amount_micros');
      const perdida = valorDaEvidencia(
        orcamento,
        'metrics.search_budget_lost_impression_share',
      );
      propostas.push({
        id: 'subir-verba',
        alvo: 'orcamento',
        titulo: 'Subir a verba diária',
        frase: `a campanha perdeu ${perdida ?? 'parte'} dos leilões por falta de verba. Há demanda que a verba atual não alcança.`,
        eixo: 'orcamento',
        evidencias: orcamento.evidencias,
        confianca: 'alta',
        amostra: {
          n: null,
          unidade: 'medida agregada da janela',
          janela: diagnostico.janela,
          // ⚠️ A parcela perdida por verba é agregada: ela não diz em quantos
          // dias a verba estourou. Declarar isso é o que impede a proposta de
          // parecer mais forte do que é.
          insuficiente: true,
        },
        diff: {
          linhas: [
            { rotulo: 'verba diária', antes: atual, depois: null, delta: null },
            {
              rotulo: 'leilões perdidos por verba',
              antes: perdida,
              depois: null,
              delta: null,
            },
          ],
          inalterado: ['lance', 'keywords', 'anúncios', 'segmentação'],
          gasto_diario: null,
        },
        aprovacao: semAprovacao(),
        bloqueio: SEM_ENDERECO_SEGURO,
      });
    }

    const leilao = porEixo.get('leilao');
    if (leilao?.estado === 'limita') {
      const perdaRank = valorDaEvidencia(
        leilao,
        'metrics.search_rank_lost_impression_share',
      );
      propostas.push({
        id: 'rever-lance',
        alvo: 'lance',
        titulo: 'Rever o lance',
        frase: `a campanha perdeu ${perdaRank ?? 'parte'} dos leilões por posição. Lance ou qualidade abaixo do necessário para aparecer.`,
        eixo: 'leilao',
        evidencias: leilao.evidencias,
        // Perda por posição tem duas causas — lance e qualidade — e esta
        // evidência não separa as duas. Mexer no lance pode não resolver.
        confianca: 'media',
        amostra: {
          n: null,
          unidade: 'medida agregada da janela',
          janela: diagnostico.janela,
          insuficiente: true,
        },
        diff: {
          linhas: [
            {
              rotulo: 'leilões perdidos por posição',
              antes: perdaRank,
              depois: null,
              delta: null,
            },
          ],
          inalterado: ['orçamento', 'segmentação'],
          gasto_diario: null,
        },
        aprovacao: semAprovacao(),
        bloqueio: SEM_ENDERECO_SEGURO,
      });
    }
  }

  return {
    versao: diagnostico.versao,
    volc_campaign_id: diagnostico.volc_campaign_id,
    propostas,
    leitura: diagnostico.leitura,
  };
}

/** O diff de uma proposta de verba com o valor que o operador digitou. */
export function comValorProposto(
  proposta: Proposta,
  micros: number | null,
  moeda: string | null,
): Proposta {
  if (proposta.alvo !== 'orcamento') return proposta;
  return {
    ...proposta,
    diff: {
      ...proposta.diff,
      linhas: proposta.diff.linhas.map((l, i) =>
        i === 0 ? { ...l, depois: micros == null ? null : dinheiro(micros, moeda) } : l,
      ),
    },
  };
}
