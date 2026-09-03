/**
 * Visão operacional derivada só do inventário real.
 *
 * Ausência não vira zero saudável. Um Cofre vazio tem total 0 (fato) e o resto
 * das perguntas fica sem amostra. Pintar "0 bloqueadores" sobre zero ativos
 * ensinaria a operação a ler silêncio como prontidão.
 */
import { STATE_LABEL, VERIFICATION_LABEL, type AssetState } from "../contract";
import type { AtivoDaLista } from "../cofreApi";

export type Amostra = "vazia" | "presente";

export interface ContagemNomeada {
  chave: string;
  rotulo: string;
  total: number;
}

export interface ProximoAto {
  ativoId: string | null;
  nome: string | null;
  frase: string;
}

export interface VisaoDoCofre {
  amostra: Amostra;
  total: number;
  porEstado: ContagemNomeada[];
  verificados: number | null;
  semAcesso: number | null;
  revisoesVencidas: number | null;
  cofreBloqueado: number | null;
  relacaoIncompleta: number | null;
  prontidaoDominante: { rotulo: string; detalhe: string };
  bloqueadores: string[];
  proximoAto: ProximoAto;
}

const ORDEM_ESTADO: AssetState[] = [
  "declared", "verified", "ready", "active", "restricted", "inactive", "retired",
];

const PESO_CRITICIDADE: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3,
};

function pesoDoAtivo(ativo: AtivoDaLista): number {
  const criticidade = PESO_CRITICIDADE[ativo.criticidade] ?? 4;
  const urgencia =
    ativo.verificacao_estado === "blocked" ? 0 :
    ativo.verificacao_estado === "expired" ? 1 :
    ativo.verificacao_estado === "failed" ? 2 :
    !ativo.credencial_registrada ? 3 :
    ativo.verificacao_estado !== "verified" ? 4 :
    ativo.relacoes.length === 0 ? 5 :
    6;
  return urgencia * 10 + criticidade;
}

export function derivarVisao(ativos: AtivoDaLista[]): VisaoDoCofre {
  if (ativos.length === 0) {
    return {
      amostra: "vazia",
      total: 0,
      porEstado: [],
      verificados: null,
      semAcesso: null,
      revisoesVencidas: null,
      cofreBloqueado: null,
      relacaoIncompleta: null,
      prontidaoDominante: {
        rotulo: "Sem amostra",
        detalhe: "O Cofre respondeu e não há ativo. Não há prontidão para resumir.",
      },
      bloqueadores: [],
      proximoAto: {
        ativoId: null,
        nome: null,
        frase: "Cadastrar o primeiro ativo da operação.",
      },
    };
  }

  const porEstadoMap = new Map<string, number>();
  for (const ativo of ativos) {
    porEstadoMap.set(ativo.estado, (porEstadoMap.get(ativo.estado) ?? 0) + 1);
  }
  const porEstado: ContagemNomeada[] = ORDEM_ESTADO
    .filter((estado) => porEstadoMap.has(estado))
    .map((estado) => ({
      chave: estado,
      rotulo: STATE_LABEL[estado],
      total: porEstadoMap.get(estado) ?? 0,
    }));
  for (const [chave, total] of porEstadoMap) {
    if (!ORDEM_ESTADO.includes(chave as AssetState)) {
      porEstado.push({ chave, rotulo: chave, total });
    }
  }

  const verificados = ativos.filter((a) => a.verificacao_estado === "verified").length;
  const semAcesso = ativos.filter((a) => !a.credencial_registrada).length;
  const revisoesVencidas = ativos.filter((a) => a.verificacao_estado === "expired").length;
  const cofreBloqueado = ativos.filter((a) => a.verificacao_estado === "blocked").length;
  const relacaoIncompleta = ativos.filter((a) => a.relacoes.length === 0).length;

  const bloqueadores: string[] = [];
  if (cofreBloqueado) bloqueadores.push(`${cofreBloqueado} com cofre externo bloqueado`);
  if (revisoesVencidas) bloqueadores.push(`${revisoesVencidas} com revisão vencida`);
  if (semAcesso) bloqueadores.push(`${semAcesso} sem referência de acesso`);
  const falhou = ativos.filter((a) => a.verificacao_estado === "failed").length;
  if (falhou) bloqueadores.push(`${falhou} com verificação falha`);
  if (relacaoIncompleta) bloqueadores.push(`${relacaoIncompleta} sem relação declarada`);

  const dominante = prontidaoMaisFrequente(ativos);
  const urgente = [...ativos].sort((a, b) => pesoDoAtivo(a) - pesoDoAtivo(b))[0];

  return {
    amostra: "presente",
    total: ativos.length,
    porEstado,
    verificados,
    semAcesso,
    revisoesVencidas,
    cofreBloqueado,
    relacaoIncompleta,
    prontidaoDominante: dominante,
    bloqueadores,
    proximoAto: {
      ativoId: urgente.ativo_id,
      nome: urgente.nome,
      frase: urgente.proxima_acao,
    },
  };
}

function prontidaoMaisFrequente(ativos: AtivoDaLista[]): { rotulo: string; detalhe: string } {
  const baldes = new Map<string, number>();
  for (const ativo of ativos) {
    const chave = classeDeProntidao(ativo);
    baldes.set(chave, (baldes.get(chave) ?? 0) + 1);
  }
  const [chave, total] = [...baldes.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
  const rotulo = ROTULO_CLASSE[chave] ?? chave;
  return {
    rotulo,
    detalhe: `${total} de ${ativos.length} nesta classe. Não é um veredito de publicação.`,
  };
}

function classeDeProntidao(ativo: AtivoDaLista): string {
  if (ativo.aposentado_em || ativo.estado === "retired") return "aposentado";
  if (ativo.verificacao_estado === "blocked") return "cofre_bloqueado";
  if (ativo.verificacao_estado === "expired") return "revisao_vencida";
  if (ativo.verificacao_estado === "failed") return "verificacao_falhou";
  if (!ativo.credencial_registrada) return "sem_referencia";
  if (ativo.verificacao_estado !== "verified") return "referencia_sem_prova";
  if (ativo.relacoes.length === 0) return "relacao_incompleta";
  if (ativo.estado === "ready" || ativo.estado === "active") return "em_ordem_de_registro";
  return "declarado";
}

const ROTULO_CLASSE: Record<string, string> = {
  aposentado: "Aposentados",
  cofre_bloqueado: "Cofre externo bloqueado",
  revisao_vencida: "Revisão vencida",
  verificacao_falhou: "Verificação falhou",
  sem_referencia: "Sem referência de acesso",
  referencia_sem_prova: "Referência sem verificação",
  relacao_incompleta: "Relação incompleta",
  em_ordem_de_registro: "Em ordem no registro",
  declarado: "Só declarado",
};

export function rotuloDeVerificacao(estado: string): string {
  return VERIFICATION_LABEL[estado as keyof typeof VERIFICATION_LABEL] ?? estado;
}
