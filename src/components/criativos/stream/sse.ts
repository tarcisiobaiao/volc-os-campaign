/**
 * O protocolo SSE lido a partir de um corpo em streaming. Puro, sem rede.
 *
 * ## Por que isto não mora no cliente HTTP
 *
 * Porque o cliente HTTP importa a sessão do Supabase, e a única forma de provar
 * que um quadro cortado ao meio pelo chunk da rede não vira evento perdido é
 * chamar a função com o corte no meio. Um teste que precisa de credencial para
 * exercitar um parser de texto não é teste do parser.
 *
 * ## O corte é em linha em branco, não em `\n`
 *
 * Um quadro SSE termina com linha vazia. Cortar em `\n` partiria um quadro de
 * várias linhas `data:` ao meio, que é exatamente o formato que o servidor usa
 * quando o JSON é longo.
 */
export interface QuadroSse {
  evento: string;
  dados: string;
}

export function repartirQuadros(buffer: string): { quadros: string[]; resto: string } {
  const normalizado = buffer.replace(/\r\n/g, '\n');
  const partes = normalizado.split('\n\n');
  // O último pedaço pode ser um quadro incompleto: ele volta como resto e é
  // concatenado com o próximo chunk. Tratá-lo como quadro perderia metade dele.
  const resto = partes.pop() ?? '';
  return { quadros: partes.filter((q) => q.trim().length > 0), resto };
}

export function lerQuadro(bruto: string): QuadroSse | null {
  let evento = 'message';
  const dados: string[] = [];
  for (const linha of bruto.split('\n')) {
    // Comentário (keep-alive do servidor) não é evento.
    if (linha.startsWith(':')) continue;
    if (linha.startsWith('event:')) evento = linha.slice(6).trim();
    else if (linha.startsWith('data:')) dados.push(linha.slice(5).replace(/^ /, ''));
  }
  if (!dados.length) return null;
  return { evento, dados: dados.join('\n') };
}
