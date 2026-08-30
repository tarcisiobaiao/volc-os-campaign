/**
 * A leitura de um lote parcial: o que ficou pronto continua pronto.
 *
 * ## Por que `partial` não pode virar booleano
 *
 * Um lote de quatro formatos com um recusado não é sucesso nem falha. Chamá-lo
 * de falha joga fora três arquivos que custaram chamada real ao motor; chamá-lo
 * de sucesso manda para o ar um pacote incompleto. O contrato guarda o erro na
 * PEÇA (regra C da v11_01) exatamente para que esta camada possa mostrar as
 * três prontas e a quarta com o motivo, lado a lado.
 *
 * ## Por que o retry olha `permanente`
 *
 * `permanente: true` é o motor dizendo "o mesmo insumo vai errar igual". Um
 * botão de repetir que ignora isso vira uma cascata que queima cota repetindo
 * um pedido já recusado. Quando TODA falha pendente é permanente, o botão sai
 * do ar com o motivo escrito, que é o que o DESIGN.md pede de uma ação
 * indisponível.
 */
import type { CreativeJob, EstadoDaRendition, Rendition } from '@/types/criativos';

export interface ResumoDasPecas {
  prontas: Rendition[];
  falhadas: Rendition[];
  emCurso: Rendition[];
  canceladas: Rendition[];
  total: number;
}

const EM_CURSO: readonly EstadoDaRendition[] = ['pendente', 'gerando'];

export function resumirPecas(renditions: Rendition[]): ResumoDasPecas {
  return {
    prontas: renditions.filter((r) => r.estado === 'pronta'),
    falhadas: renditions.filter((r) => r.estado === 'falhou'),
    emCurso: renditions.filter((r) => EM_CURSO.includes(r.estado)),
    canceladas: renditions.filter((r) => r.estado === 'cancelada'),
    total: renditions.length,
  };
}

/**
 * A frase que descreve o lote sem apagar nenhuma das partes.
 *
 * Nunca diz "falhou" quando há peça pronta, e nunca diz "pronto" quando há peça
 * faltando: as duas frases levariam a decisões que os arquivos não sustentam.
 */
export function frasePecas(resumo: ResumoDasPecas): string {
  const { prontas, falhadas, emCurso, canceladas, total } = resumo;
  if (total === 0) return 'Nenhuma peça foi registrada neste trabalho.';
  if (prontas.length === total) {
    return `As ${total} peças pedidas ficaram prontas.`;
  }
  const partes: string[] = [];
  partes.push(`${prontas.length} de ${total} ${prontas.length === 1 ? 'peça pronta' : 'peças prontas'}`);
  if (falhadas.length) partes.push(`${falhadas.length} com falha`);
  if (emCurso.length) partes.push(`${emCurso.length} ainda em produção`);
  if (canceladas.length) partes.push(`${canceladas.length} cancelada${canceladas.length > 1 ? 's' : ''}`);
  return `${partes.join(', ')}.`;
}

export interface OfertaDeAcao {
  disponivel: boolean;
  /** Por que está disponível, ou por que não está. Sempre presente. */
  motivo: string;
}

export function ofertaDeRetry(job: CreativeJob): OfertaDeAcao {
  if (job.procedenciaExecucao === 'observado') {
    return {
      disponivel: false,
      motivo: 'Este build foi observado, não produzido aqui. O VOLC O.S. não pode repeti-lo.',
    };
  }
  if (job.estado !== 'partial' && job.estado !== 'failed') {
    return {
      disponivel: false,
      motivo: 'Repetir só faz sentido depois que o trabalho termina com peça faltando.',
    };
  }
  const resumo = resumirPecas(job.renditions);
  const faltando = [...resumo.falhadas, ...resumo.canceladas];
  if (!faltando.length && job.estado === 'partial') {
    return { disponivel: false, motivo: 'Não há peça faltando para preencher.' };
  }
  const permanentes = faltando.filter((r) => r.erro?.permanente === true);
  if (faltando.length > 0 && permanentes.length === faltando.length) {
    return {
      disponivel: false,
      motivo:
        'Todas as falhas pendentes são permanentes: o motor já disse que o mesmo insumo falharia igual. Ajuste o briefing e peça um trabalho novo.',
    };
  }
  return {
    disponivel: true,
    motivo:
      'Repetir preenche apenas as peças que faltaram. As peças já prontas não são geradas de novo e não custam de novo.',
  };
}

export function ofertaDeCancelamento(job: CreativeJob): OfertaDeAcao {
  if (job.procedenciaExecucao === 'observado') {
    return {
      disponivel: false,
      motivo: 'Este build foi observado, não está em execução aqui.',
    };
  }
  if (job.estado === 'queued' || job.estado === 'running') {
    return {
      disponivel: true,
      motivo: 'Interrompe o que ainda não começou. As peças já prontas permanecem.',
    };
  }
  return { disponivel: false, motivo: 'O trabalho já terminou. Não há o que interromper.' };
}
