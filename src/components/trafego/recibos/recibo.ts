/**
 * A leitura de um recibo de lançamento.
 *
 * O formato é o que `volc_ads` grava em `volc_ads/dados/recibos/*.json`, lido
 * dos cinco recibos reais existentes — não inventado. Os cinco são `ACEITO`
 * com `falha: null`, o que significa que **o ramo de falha não tem amostra
 * observada**. Por isso a leitura aqui é tolerante em vez de estrita: assumir a
 * forma de um erro que nunca se viu produz uma tela que quebra exatamente no
 * primeiro erro real, que é quando ela mais precisa funcionar.
 */
import type { Aprovacao, FalhaDoRecibo, OperacaoCriada, Recibo } from '@/types/diagnostico';

function texto(v: unknown): string | null {
  return typeof v === 'string' && v !== '' ? v : null;
}

function numero(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function lerFalha(v: unknown): FalhaDoRecibo | null {
  if (v == null) return null;
  // Uma falha que chega como texto puro continua sendo a evidência. Descartá-la
  // porque não é objeto seria jogar fora a única coisa que explica o que houve.
  if (typeof v === 'string') {
    return { mensagem: v, codigo: null, posicao: null, campo: null };
  }
  if (typeof v !== 'object') return null;
  const o = v as Record<string, unknown>;
  return {
    mensagem: texto(o.mensagem) ?? texto(o.message) ?? texto(o.erro) ?? null,
    codigo: texto(o.codigo) ?? texto(o.code) ?? null,
    posicao: numero(o.posicao),
    campo: texto(o.campo) ?? texto(o.field) ?? null,
  };
}

function lerCriados(v: unknown): OperacaoCriada[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((item, i) => {
    if (typeof item !== 'object' || item === null) return [];
    const o = item as Record<string, unknown>;
    const nome = texto(o.resource_name);
    if (!nome) return [];
    return [
      {
        posicao: numero(o.posicao) ?? i,
        tipo: texto(o.tipo) ?? 'operação não nomeada',
        resource_name: nome,
      },
    ];
  });
}

/**
 * Lê um recibo cru. `null` quando o objeto não tem o mínimo para ser um recibo.
 *
 * O mínimo é `carimbo` e `impressao`: sem os dois não dá para dizer QUANDO nem
 * O QUÊ, e um recibo que não diz nenhum dos dois não prova nada.
 */
export function lerRecibo(bruto: unknown): Recibo | null {
  if (typeof bruto !== 'object' || bruto === null) return null;
  const o = bruto as Record<string, unknown>;
  const carimbo = texto(o.carimbo);
  const impressao = texto(o.impressao);
  if (!carimbo || !impressao) return null;

  return {
    estado: texto(o.estado) ?? 'estado não declarado',
    carimbo,
    customer_id: texto(o.customer_id) ?? '',
    login_customer_id: texto(o.login_customer_id),
    nome_campanha: texto(o.nome_campanha) ?? 'campanha sem nome no recibo',
    n_operacoes: numero(o.n_operacoes),
    impressao,
    motivo: texto(o.motivo) ?? '',
    criados: lerCriados(o.criados),
    request_id: texto(o.request_id) ?? '',
    falha: lerFalha(o.falha),
    explicacao: texto(o.explicacao) ?? '',
    nada_foi_criado: o.nada_foi_criado === true,
  };
}

/**
 * O carimbo `20260819_123825` em leitura humana.
 *
 * ⚠️ O carimbo NÃO declara fuso. Ele é gravado pelo relógio da máquina que
 * subiu a campanha, e esta tela não sabe qual era. Ela mostra o instante como
 * está e diz que o fuso não foi declarado, em vez de convertê-lo para o fuso
 * do navegador — que produziria uma hora diferente da que está no arquivo, sem
 * nenhum aviso, para quem estivesse conferindo os dois lado a lado.
 */
export function momentoDoCarimbo(carimbo: string): { texto: string; semFuso: boolean } | null {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(carimbo);
  if (!m) return null;
  const [, ano, mes, dia, h, min, s] = m;
  return { texto: `${dia}/${mes}/${ano} ${h}:${min}:${s}`, semFuso: true };
}

/** Quantas operações de cada tipo o recibo confirma. Ordem estável por tipo. */
export function porTipo(recibo: Recibo): { tipo: string; n: number }[] {
  const contagem = new Map<string, number>();
  for (const c of recibo.criados) {
    contagem.set(c.tipo, (contagem.get(c.tipo) ?? 0) + 1);
  }
  return [...contagem]
    .map(([tipo, n]) => ({ tipo, n }))
    .sort((a, b) => (b.n - a.n) || a.tipo.localeCompare(b.tipo));
}

/**
 * A contradição que só um recibo revela: ele diz um número e entrega outro.
 *
 * `n_operacoes` é o tamanho do grafo enviado e `criados` é o que a conta
 * confirmou. Nos cinco recibos reais eles batem. Quando não baterem, é fato
 * material — e a tela precisa dizer, não escolher o número mais bonito.
 *
 * ⚠️ Três estados, e o terceiro existe por um defeito que já esteve aqui.
 * Enquanto `n_operacoes` ausente virava `0`, um recibo que simplesmente não
 * declarava o campo era comparado como `criados.length === 0` — e um recibo
 * saudável, com 34 operações confirmadas, era acusado de contradição material.
 * A tela gritaria sobre uma divergência inventada pelo próprio leitor.
 *
 * `conferirImpressao`, logo abaixo, já resolvia o mesmo problema com um terceiro
 * estado. Esta função passou a usar o mesmo molde: ausência é
 * `nao_da_para_conferir`, nunca `difere`.
 */
export type ConferenciaDaContagem = 'confere' | 'difere' | 'nao_da_para_conferir';

export function contagemConfere(recibo: Recibo): ConferenciaDaContagem {
  if (recibo.n_operacoes === null) return 'nao_da_para_conferir';
  return recibo.criados.length === recibo.n_operacoes ? 'confere' : 'difere';
}

export type ConferenciaDaImpressao = 'confere' | 'difere' | 'nao_da_para_conferir';

/**
 * O recibo prova o que foi criado; a aprovação prova o que foi autorizado.
 *
 * Só a impressão amarra os dois. Sem ela, "aprovado" e "criado" são dois fatos
 * verdadeiros sobre coisas possivelmente diferentes — e é exatamente assim que
 * uma proposta editada depois da assinatura vai ao ar com carimbo de aprovada.
 */
export function conferirImpressao(
  aprovacao: Aprovacao | null | undefined,
  recibo: Recibo | null | undefined,
): ConferenciaDaImpressao {
  if (!aprovacao?.impressao || !recibo?.impressao) return 'nao_da_para_conferir';
  return aprovacao.impressao === recibo.impressao ? 'confere' : 'difere';
}

export const FRASE_DA_CONFERENCIA: Record<ConferenciaDaImpressao, string> = {
  confere:
    'a impressão do recibo é a mesma que foi aprovada. O que saiu é o que foi autorizado.',
  difere:
    'a impressão do recibo NÃO é a que foi aprovada. Alguma coisa mudou entre a assinatura e o envio.',
  nao_da_para_conferir:
    'não dá para conferir: falta a impressão de um dos dois lados. A aprovação e o recibo continuam válidos cada um por si, e nada amarra um ao outro.',
};
