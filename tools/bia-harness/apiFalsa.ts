/**
 * API falsa da Bia para a bancada visual. Nenhuma chamada de rede: cada cena
 * monta o estado que a captura precisa (inclusive os que não se provoca com
 * segurança no Hermes real: incerto, falha, rede caída).
 */
import { ErroDeApi } from '@/lib/secureApi';
import type { BiaApi } from '@/features/bia/api';
import type {
  AnexoDaBia,
  ComandoDoCatalogo,
  EstadoDaBia,
  EventoDeFluxo,
  ExecucaoDaBia,
} from '@/features/bia/tipos';

const agora = Date.now();
const iso = (minAtras: number) => new Date(agora - minAtras * 60_000).toISOString();

const ESTADO: EstadoDaBia = {
  modo: 'consulta',
  aviso: 'Bia em modo de consulta — nenhuma ação operacional será executada.',
  memoria: {
    compartilhada_com: 'telegram',
    aviso:
      'É a mesma Bia do Telegram: mesma identidade e memória longa. Esta conversa é uma sessão separada; o que for dito aqui pode ser lembrado lá.',
  },
  motor_configurado: true,
  limites: { max_caracteres: 4000, envios_por_minuto: 6, espera_maxima_s: 300 },
  capacidades: ['anexos', 'comandos', 'fluxo'],
};

const web = (nome: string, descricao: string, args = ''): ComandoDoCatalogo => ({
  nome, descricao, args, origem: 'volc', classe: 'local_ui', disponivel: true,
  execucao: 'local', motivo: '', equivalente_web: null, aliases: [],
});
const bloq = (nome: string, classe: ComandoDoCatalogo['classe'], motivo: string): ComandoDoCatalogo => ({
  nome, descricao: motivo, args: '', origem: 'hermes_registro', classe, disponivel: false,
  execucao: null, motivo, equivalente_web: null, aliases: [],
});

const COMANDOS: ComandoDoCatalogo[] = [
  web('nova', 'Abrir uma nova conversa, isolada da atual'),
  web('conversas', 'Ver e retomar suas conversas recentes'),
  web('anexar', 'Escolher imagem ou documento para enviar'),
  web('copiar', 'Copiar a última resposta da Bia'),
  web('contexto', 'Incluir o contexto somente leitura de uma campanha', '<id da campanha>'),
  { ...web('status', 'Ver o estado da conversa: mensagens, tokens, custo e versão do Hermes'), classe: 'hermes_safe', execucao: 'backend' },
  web('ajuda', 'Listar os comandos disponíveis e indisponíveis'),
  bloq('compress', 'hermes_safe', 'Reescreve o histórico da sessão com outro modelo; fora da V1.'),
  bloq('config', 'external_mutation', 'Configuração do profile (terminal).'),
  bloq('cron', 'requires_tool', 'Agenda tarefas: exige ferramentas, desligadas na web.'),
  bloq('model', 'external_mutation', 'Troca o modelo do profile compartilhado com o Telegram.'),
];

const RESPOSTA_LONGA = `Resumo do desempenho da **Campanha Primavera** nos últimos 7 dias:

1. **Investimento:** R$ 962,50 (R$ 137,50/dia, dentro do orçamento).
2. **CPA médio:** R$ 21,40 — 17% acima da meta de R$ 18,20.
3. **Melhor grupo:** *Jardim Vertical*, com CTR de 4,8%.

| Grupo | Cliques | CPA |
|---|---:|---:|
| Jardim Vertical | 412 | R$ 16,90 |
| Suculentas | 288 | R$ 24,10 |
| Inverno (pausado) | 0 | — |

Para conferir a consulta usada:

\`\`\`sql
select grupo, sum(cliques), avg(cpa) from metricas where campanha = 'primavera' group by grupo;
\`\`\`

Detalhes do critério estão na [documentação do Google Ads](https://support.google.com/google-ads/answer/6395625).
Uma palavra muito longa para testar quebra: abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnop.`;

function execucao(p: Partial<ExecucaoDaBia> & { id: string }): ExecucaoDaBia {
  return {
    conversa_id: 'c1', request_id: `r-${p.id}`, estado: 'succeeded', entrada: '', resposta: null,
    erro: null, contexto: null, criada_em: iso(10), terminada_em: iso(9), ...p,
  };
}

const PNG_1PX =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#7a1f3d"/><circle cx="32" cy="32" r="18" fill="#e0526f"/></svg>',
  );

export type Cena =
  | 'vazio' | 'conversa' | 'longa' | 'processando' | 'fila' | 'digitando'
  | 'incerta' | 'erro' | 'upload' | 'paleta' | 'conversas';

export function apiFalsa(cena: Cena): BiaApi {
  let execs: ExecucaoDaBia[] = [];
  if (cena !== 'vazio' && cena !== 'upload' && cena !== 'paleta') {
    execs.push(
      execucao({
        id: 'e1', entrada: 'Descreva esta foto em uma frase.', criada_em: iso(12), terminada_em: iso(12),
        resposta: 'A foto mostra suculentas de folhas longas, iluminadas em vermelho e rosa sobre fundo preto.',
        contexto: { campanha: null, anexos: [{ id: 'a1', nome: 'foto-suculentas.jpg', tipo: 'jpeg', familia: 'imagem', tamanho: 304458 }] },
      }),
    );
  }
  if (cena === 'longa' || cena === 'conversas') {
    execs.push(
      execucao({
        id: 'e2', entrada: 'Resuma a Campanha Primavera com os números do relatório anexado.', criada_em: iso(6), terminada_em: iso(5),
        resposta: RESPOSTA_LONGA,
        contexto: {
          campanha: { campaign_ref: 'primavera-2026', janela: 'ultimos_7_dias' },
          anexos: [{ id: 'a2', nome: 'relatorio-primavera-semana-41-versao-final-revisada.pdf', tipo: 'pdf', familia: 'documento', tamanho: 482113 }],
        },
      }),
    );
  }
  if (cena === 'processando') execs.push(execucao({ id: 'e3', estado: 'running', entrada: 'Quais grupos devo revisar primeiro?', criada_em: iso(0), terminada_em: null }));
  if (cena === 'fila') execs.push(execucao({ id: 'e3', estado: 'queued', entrada: 'Quais grupos devo revisar primeiro?', criada_em: iso(0), terminada_em: null }));
  if (cena === 'digitando') execs.push(execucao({ id: 'e3', estado: 'running', entrada: 'Quais grupos devo revisar primeiro?', criada_em: iso(0), terminada_em: null }));
  if (cena === 'incerta') {
    execs.push(execucao({ id: 'e3', estado: 'uncertain', entrada: 'Quais grupos devo revisar primeiro?', criada_em: iso(1), terminada_em: iso(0),
      erro: { codigo: 'hermes_conexao', mensagem: 'A conexão com a Bia caiu antes da confirmação.' } }));
  }
  if (cena === 'erro') {
    execs.push(execucao({ id: 'e3', estado: 'failed', entrada: 'Pause o grupo Inverno agora.', criada_em: iso(1), terminada_em: iso(0),
      erro: { codigo: 'hermes_usou_ferramenta', mensagem: 'A Bia tentou usar uma ferramenta, o que não é permitido na web. O turno foi interrompido.' } }));
  }

  const conversaId = cena === 'vazio' || cena === 'upload' || cena === 'paleta' ? null : 'c1';
  try {
    if (conversaId) window.localStorage.setItem('volc.bia.conversa.harness', conversaId);
    else window.localStorage.removeItem('volc.bia.conversa.harness');
  } catch { /* sem armazenamento */ }

  let nUpload = 0;
  const nunca = new Promise<never>(() => undefined);

  return {
    estado: async () => ESTADO,
    novaConversa: async () => ({ conversa: { id: 'c2', titulo: null, criada_em: iso(0), atualizada_em: iso(0) } }),
    conversas: async () => ({
      conversas: [
        { id: 'c1', titulo: 'Resuma a Campanha Primavera com os números do relatório anexado.', criada_em: iso(60), atualizada_em: iso(5), mensagens: 2 },
        { id: 'c0', titulo: 'Descreva esta foto em uma frase.', criada_em: iso(60 * 26), atualizada_em: iso(60 * 25), mensagens: 1 },
        { id: 'c-1', titulo: null, criada_em: iso(60 * 24 * 4), atualizada_em: iso(60 * 24 * 4), mensagens: 0 },
      ],
    }),
    historico: async () => ({ conversa: { id: 'c1', titulo: null, criada_em: iso(60), atualizada_em: iso(1) }, execucoes: execs, aviso: '' }),
    enviar: async () => {
      if (cena === 'erro') throw new ErroDeApi('A rede falhou.', 0, 'REDE');
      const e = execucao({ id: `n${Date.now()}`, estado: 'queued', entrada: 'nova', criada_em: new Date().toISOString(), terminada_em: null });
      execs = [...execs, e];
      return { execucao: e, aviso: '' };
    },
    execucao: async (id) => ({ execucao: execs.find((e) => e.id === id)! }),
    reconciliar: async (id) => ({ execucao: execs.find((e) => e.id === id)! }),
    comandos: async () => ({ comandos: COMANDOS }),
    executarComando: async () => ({
      comando: 'status',
      resultado: { conversa: { mensagens: 2, por_estado: { succeeded: 2 } }, hermes: { versao: '0.18.0', gateway: 'running' }, sessao_web: null, avisos: [] },
      recibo: {},
    }),
    removerAnexo: async () => ({ removido: true }),
    enviarAnexo(arquivo: File, aoProgresso: (f: number) => void) {
      const n = nUpload++;
      const anexo: AnexoDaBia = {
        id: `up${n}`, nome: arquivo.name, tipo: arquivo.name.split('.').pop() ?? '', familia: /\.(png|jpe?g|webp)$/i.test(arquivo.name) ? 'imagem' : 'documento',
        tamanho: arquivo.size, mime: arquivo.type, sha256: '', criado_em: iso(0), expira_em: iso(-60 * 24 * 7),
        paginas: /\.pdf$/i.test(arquivo.name) ? 3 : null, largura: null, altura: null, caracteres: null, truncado: false,
      };
      if (n === 0) return { promessa: Promise.resolve(anexo), cancelar: () => undefined };
      if (n === 1) {
        setTimeout(() => aoProgresso(0.62), 50);
        return { promessa: nunca, cancelar: () => undefined };
      }
      return {
        promessa: Promise.reject(new ErroDeApi('O conteúdo não corresponde a um PNG válido (tipo divergente).', 422, 'tipo_divergente')),
        cancelar: () => undefined,
      };
    },
    urlDoAnexo: async () => PNG_1PX,
    async acompanhar(id: string, aoEvento: (e: EventoDeFluxo) => void, sinal: AbortSignal) {
      if (cena === 'digitando') {
        setTimeout(() => aoEvento({ tipo: 'parcial', texto: 'Comece pelo grupo **Suculentas**: o CPA está em R$ 24,10, 32% acima da meta. Depois' }), 100);
      }
      await new Promise<void>((resolver) => sinal.addEventListener('abort', () => resolver()));
      void id;
    },
  };
}
