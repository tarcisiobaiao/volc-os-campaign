/**
 * A leitura REAL de uma campanha Meta — campanha → conjuntos → anúncios → peça.
 *
 * ---------------------------------------------------------------------------
 * O DEFEITO QUE ESTE ARQUIVO EXISTE PARA FECHAR
 * ---------------------------------------------------------------------------
 *
 * Até aqui, abrir `/dashboard/campaign/<id>?rede=meta` procurava o identificador
 * dentro de `META_DEMO` e, quando não achava, fazia `<Navigate>` para a lista.
 * O efeito prático era o pior possível: uma campanha REAL — a única que pode
 * existir depois de uma sincronização — desaparecia da tela sem dizer nada, e a
 * única identidade que a página sabia abrir era a fictícia. A demonstração
 * deixava de ser uma porta explícita e virava o destino de qualquer leitura que
 * não desse certo.
 *
 * Aqui a ordem é a inversa e é a regra do milestone: identidade real lê o read
 * model; a demonstração só existe atrás de `?modo=demo`; e nenhum estado de
 * leitura — falha, vazio, escopo desconhecido, objeto não encontrado — pode
 * levar de volta ao cenário fictício.
 *
 * ---------------------------------------------------------------------------
 * AS SEIS FORMAS DE NÃO TER A RESPOSTA INTEIRA
 * ---------------------------------------------------------------------------
 *
 * `read_model.py` devolve SEMPRE `ok: true`, inclusive quando o Supabase está
 * fora, quando as tabelas nunca foram criadas e quando a conta pedida não
 * existe no snapshot. Um cliente que só olhasse `items` transformaria as três
 * em "esta conta não tem campanhas" — a única leitura que o servidor nunca fez.
 * Por isso `estado` é renderizado como CONTEÚDO, com a frase que distingue cada
 * caso, e nunca como tela em branco nem como aviso passageiro.
 *
 * ---------------------------------------------------------------------------
 * ⚠️ POR QUE O RETORNO FINANCEIRO APARECE COMO AUSENTE
 * ---------------------------------------------------------------------------
 *
 * `_sanitize_rows` remove `objeto_externo` de toda linha de insight antes de
 * ela sair do servidor — é a mesma regra que remove os identificadores crus da
 * Meta. Sem esse campo, uma linha de insight não declara A QUE objeto pertence:
 * ela é um fato da CONTA. Atribuir o gasto da conta a esta campanha seria
 * inventar a medida mais cara da tela. Então os quatro cartões da espinha
 * econômica mostram `—`, a frase diz por quê, e os insights da conta aparecem
 * embaixo com o rótulo de que são da conta.
 */
import React from 'react';
import {
  ArrowLeft,
  CircleDashed,
  CircleDot,
  CircleHelp,
  CirclePause,
  CircleSlash,
  Coins,
  DollarSign,
  Image as ImageIcon,
  Target,
  TrendingUp,
  TriangleAlert,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { SeletorRedeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  ENTIDADES_META_QUE_EXIGEM_CONTA,
  pautadorApi,
  type ContaMetaReadModel,
  type ContasDoReadModelMeta,
  type DetalheMetaReadModel,
  type EntidadeMetaReadModel,
  type EstadoDoReadModelMeta,
  type ItemMetaReadModel,
  type PaginaMetaReadModel,
} from '@/lib/pautadorApi';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import { useDensidade, type Densidade } from '@/components/trafego/inventario/densidade';
import {
  AvisoDeLeituraParcial,
  EsqueletoDoInventario,
  FalhaDoInventario,
  InventarioVazio,
} from '@/components/trafego/inventario/EstadosDoInventario';
import {
  descreverFalha,
  registrarDetalhe,
  FRASES_DE_FALHA,
  type OcorrenciaOperacional,
} from '@/components/trafego/inventario/erros';
import { AUSENTE, contagem, dinheiro, horaDeLeitura } from '@/components/trafego/inventario/formato';
import { Chip, SeloDeFrescor, type Tom } from '@/components/trafego/inventario/Selos';
import type { Frescor, Leitura as LeituraDaConta } from '@/types/trafego';

// ═══════════════════════════════════════════════════════════════════════════
// FORMATO — as regras de `formato.tsx`, com a UNIDADE certa
// ═══════════════════════════════════════════════════════════════════════════

/**
 * PostgREST devolve `numeric` como string. `null`, `''` e um número que não é
 * número são a MESMA coisa aqui: ausência. Nenhum deles vira zero.
 */
export function comoNumero(valor: unknown): number | null {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = typeof valor === 'number' ? valor : Number(valor);
  return Number.isFinite(n) ? n : null;
}

/**
 * Dinheiro da Meta.
 *
 * ⚠️ `dinheiro()` de `formato.tsx` recebe MICROS, porque é assim que o Google
 * Ads guarda dinheiro. A Meta devolve `spend` em unidade de moeda ("684.20").
 * Passar um pelo outro dividiria a conta por um milhão sem nenhum aviso — o
 * gasto de uma campanha viraria menos de um centavo. A conversão acontece aqui,
 * uma vez e explicada, e o resto da regra (ausência = `—`, moeda não declarada
 * dita em vez de assumida) continua sendo a de `formato.tsx`.
 */
export function dinheiroMeta(valor: unknown, moeda: string | null): string {
  const n = comoNumero(valor);
  if (n === null) return AUSENTE;
  return dinheiro(Math.round(n * 1_000_000), moeda);
}

/** Decimal com casas fixas. `null` continua `—`, jamais `0,00`. */
export function decimalMeta(valor: unknown, casas = 2, sufixo = ''): string {
  const n = comoNumero(valor);
  if (n === null) return AUSENTE;
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(n)}${sufixo}`;
}

/** Contagem inteira, pela regra do módulo: `0` sobrevive, `null` vira `—`. */
export function contagemMeta(valor: unknown): string {
  const n = comoNumero(valor);
  return contagem(n === null ? null : Math.round(n));
}

const textoOuAusente = (valor: unknown): string =>
  typeof valor === 'string' && valor.trim() !== '' ? valor : AUSENTE;

// ═══════════════════════════════════════════════════════════════════════════
// VOCABULÁRIO — o estado que a META declara
// ═══════════════════════════════════════════════════════════════════════════

/**
 * ⚠️ POR QUE ISTO NÃO É `SeloDeEstadoExterno`.
 *
 * `SeloDeEstadoExterno` conhece TRÊS palavras — `ENABLED`, `PAUSED`, `REMOVED`
 * — e as descreve como "ligada no Google", "pausada no Google", "removida no
 * Google". Elas ficam em inglês lá justamente porque são as palavras que o
 * operador lê no painel do Google. O vocabulário da Meta é outro (`ACTIVE`,
 * `ARCHIVED`, `CAMPAIGN_PAUSED`, `DISAPPROVED`…), e o único valor em comum,
 * `PAUSED`, sairia com a frase "pausada no Google" sobre um fato da Meta.
 *
 * O selo continua sendo o mesmo primitivo — `Chip`, glifo + palavra +
 * descrição, cor como terceiro sinal. O que muda é o dicionário, que é o que
 * tinha de mudar.
 */
const ESTADO_META: Record<
  string,
  { descricao: string; tom: Tom; glifo: React.ComponentType<{ className?: string }> }
> = {
  ACTIVE: { descricao: 'a Meta declara este objeto como ativo', tom: 'bom', glifo: CircleDot },
  PAUSED: { descricao: 'a Meta declara este objeto como pausado', tom: 'neutro', glifo: CirclePause },
  CAMPAIGN_PAUSED: {
    descricao: 'o objeto está ativo, e a campanha acima dele está pausada',
    tom: 'neutro',
    glifo: CirclePause,
  },
  ADSET_PAUSED: {
    descricao: 'o anúncio está ativo, e o conjunto acima dele está pausado',
    tom: 'neutro',
    glifo: CirclePause,
  },
  ARCHIVED: { descricao: 'arquivado na Meta', tom: 'neutro', glifo: CircleSlash },
  DELETED: { descricao: 'excluído na Meta', tom: 'neutro', glifo: CircleSlash },
  PENDING_REVIEW: { descricao: 'a Meta ainda está revisando este objeto', tom: 'atencao', glifo: CircleDashed },
  IN_PROCESS: { descricao: 'a Meta declara o processamento em curso', tom: 'atencao', glifo: CircleDashed },
  WITH_ISSUES: { descricao: 'a Meta declara pendências neste objeto', tom: 'atencao', glifo: TriangleAlert },
  PREAPPROVED: { descricao: 'aprovado em pré-análise pela Meta', tom: 'atencao', glifo: CircleDashed },
  DISAPPROVED: { descricao: 'a Meta reprovou este objeto', tom: 'ruim', glifo: TriangleAlert },
};

export const SeloDeEstadoMeta: React.FC<{ estado: unknown }> = ({ estado }) => {
  if (typeof estado !== 'string' || estado.trim() === '') {
    return (
      <Chip
        glifo={CircleHelp}
        palavra="estado não lido"
        descricao="esta leitura do read model não trouxe o estado efetivo deste objeto"
        tom="atencao"
      />
    );
  }
  const conhecido = ESTADO_META[estado];
  if (!conhecido) {
    // O valor cru vai para a DESCRIÇÃO, nunca para a palavra: imprimir
    // `SOMETHING_NEW` como se fosse o estado põe vocabulário de máquina
    // exatamente onde o operador procura a resposta.
    return (
      <Chip
        glifo={CircleHelp}
        palavra="estado não reconhecido"
        descricao={`a conta Meta informou "${estado}", que esta versão da tela não conhece`}
        tom="atencao"
      />
    );
  }
  return (
    <Chip glifo={conhecido.glifo} palavra={estado} descricao={conhecido.descricao} tom={conhecido.tom} />
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// OS ESTADOS DO READ MODEL, COMO CONTEÚDO
// ═══════════════════════════════════════════════════════════════════════════

/** O que cada estado do servidor AFIRMA, na língua de quem opera. */
export const FRASE_DO_ESTADO: Record<EstadoDoReadModelMeta, { titulo: string; explica: string }> = {
  COM_SNAPSHOT: {
    titulo: 'lido do snapshot',
    explica: 'a resposta abaixo veio do read model persistido desta conta.',
  },
  SEM_SNAPSHOT: {
    titulo: 'ainda não sincronizado',
    explica:
      'as tabelas existem e não há linha desta entidade neste escopo. Isso é diferente de ' +
      'a conta estar vazia: nenhuma sincronização precisa ter chegado até aqui.',
  },
  SCHEMA_NAO_APLICADO: {
    titulo: 'persistência Meta não instalada',
    explica:
      'as tabelas do read model Meta não existem neste Supabase. Nada foi lido e nada pode ' +
      'ser gravado até a migration — que é separadamente autorizada — ser aplicada.',
  },
  SEM_CONEXAO: {
    titulo: 'sem conexão com o registro',
    explica:
      'o backend não conseguiu falar com o Supabase. O que está nas contas de anúncio não ' +
      'mudou por causa disto — o que faltou foi conseguir olhar.',
  },
  ESCOPO_OBRIGATORIO: {
    titulo: 'falta escolher a conta',
    explica:
      'conjuntos, anúncios e vínculos só são lidos dentro de uma conta. Sem a conta, o ' +
      'servidor recusa a pergunta em vez de responder com o que for de outra conta.',
  },
  ESCOPO_DESCONHECIDO: {
    titulo: 'conta não resolvida no snapshot',
    explica:
      'a referência de conta pedida não corresponde a nenhuma conta persistida. Um ' +
      'identificador vindo do navegador nunca vira autorização por si só.',
  },
  NAO_ENCONTRADO_NO_ESCOPO: {
    titulo: 'não pertence a esta conta',
    explica:
      'a conta foi lida por inteiro e esta referência não estava na resposta. Ela pode ' +
      'existir em outra conta; o servidor não diz em qual, e esta tela também não.',
  },
  NAO_ENCONTRADO_ESCOPO_PARCIAL: {
    titulo: 'não encontrada — e a leitura foi parcial',
    explica:
      'esta referência não apareceu na parte da conta que voltou. Como a leitura não veio ' +
      'inteira, não dá para afirmar que ela não existe aqui.',
  },
};

/** As duas frases fechadas de `erros.ts` que descrevem estas duas falhas. */
const FRASE_DE_FALHA_DO_ESTADO: Partial<Record<EstadoDoReadModelMeta, string>> = {
  SEM_CONEXAO: FRASES_DE_FALHA.sistema_fora_do_ar.mensagem,
  SCHEMA_NAO_APLICADO: FRASES_DE_FALHA.indisponivel_nesta_versao.mensagem,
};

/**
 * Um estado do servidor virando bloco de conteúdo.
 *
 * `SEM_CONEXAO` e `SCHEMA_NAO_APLICADO` são falhas de leitura e vão para
 * `FalhaDoInventario`, que já traz o código copiável da ocorrência. Os demais
 * não são falhas — são respostas — e por isso não usam a caixa de erro.
 */
export const EstadoDoReadModel: React.FC<{
  estado: EstadoDoReadModelMeta;
  aoTentarDeNovo?: () => void;
  className?: string;
}> = ({ estado, aoTentarDeNovo, className }) => {
  const frase = FRASE_DO_ESTADO[estado];
  const comoFalha = FRASE_DE_FALHA_DO_ESTADO[estado];
  if (comoFalha) {
    return (
      <div className={className}>
        <FalhaDoInventario motivo={comoFalha} aoTentarDeNovo={aoTentarDeNovo} />
        <p className="mt-2 max-w-[74ch] text-[12px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">{frase.titulo}</span> — {frase.explica}
        </p>
      </div>
    );
  }
  return (
    <div
      className={cn('rounded-md border border-border bg-card px-4 py-4', className)}
      role="status"
    >
      <h2 className="font-display text-[15px] font-semibold">{frase.titulo}</h2>
      <p className="mt-1 max-w-[74ch] text-[13px] leading-relaxed text-muted-foreground">
        {frase.explica}
      </p>
      {aoTentarDeNovo && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 h-9 px-3 text-xs"
          onClick={aoTentarDeNovo}
        >
          tentar de novo
        </Button>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// LEITURA — o hook que não deixa uma falha virar lista vazia
// ═══════════════════════════════════════════════════════════════════════════

export type Leitura<T> =
  | { fase: 'lendo' }
  | { fase: 'falhou'; ocorrencia: OcorrenciaOperacional }
  | { fase: 'respondeu'; resposta: T };

function usarFalha(erro: unknown): OcorrenciaOperacional {
  const ocorrencia = descreverFalha(erro, 'campanha_canonica');
  registrarDetalhe(erro, ocorrencia);
  return ocorrencia;
}

/** A lista de contas do read model — a única fonte de `conta_ref` legítimo. */
export function useContasDoReadModel(): {
  leitura: Leitura<ContasDoReadModelMeta>;
  recarregar: () => void;
} {
  const [leitura, setLeitura] = React.useState<Leitura<ContasDoReadModelMeta>>({ fase: 'lendo' });
  const [tentativa, setTentativa] = React.useState(0);

  React.useEffect(() => {
    let vivo = true;
    setLeitura({ fase: 'lendo' });
    pautadorApi
      .contasMetaReadModel()
      .then((resposta) => {
        if (vivo) setLeitura({ fase: 'respondeu', resposta });
      })
      .catch((erro) => {
        const ocorrencia = usarFalha(erro);
        if (vivo) setLeitura({ fase: 'falhou', ocorrencia });
      });
    return () => {
      vivo = false;
    };
  }, [tentativa]);

  return { leitura, recarregar: () => setTentativa((n) => n + 1) };
}

export interface PaginaEmLeitura {
  leitura: Leitura<PaginaMetaReadModel>;
  carregandoMais: boolean;
  /** Só existe quando o servidor entregou um `proximo_cursor`. */
  carregarMais: (() => void) | null;
  recarregar: () => void;
}

/**
 * Uma entidade do read model, paginada pelo cursor OPACO do servidor.
 *
 * ⚠️ A próxima página é APENDADA, e `completo`/`has_more` passam a ser os da
 * última resposta. É o servidor que sabe se ainda falta alguma coisa; somar
 * páginas no cliente e declarar o resultado completo seria a mesma mentira que
 * o teto de 500 linhas era antes de existir cursor.
 */
export function usePaginaDoReadModel(
  entidade: EntidadeMetaReadModel,
  contaRef: string | null,
  ativo = true,
): PaginaEmLeitura {
  const [leitura, setLeitura] = React.useState<Leitura<PaginaMetaReadModel>>({ fase: 'lendo' });
  const [carregandoMais, setCarregandoMais] = React.useState(false);
  const [tentativa, setTentativa] = React.useState(0);

  React.useEffect(() => {
    // ⚠️ SEM CONTA, NENHUMA ENTIDADE É PEDIDA — nem as que o servidor
    // responderia.
    //
    // `criativos` e `insights` têm coluna de conta própria e, sem `conta_ref`,
    // o servidor devolve as linhas de TODAS as contas persistidas. Numa tela
    // que fala de UMA campanha, isso seria misturar contas de clientes
    // diferentes na mesma tabela. As que exigem conta responderiam
    // `ESCOPO_OBRIGATORIO`, e gastar a viagem para ouvir uma recusa previsível
    // é fazer o operador esperar por nada. Os dois casos param aqui.
    if (!ativo || !contaRef) {
      setLeitura({
        fase: 'respondeu',
        resposta: {
          ok: true,
          has_snapshot: false,
          estado: 'ESCOPO_OBRIGATORIO',
          entidade,
          conta_ref: null,
          items: [],
          completo: false,
          has_more: false,
          proximo_cursor: null,
          motivo: ENTIDADES_META_QUE_EXIGEM_CONTA.has(entidade)
            ? 'esta entidade exige conta_ref explicita'
            : 'sem conta escolhida a leitura misturaria contas diferentes',
        },
      });
      return undefined;
    }
    let vivo = true;
    setLeitura({ fase: 'lendo' });
    pautadorApi
      .inventarioMetaReadModel(entidade, { contaRef })
      .then((resposta) => {
        if (vivo) setLeitura({ fase: 'respondeu', resposta });
      })
      .catch((erro) => {
        const ocorrencia = usarFalha(erro);
        if (vivo) setLeitura({ fase: 'falhou', ocorrencia });
      });
    return () => {
      vivo = false;
    };
  }, [entidade, contaRef, ativo, tentativa]);

  const cursor =
    leitura.fase === 'respondeu' && leitura.resposta.has_more
      ? leitura.resposta.proximo_cursor
      : null;

  const carregarMais = React.useCallback(() => {
    if (!cursor) return;
    setCarregandoMais(true);
    pautadorApi
      .inventarioMetaReadModel(entidade, { contaRef, cursor })
      .then((proxima) => {
        setLeitura((antes) =>
          antes.fase === 'respondeu'
            ? {
                fase: 'respondeu',
                resposta: { ...proxima, items: [...antes.resposta.items, ...proxima.items] },
              }
            : { fase: 'respondeu', resposta: proxima },
        );
      })
      .catch((erro) => setLeitura({ fase: 'falhou', ocorrencia: usarFalha(erro) }))
      .finally(() => setCarregandoMais(false));
  }, [entidade, contaRef, cursor]);

  return {
    leitura,
    carregandoMais,
    carregarMais: cursor ? carregarMais : null,
    recarregar: () => setTentativa((n) => n + 1),
  };
}

/** O detalhe de UM objeto, resolvido dentro de uma conta. */
export function useDetalheDoReadModel(
  entidade: EntidadeMetaReadModel,
  referencia: string,
  contaRef: string | null,
): { leitura: Leitura<DetalheMetaReadModel>; recarregar: () => void } {
  const [leitura, setLeitura] = React.useState<Leitura<DetalheMetaReadModel>>({ fase: 'lendo' });
  const [tentativa, setTentativa] = React.useState(0);

  React.useEffect(() => {
    if (!contaRef) {
      setLeitura({
        fase: 'respondeu',
        resposta: {
          ok: true,
          has_snapshot: false,
          estado: 'ESCOPO_OBRIGATORIO',
          entidade,
          item: null,
        },
      });
      return undefined;
    }
    let vivo = true;
    setLeitura({ fase: 'lendo' });
    pautadorApi
      .detalheMetaReadModel(entidade, referencia, contaRef)
      .then((resposta) => {
        if (vivo) setLeitura({ fase: 'respondeu', resposta });
      })
      .catch((erro) => {
        const ocorrencia = usarFalha(erro);
        if (vivo) setLeitura({ fase: 'falhou', ocorrencia });
      });
    return () => {
      vivo = false;
    };
  }, [entidade, referencia, contaRef, tentativa]);

  return { leitura, recarregar: () => setTentativa((n) => n + 1) };
}

// ═══════════════════════════════════════════════════════════════════════════
// A CONTA — cabeçalho, frescor e escolha
// ═══════════════════════════════════════════════════════════════════════════

const DIA_EM_SEGUNDOS = 86_400;

/**
 * O frescor de uma conta a partir do carimbo, sem inventar a palavra.
 *
 * ⚠️ Sem carimbo é `nunca_lido` e NUNCA `recente`: é a degradação mais cara do
 * módulo, porque faz o operador decidir gasto olhando para um número de idade
 * desconhecida achando que olha para agora.
 */
export function frescorDaConta(
  conta: ContaMetaReadModel | null,
  parcial: boolean,
): { frescor: Frescor; leitura: LeituraDaConta | null } {
  const carimbo = conta?.ultima_leitura_ok_em ?? conta?.observado_em ?? null;
  if (!carimbo) return { frescor: 'nunca_lido', leitura: null };
  const instante = new Date(carimbo).getTime();
  if (Number.isNaN(instante)) return { frescor: 'nunca_lido', leitura: null };
  const idade_s = Math.round((Date.now() - instante) / 1000);
  if (parcial) return { frescor: 'parcial', leitura: { lido_em: carimbo, idade_s } };
  return {
    frescor: idade_s > DIA_EM_SEGUNDOS ? 'velho' : 'recente',
    leitura: { lido_em: carimbo, idade_s },
  };
}

const CabecalhoDaConta: React.FC<{
  conta: ContaMetaReadModel;
  parcial: boolean;
  moeda: string | null;
  fuso: string | null;
}> = ({ conta, parcial, moeda, fuso }) => {
  const { frescor, leitura } = frescorDaConta(conta, parcial);
  const hora = horaDeLeitura(conta.ultima_leitura_ok_em ?? conta.observado_em ?? null);
  return (
    <div className="rounded-md border border-border bg-muted/40 px-4 py-3 [box-shadow:inset_3px_0_0_hsl(var(--primary))]">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            conta de anúncios
          </span>
          <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className="font-display text-[17px] font-bold leading-tight tracking-tight text-foreground break-words">
              {textoOuAusente(conta.nome_observado)}
            </span>
            <span
              className="tabular text-[11px] text-muted-foreground"
              title="identificador da conta, com os primeiros dígitos ocultos — o servidor nunca envia o completo"
            >
              {conta.id_mascarado ?? AUSENTE}
            </span>
          </span>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <Chip
            glifo={Coins}
            palavra={moeda ?? 'sem moeda'}
            descricao={
              moeda
                ? `todo dinheiro desta tela está em ${moeda}, a moeda declarada pela conta`
                : 'a conta não declarou moeda nesta leitura; nenhum valor aqui pode ser lido como real'
            }
            tom={moeda ? 'neutro' : 'atencao'}
          />
          <Chip
            glifo={CircleDot}
            palavra={fuso ?? 'sem fuso'}
            descricao={
              fuso
                ? `as datas desta conta são apuradas no fuso ${fuso}`
                : 'a conta não declarou fuso nesta leitura'
            }
            tom={fuso ? 'neutro' : 'atencao'}
          />
          <SeloDeFrescor frescor={frescor} leitura={leitura} />
          {hora && <span className="text-[11px] text-muted-foreground">às {hora}</span>}
        </div>
      </div>
    </div>
  );
};

/**
 * A escolha da conta — que existe porque a resposta depende dela.
 *
 * Não é um filtro de conveniência: `conjuntos`, `anuncios` e `vinculos` são
 * recusados sem conta, e o detalhe de um objeto é resolvido DENTRO de uma. Com
 * uma conta só, a escolha não aparece: um controle com uma opção só é ruído.
 */
export const EscolhaDeConta: React.FC<{
  contas: ContaMetaReadModel[];
  escolhida: string | null;
  aoEscolher: (contaRef: string) => void;
  /** Com o escopo pedido desconhecido, a escolha aparece MESMO com uma conta só:
   *  sem ela a tela vira um beco sem saída — diz que não reconheceu a conta e
   *  não oferece nenhuma que reconheça. */
  forcarVisibilidade?: boolean;
}> = ({ contas, escolhida, aoEscolher, forcarVisibilidade = false }) => {
  if (contas.length === 0) return null;
  if (contas.length === 1 && !forcarVisibilidade) return null;
  return (
    <fieldset className="rounded-md border border-border bg-card px-4 py-3">
      <legend className="kicker px-1">conta lida</legend>
      <div className="flex flex-wrap gap-2">
        {contas.map((conta) => {
          const ref = conta.conta_ref ?? '';
          const ativa = ref === escolhida;
          return (
            <button
              key={ref || conta.cofre_ativo_id || conta.nome_observado || 'sem-ref'}
              type="button"
              aria-pressed={ativa}
              disabled={!ref}
              onClick={() => ref && aoEscolher(ref)}
              className={cn(
                'min-h-9 max-w-full truncate rounded-md border px-3 text-left text-[13px]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                ativa ? 'border-primary/45 bg-primary/[0.06] font-medium' : 'border-border bg-card',
              )}
            >
              {textoOuAusente(conta.nome_observado)}{' '}
              <span className="tabular text-[11px] text-muted-foreground">
                {conta.id_mascarado ?? ''}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
};

/** Resolve qual conta responde — preferida, única, ou escolha do operador. */
export function useEscopoDeConta(contaPreferida?: string | null): {
  leitura: Leitura<ContasDoReadModelMeta>;
  contas: ContaMetaReadModel[];
  contaRef: string | null;
  conta: ContaMetaReadModel | null;
  /** A URL pediu uma conta que o snapshot não conhece. Não é "sem conta". */
  escopoDesconhecido: boolean;
  referenciaPedida: string | null;
  escolher: (contaRef: string) => void;
  recarregar: () => void;
} {
  const { leitura, recarregar } = useContasDoReadModel();
  const [escolhida, setEscolhida] = React.useState<string | null>(contaPreferida ?? null);

  React.useEffect(() => {
    if (contaPreferida) setEscolhida(contaPreferida);
  }, [contaPreferida]);

  const contas = leitura.fase === 'respondeu' ? (leitura.resposta.contas ?? []) : [];
  const referencias = contas.map((c) => c.conta_ref).filter((r): r is string => Boolean(r));

  // ⚠️ UM HANDLE DESCONHECIDO NÃO PODE VIRAR OUTRA CONTA.
  //
  // A queda para `referencias[0]` quando havia exatamente uma conta parecia uma
  // conveniência — e era uma troca silenciosa de escopo: `?conta=<handle de
  // outra conta>` mostrava os números da conta A com a URL dizendo outra coisa.
  // O operador leria gasto e resultado da conta errada sem nada na tela
  // discordando dele. O backend recusa esse caso com `ESCOPO_DESCONHECIDO`; o
  // cliente não pode ser mais permissivo que ele.
  //
  // A conta única só é assumida quando NINGUÉM pediu outra.
  const pedidaEDesconhecida = Boolean(escolhida) && !referencias.includes(escolhida as string);
  const contaRef = pedidaEDesconhecida
    ? null
    : escolhida && referencias.includes(escolhida)
      ? escolhida
      : referencias.length === 1
        ? referencias[0]
        : null;
  const conta = contas.find((c) => c.conta_ref === contaRef) ?? null;

  return {
    leitura,
    contas,
    contaRef,
    conta,
    escopoDesconhecido: pedidaEDesconhecida,
    referenciaPedida: pedidaEDesconhecida ? (escolhida as string) : null,
    escolher: setEscolhida,
    recarregar,
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// PEDAÇOS DE TELA REUTILIZADOS
// ═══════════════════════════════════════════════════════════════════════════

/** O cartão da espinha econômica. O valor é sempre texto já formatado. */
const CartaoDeMedida: React.FC<{
  rotulo: string;
  valor: string;
  glifo: React.ComponentType<{ className?: string }>;
  nota: string;
  faixa?: string;
  ordem: number;
}> = ({ rotulo, valor, glifo: Glifo, nota, faixa, ordem }) => (
  <Card className="relative overflow-hidden reveal hover-lift" style={{ '--i': ordem } as React.CSSProperties}>
    {faixa && <span className={cn('pointer-events-none absolute inset-x-0 top-0 h-0.5', faixa)} />}
    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
      <span className="kicker">{rotulo}</span>
      <span className="rounded-md bg-muted text-muted-foreground p-1.5">
        <Glifo className="h-4 w-4" aria-hidden />
      </span>
    </CardHeader>
    <CardContent>
      <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight">{valor}</div>
      <div className="mt-2 text-xs leading-snug text-muted-foreground">{nota}</div>
    </CardContent>
  </Card>
);

const Kicker: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex items-center gap-3">
    <span className="kicker whitespace-nowrap">{children}</span>
    <span className="hairline-aurora flex-1" />
  </div>
);

/** "Isto é uma página, e ainda falta." — `completo`/`has_more`, ditos. */
const Continuacao: React.FC<{
  pagina: PaginaMetaReadModel;
  quePagina: string;
  carregandoMais: boolean;
  carregarMais: (() => void) | null;
}> = ({ pagina, quePagina, carregandoMais, carregarMais }) => {
  // Escopo recusado e falha de leitura NÃO são "leitura incompleta": elas já
  // têm o próprio bloco, e repetir "isto não é o total" embaixo de uma recusa
  // faria a tela parecer ter lido alguma coisa.
  if (pagina.estado !== 'COM_SNAPSHOT' && pagina.estado !== 'SEM_SNAPSHOT') return null;
  if (pagina.completo && !pagina.has_more) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <p className="max-w-[70ch] text-[12px] leading-snug text-muted-foreground">
        {pagina.has_more
          ? `Esta é uma página de ${quePagina}: o servidor declara que há mais linhas neste escopo.`
          : `O servidor declarou esta leitura de ${quePagina} incompleta${
              pagina.motivo === 'ESCOPO_PAI_TRUNCADO'
                ? ' — o escopo acima passou do teto que o servidor resolve de uma vez.'
                : '.'
            }`}{' '}
        O que está na tela não pode ser lido como o total.
      </p>
      {carregarMais && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 px-3 text-xs"
          disabled={carregandoMais}
          aria-busy={carregandoMais || undefined}
          onClick={carregarMais}
        >
          {carregandoMais ? 'lendo próxima página…' : 'ler próxima página'}
        </Button>
      )}
    </div>
  );
};

/**
 * `completo: false` numa leitura QUE ACONTECEU vira o aviso de leitura parcial.
 *
 * ⚠️ Uma recusa de escopo também traz `completo: false`, e contá-la aqui faria
 * a tela dizer "parte desta conta não pôde ser lida" sobre uma conta que nunca
 * chegou a ser perguntada. Parcial é sobre o que voltou pela metade, não sobre
 * o que não foi pedido.
 */
export function ehLeituraQueAconteceu(pagina: PaginaMetaReadModel | null): boolean {
  return Boolean(pagina) && (pagina!.estado === 'COM_SNAPSHOT' || pagina!.estado === 'SEM_SNAPSHOT');
}

function faltouDe(paginas: Array<PaginaMetaReadModel | null>, identificacao: string) {
  return paginas
    .filter((p): p is PaginaMetaReadModel => ehLeituraQueAconteceu(p) && !p!.completo)
    .map((p) => ({
      customer_id: identificacao,
      escopo: p.entidade === 'insights' ? 'metricas' : 'campanhas',
      motivo: '',
    }));
}

// ═══════════════════════════════════════════════════════════════════════════
// A HIERARQUIA
// ═══════════════════════════════════════════════════════════════════════════

const chave = (item: ItemMetaReadModel, i: number): string =>
  String(
    item.entity_ref ??
      item.meta_ad_id ??
      item.meta_adset_id ??
      item.meta_campaign_id ??
      item.meta_creative_id ??
      i,
  );

const Peca: React.FC<{ criativo: ItemMetaReadModel | null }> = ({ criativo }) => {
  if (!criativo) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
        <ImageIcon className="h-3 w-3 shrink-0" aria-hidden />
        {AUSENTE} sem peça vinculada nesta leitura
      </span>
    );
  }
  return (
    <span className="inline-flex min-w-0 max-w-full items-start gap-1.5 text-[12px]">
      <ImageIcon className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0">
        {/* Nome de criativo e `object_story_id` são livres e longos. `break-words`
            impede que a coluna estoure a tabela e force rolagem lateral da página. */}
        <span className="block break-words font-medium">{textoOuAusente(criativo.nome)}</span>
        {criativo.object_story_id && (
          <span className="mt-0.5 block break-all text-[11px] text-muted-foreground">
            {String(criativo.object_story_id)}
          </span>
        )}
      </span>
    </span>
  );
};

interface Arvore {
  conjunto: ItemMetaReadModel;
  anuncios: Array<{ anuncio: ItemMetaReadModel; criativo: ItemMetaReadModel | null }>;
}

function montarArvore(
  campanhaId: string | null,
  conjuntos: ItemMetaReadModel[],
  anuncios: ItemMetaReadModel[],
  criativos: ItemMetaReadModel[],
  vinculos: ItemMetaReadModel[],
): Arvore[] {
  const criativoPorId = new Map(
    criativos.map((c) => [String(c.meta_creative_id ?? ''), c] as const),
  );
  const criativoDoAnuncio = new Map(
    vinculos.map((v) => [String(v.meta_ad_id ?? ''), String(v.meta_creative_id ?? '')] as const),
  );
  const doEscopo = campanhaId
    ? conjuntos.filter((c) => String(c.meta_campaign_id ?? '') === campanhaId)
    : [];
  return doEscopo.map((conjunto) => {
    const id = String(conjunto.meta_adset_id ?? '');
    return {
      conjunto,
      anuncios: anuncios
        .filter((a) => String(a.meta_adset_id ?? '') === id)
        .map((anuncio) => ({
          anuncio,
          criativo:
            criativoPorId.get(criativoDoAnuncio.get(String(anuncio.meta_ad_id ?? '')) ?? '') ?? null,
        })),
    };
  });
}

const LinhaDeAnuncio: React.FC<{
  anuncio: ItemMetaReadModel;
  criativo: ItemMetaReadModel | null;
  densidade: Densidade;
}> = ({ anuncio, criativo, densidade }) => {
  if (densidade === 'compacta') {
    return (
      <li className="border-t border-border/60 px-3 py-2.5">
        <p className="break-words text-[13px] font-medium">{textoOuAusente(anuncio.nome)}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <SeloDeEstadoMeta estado={anuncio.effective_status} />
          <span className="tabular text-[11px] text-muted-foreground">
            {textoOuAusente(anuncio.id_mascarado)}
          </span>
        </div>
        <div className="mt-1.5">
          <Peca criativo={criativo} />
        </div>
      </li>
    );
  }
  return (
    <tr className="border-t border-border/60 align-top">
      <td className="px-3 py-2.5">
        <SeloDeEstadoMeta estado={anuncio.effective_status} />
      </td>
      <td className="px-3 py-2.5">
        <span className="block max-w-[42ch] break-words text-[13px] font-medium">
          {textoOuAusente(anuncio.nome)}
        </span>
        <span className="tabular text-[11px] text-muted-foreground">
          {textoOuAusente(anuncio.id_mascarado)}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <div className="max-w-[46ch]">
          <Peca criativo={criativo} />
        </div>
      </td>
    </tr>
  );
};

const Hierarquia: React.FC<{
  arvore: Arvore[];
  densidade: Densidade;
  temCampanha: boolean;
}> = ({ arvore, densidade, temCampanha }) => {
  if (!temCampanha) return null;
  if (arvore.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border bg-card px-4 py-6 text-[13px] text-muted-foreground">
        Nenhum conjunto desta campanha apareceu no que foi lido. Isso é o que o snapshot
        contém — não uma afirmação de que a campanha não tem conjuntos na Meta.
      </p>
    );
  }
  if (densidade === 'compacta') {
    return (
      <div className="rounded-md border border-border bg-card">
        {arvore.map(({ conjunto, anuncios }, i) => (
          <section key={chave(conjunto, i)} className="border-b border-border last:border-b-0">
            <div className="px-3 py-3">
              <p className="break-words font-display text-[15px] font-semibold">
                {textoOuAusente(conjunto.nome)}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <SeloDeEstadoMeta estado={conjunto.effective_status} />
                <span className="text-[11px] text-muted-foreground">
                  otimização: {textoOuAusente(conjunto.optimization_goal)}
                </span>
              </div>
            </div>
            {anuncios.length === 0 ? (
              <p className="border-t border-border/60 px-3 py-2.5 text-[12px] text-muted-foreground">
                {AUSENTE} nenhum anúncio deste conjunto veio nesta leitura
              </p>
            ) : (
              <ul className="list-none">
                {anuncios.map(({ anuncio, criativo }, j) => (
                  <LinhaDeAnuncio
                    key={chave(anuncio, j)}
                    anuncio={anuncio}
                    criativo={criativo}
                    densidade={densidade}
                  />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    );
  }
  return (
    // A largura mora AQUI e não no `body`: uma tabela larga rola dentro da
    // própria caixa, e a página nunca ganha rolagem lateral.
    <div className="overflow-x-auto rounded-md border border-border bg-card">
      <table className="w-full min-w-[46rem] text-left text-sm">
        <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2.5 font-semibold">Estado</th>
            <th scope="col" className="px-3 py-2.5 font-semibold">Anúncio</th>
            <th scope="col" className="px-3 py-2.5 font-semibold">Peça vinculada</th>
          </tr>
        </thead>
        {arvore.map(({ conjunto, anuncios }, i) => (
          <tbody key={chave(conjunto, i)} className="border-b border-border last:border-b-0">
            <tr>
              <th scope="rowgroup" colSpan={3} className="px-3 py-3 text-left font-normal">
                <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  conjunto
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="break-words font-display text-[15px] font-semibold">
                    {textoOuAusente(conjunto.nome)}
                  </span>
                  <SeloDeEstadoMeta estado={conjunto.effective_status} />
                  <span className="text-[11px] text-muted-foreground">
                    otimização: {textoOuAusente(conjunto.optimization_goal)}
                  </span>
                </span>
              </th>
            </tr>
            {anuncios.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-2.5 text-[12px] text-muted-foreground">
                  {AUSENTE} nenhum anúncio deste conjunto veio nesta leitura
                </td>
              </tr>
            ) : (
              anuncios.map(({ anuncio, criativo }, j) => (
                <LinhaDeAnuncio
                  key={chave(anuncio, j)}
                  anuncio={anuncio}
                  criativo={criativo}
                  densidade={densidade}
                />
              ))
            )}
          </tbody>
        ))}
      </table>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// INSIGHTS DA CONTA
// ═══════════════════════════════════════════════════════════════════════════

/**
 * ⚠️ Isto é o que a CONTA mediu, não o que esta campanha mediu.
 *
 * `objeto_externo` é removido de toda linha antes de ela sair do servidor. Sem
 * ele, não existe caminho honesto para dizer que uma destas linhas pertence a
 * esta campanha — e a tabela diz isso no título, e não numa nota de rodapé.
 */
const InsightsDaConta: React.FC<{ pagina: PaginaMetaReadModel; moeda: string | null }> = ({
  pagina,
  moeda,
}) => {
  if (pagina.items.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-card">
      <table className="w-full min-w-[54rem] text-left text-sm">
        <caption className="sr-only">
          Linhas de insight da conta, sem atribuição a um objeto
        </caption>
        <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2.5 font-semibold">Nível</th>
            <th scope="col" className="px-3 py-2.5 font-semibold">Período</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">Gasto</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">Impressões</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">Alcance</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">Cliques no link</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">LP views</th>
            <th scope="col" className="px-3 py-2.5 text-right font-semibold">CTR</th>
          </tr>
        </thead>
        <tbody>
          {pagina.items.map((linha, i) => (
            <tr key={String(linha.meta_insight_daily_id ?? i)} className="border-t border-border/60">
              <td className="px-3 py-2.5">{textoOuAusente(linha.nivel)}</td>
              <td className="px-3 py-2.5 tabular whitespace-nowrap">
                {textoOuAusente(linha.periodo_inicio)} → {textoOuAusente(linha.periodo_fim)}
              </td>
              <td className="px-3 py-2.5 text-right tabular">
                {dinheiroMeta(linha.spend, (linha.currency as string | null) ?? moeda)}
              </td>
              <td className="px-3 py-2.5 text-right tabular">{contagemMeta(linha.impressions)}</td>
              <td className="px-3 py-2.5 text-right tabular">{contagemMeta(linha.reach)}</td>
              <td className="px-3 py-2.5 text-right tabular">
                {contagemMeta(linha.inline_link_clicks)}
              </td>
              <td className="px-3 py-2.5 text-right tabular">
                {contagemMeta(linha.landing_page_views)}
              </td>
              <td className="px-3 py-2.5 text-right tabular">{decimalMeta(linha.ctr, 2, '%')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// A VISTA
// ═══════════════════════════════════════════════════════════════════════════

export interface MetaCampaignReadViewProps {
  /** UUID persistido OU a referência `metaobj_…` do recibo de criação. */
  referencia: string;
  /** A conta escolhida pela URL, quando houve escolha. */
  contaRef?: string | null;
  /** Chamado quando o operador troca de conta, para a URL acompanhar. */
  aoEscolherConta?: (contaRef: string) => void;
  /** Volta à origem. Sem isto, a página não mostra o controle. */
  aoVoltar?: () => void;
}

export const MetaCampaignReadView: React.FC<MetaCampaignReadViewProps> = ({
  referencia,
  contaRef: contaPreferida = null,
  aoEscolherConta,
  aoVoltar,
}) => {
  const densidade = useDensidade();
  const escopo = useEscopoDeConta(contaPreferida);
  const { contaRef, conta, contas } = escopo;

  const campanha = useDetalheDoReadModel('campanhas', referencia, contaRef);
  const conjuntos = usePaginaDoReadModel('conjuntos', contaRef);
  const anuncios = usePaginaDoReadModel('anuncios', contaRef);
  const criativos = usePaginaDoReadModel('criativos', contaRef);
  const vinculos = usePaginaDoReadModel('vinculos', contaRef);
  const insights = usePaginaDoReadModel('insights', contaRef);

  const escolher = React.useCallback(
    (proxima: string) => {
      escopo.escolher(proxima);
      aoEscolherConta?.(proxima);
    },
    [escopo, aoEscolherConta],
  );

  const paginaDe = (p: PaginaEmLeitura): PaginaMetaReadModel | null =>
    p.leitura.fase === 'respondeu' ? p.leitura.resposta : null;

  const itemCampanha =
    campanha.leitura.fase === 'respondeu' ? campanha.leitura.resposta.item : null;
  const campanhaId = itemCampanha ? String(itemCampanha.meta_campaign_id ?? '') : null;

  const arvore = React.useMemo(
    () =>
      montarArvore(
        campanhaId,
        paginaDe(conjuntos)?.items ?? [],
        paginaDe(anuncios)?.items ?? [],
        paginaDe(criativos)?.items ?? [],
        paginaDe(vinculos)?.items ?? [],
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [campanhaId, conjuntos.leitura, anuncios.leitura, criativos.leitura, vinculos.leitura],
  );

  const paginas = [
    paginaDe(conjuntos),
    paginaDe(anuncios),
    paginaDe(criativos),
    paginaDe(vinculos),
    paginaDe(insights),
  ];
  const parcial = paginas.some((p) => ehLeituraQueAconteceu(p) && !p!.completo);
  const moeda = conta?.moeda ?? paginas.find((p) => p?.moeda)?.moeda ?? null;
  const fuso = conta?.timezone_name ?? paginas.find((p) => p?.fuso)?.fuso ?? null;
  const identificacaoDaConta =
    conta?.id_mascarado ?? conta?.nome_observado ?? 'conta não identificada';

  const espinha = (
    <>
      <Kicker>Métricas principais</Kicker>
      <p className="max-w-[80ch] text-[13px] leading-relaxed text-muted-foreground">
        Nenhuma medida abaixo pôde ser atribuída a esta campanha. As linhas de insight que o
        read model devolve são fatos <span className="font-medium text-foreground">da conta</span>:
        o servidor remove a referência do objeto antes de enviá-las, e não existe caminho honesto
        para dizer que um gasto da conta é o gasto desta campanha. Ausência aparece como{' '}
        <span className="tabular font-medium text-foreground">{AUSENTE}</span> — nunca como zero.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <CartaoDeMedida
          rotulo="Investimento Total"
          valor={AUSENTE}
          glifo={DollarSign}
          nota="gasto não atribuído a esta campanha"
          ordem={2}
        />
        <CartaoDeMedida
          rotulo="Revenue"
          valor={AUSENTE}
          glifo={TrendingUp}
          nota="nenhuma receita foi vinculada a esta campanha"
          ordem={3}
        />
        <CartaoDeMedida
          rotulo="Retorno excedente (%)"
          valor={AUSENTE}
          glifo={Target}
          nota="excedente sobre o gasto, em pontos percentuais — não é a razão receita ÷ gasto"
          ordem={4}
        />
        <CartaoDeMedida
          rotulo="Lucro Bruto"
          valor={AUSENTE}
          glifo={TrendingUp}
          nota="revenue − mídia; sem as duas parcelas não há diferença a mostrar"
          ordem={5}
        />
      </div>
    </>
  );

  // ── a conta ainda não foi resolvida ──────────────────────────────────────
  let corpo: React.ReactNode;
  if (escopo.leitura.fase === 'lendo') {
    corpo = <EsqueletoDoInventario contas={1} linhas={3} />;
  } else if (escopo.leitura.fase === 'falhou') {
    corpo = (
      <FalhaDoInventario ocorrencia={escopo.leitura.ocorrencia} aoTentarDeNovo={escopo.recarregar} />
    );
  } else if (escopo.leitura.resposta.estado !== 'COM_SNAPSHOT') {
    corpo = (
      <EstadoDoReadModel
        estado={escopo.leitura.resposta.estado}
        aoTentarDeNovo={escopo.recarregar}
      />
    );
  } else if (contas.length === 0) {
    corpo = <InventarioVazio />;
  } else if (!contaRef) {
    corpo = (
      <div className="space-y-4">
        {/* "não pedi conta" e "pedi uma conta que não existe neste snapshot"
            são respostas diferentes, e a segunda precisa dizer o que não
            reconheceu — senão o operador conclui que a conta sumiu. */}
        <EstadoDoReadModel
          estado={escopo.escopoDesconhecido ? 'ESCOPO_DESCONHECIDO' : 'ESCOPO_OBRIGATORIO'}
        />
        <EscolhaDeConta
          contas={contas}
          escolhida={null}
          aoEscolher={escolher}
          forcarVisibilidade={escopo.escopoDesconhecido}
        />
      </div>
    );
  } else {
    corpo = (
      <div className="space-y-4 md:space-y-6">
        <CabecalhoDaConta conta={conta!} parcial={parcial} moeda={moeda} fuso={fuso} />
        <EscolhaDeConta contas={contas} escolhida={contaRef} aoEscolher={escolher} />

        {campanha.leitura.fase === 'lendo' && <EsqueletoDoInventario contas={1} linhas={2} />}
        {campanha.leitura.fase === 'falhou' && (
          <FalhaDoInventario
            ocorrencia={campanha.leitura.ocorrencia}
            aoTentarDeNovo={campanha.recarregar}
          />
        )}
        {campanha.leitura.fase === 'respondeu' && !itemCampanha && (
          <EstadoDoReadModel
            estado={campanha.leitura.resposta.estado}
            aoTentarDeNovo={campanha.recarregar}
          />
        )}

        {itemCampanha && (
          <Card className="reveal hover-lift" style={{ '--i': 1 } as React.CSSProperties}>
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="flex min-w-0 items-center gap-2 font-display">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5">
                    <Target className="h-4 w-4" aria-hidden />
                  </span>
                  <span className="break-words">{textoOuAusente(itemCampanha.nome)}</span>
                </CardTitle>
                <IdentidadeDeCanal rede="meta" />
                <SeloDeEstadoMeta estado={itemCampanha.effective_status} />
              </div>
              <CardDescription className="text-sm">
                <span className="mt-1 block break-words">
                  <strong>Objetivo:</strong> {textoOuAusente(itemCampanha.objetivo)} ·{' '}
                  <strong>Estado configurado:</strong> {textoOuAusente(itemCampanha.status)}
                </span>
                <span className="mt-1 block break-all text-[12px] text-muted-foreground">
                  <strong className="font-medium">Identidade:</strong>{' '}
                  {textoOuAusente(itemCampanha.entity_ref)} ·{' '}
                  {textoOuAusente(itemCampanha.id_mascarado)}
                </span>
                <span className="mt-1 block text-[12px] text-muted-foreground">
                  <strong className="font-medium">Observada em:</strong>{' '}
                  {horaDeLeitura(itemCampanha.observado_em as string | null) ?? AUSENTE}
                </span>
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {parcial && (
          <AvisoDeLeituraParcial faltou={faltouDe(paginas, identificacaoDaConta)} />
        )}

        {espinha}

        <Kicker>Campanha → conjuntos → anúncios → peça</Kicker>
        {[conjuntos, anuncios, criativos, vinculos].some((p) => p.leitura.fase === 'lendo') ? (
          <EsqueletoDoInventario contas={1} linhas={4} />
        ) : (
          <>
            {[conjuntos, anuncios, criativos, vinculos].map((p, i) =>
              p.leitura.fase === 'falhou' ? (
                <FalhaDoInventario
                  key={i}
                  ocorrencia={p.leitura.ocorrencia}
                  aoTentarDeNovo={p.recarregar}
                />
              ) : null,
            )}
            {conjuntos.leitura.fase === 'respondeu' &&
              conjuntos.leitura.resposta.estado !== 'COM_SNAPSHOT' && (
                <EstadoDoReadModel
                  estado={conjuntos.leitura.resposta.estado}
                  aoTentarDeNovo={conjuntos.recarregar}
                />
              )}
            <Hierarquia arvore={arvore} densidade={densidade} temCampanha={Boolean(itemCampanha)} />
            {paginaDe(conjuntos) && (
              <Continuacao
                pagina={paginaDe(conjuntos)!}
                quePagina="conjuntos"
                carregandoMais={conjuntos.carregandoMais}
                carregarMais={conjuntos.carregarMais}
              />
            )}
            {paginaDe(anuncios) && (
              <Continuacao
                pagina={paginaDe(anuncios)!}
                quePagina="anúncios"
                carregandoMais={anuncios.carregandoMais}
                carregarMais={anuncios.carregarMais}
              />
            )}
            {paginaDe(criativos) && (
              <Continuacao
                pagina={paginaDe(criativos)!}
                quePagina="criativos"
                carregandoMais={criativos.carregandoMais}
                carregarMais={criativos.carregarMais}
              />
            )}
          </>
        )}

        <Kicker>Insights da conta</Kicker>
        <p className="max-w-[80ch] text-[13px] leading-relaxed text-muted-foreground">
          Estas linhas pertencem à conta{' '}
          <span className="tabular font-medium text-foreground">{identificacaoDaConta}</span> e não
          a um objeto: o servidor remove a referência do objeto antes de enviá-las. Elas estão aqui
          porque são medidas reais, e fora dos cartões acima porque atribuí-las a esta campanha
          seria inventar.
        </p>
        {insights.leitura.fase === 'lendo' && <EsqueletoDoInventario contas={1} linhas={3} />}
        {insights.leitura.fase === 'falhou' && (
          <FalhaDoInventario
            ocorrencia={insights.leitura.ocorrencia}
            aoTentarDeNovo={insights.recarregar}
          />
        )}
        {insights.leitura.fase === 'respondeu' &&
          (insights.leitura.resposta.estado === 'COM_SNAPSHOT' ? (
            <>
              <InsightsDaConta pagina={insights.leitura.resposta} moeda={moeda} />
              <Continuacao
                pagina={insights.leitura.resposta}
                quePagina="insights"
                carregandoMais={insights.carregandoMais}
                carregarMais={insights.carregarMais}
              />
            </>
          ) : (
            <EstadoDoReadModel
              estado={insights.leitura.resposta.estado}
              aoTentarDeNovo={insights.recarregar}
            />
          ))}
      </div>
    );
  }

  return (
    <div className={cn(densidade === 'compacta' ? 'p-4' : 'p-6', 'space-y-4 md:space-y-6')}>
      <div className="flex items-start gap-4">
        {aoVoltar && (
          <Button
            variant="ghost"
            size="sm"
            onClick={aoVoltar}
            className="flex-shrink-0 gap-2 touch-target"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Voltar
          </Button>
        )}
        <div className="min-w-0 flex-1">
          <div className="kicker mb-2">Leitura do read model Meta</div>
          <h1
            className={cn(
              'font-display font-bold tracking-tight leading-[1.05]',
              densidade === 'compacta' ? 'text-2xl' : 'text-4xl',
            )}
          >
            Dashboard da Campanha
          </h1>
          <div className="mt-3 aurora-rule w-16" />
          <p className="mt-3 max-w-[80ch] break-all text-sm text-muted-foreground">
            Identidade: {referencia}
          </p>
          <p className="mt-1 max-w-[80ch] text-sm text-muted-foreground">
            Somente leitura. Não há ativação, edição nem ato de orçamento neste marco — e por isso
            não há botão para nenhum deles.
          </p>
        </div>
      </div>
      {corpo}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// O CATÁLOGO REAL — o que `/settings/campaigns?rede=meta` passa a montar
// ═══════════════════════════════════════════════════════════════════════════

/**
 * As campanhas que EXISTEM no read model, em tabela.
 *
 * `design.md`: "Inventário é TABELA, nunca grade de cards iguais." A grade de
 * cartões da demonstração comparava quatro números por campanha; aqui não há
 * número por campanha para comparar (ver a nota sobre atribuição no topo), e
 * uma grade de cartões sem números seria decoração ocupando a tela inteira.
 */
export const MetaCatalogoReal: React.FC<{
  contaRef?: string | null;
  aoEscolherConta?: (contaRef: string) => void;
  hrefDaCampanha?: (referencia: string, contaRef: string) => string;
}> = ({ contaRef: contaPreferida = null, aoEscolherConta, hrefDaCampanha }) => {
  const densidade = useDensidade();
  const escopo = useEscopoDeConta(contaPreferida);
  const { contaRef, conta, contas } = escopo;
  const campanhas = usePaginaDoReadModel('campanhas', contaRef, Boolean(contaRef));

  const escolher = React.useCallback(
    (proxima: string) => {
      escopo.escolher(proxima);
      aoEscolherConta?.(proxima);
    },
    [escopo, aoEscolherConta],
  );

  const href = React.useCallback(
    (referencia: string) =>
      hrefDaCampanha
        ? hrefDaCampanha(referencia, contaRef ?? '')
        : `/dashboard/campaign/${encodeURIComponent(referencia)}?rede=meta&conta=${encodeURIComponent(contaRef ?? '')}`,
    [hrefDaCampanha, contaRef],
  );

  if (escopo.leitura.fase === 'lendo') return <EsqueletoDoInventario contas={1} linhas={4} />;
  if (escopo.leitura.fase === 'falhou') {
    return (
      <FalhaDoInventario ocorrencia={escopo.leitura.ocorrencia} aoTentarDeNovo={escopo.recarregar} />
    );
  }
  if (escopo.leitura.resposta.estado !== 'COM_SNAPSHOT') {
    return (
      <EstadoDoReadModel estado={escopo.leitura.resposta.estado} aoTentarDeNovo={escopo.recarregar} />
    );
  }
  if (contas.length === 0) return <InventarioVazio />;

  const pagina = campanhas.leitura.fase === 'respondeu' ? campanhas.leitura.resposta : null;
  const moeda = conta?.moeda ?? pagina?.moeda ?? null;
  const fuso = conta?.timezone_name ?? pagina?.fuso ?? null;

  return (
    <div className="space-y-4">
      {conta && (
        <CabecalhoDaConta
          conta={conta}
          parcial={ehLeituraQueAconteceu(pagina) && !pagina!.completo}
          moeda={moeda}
          fuso={fuso}
        />
      )}
      <EscolhaDeConta
        contas={contas}
        escolhida={contaRef}
        aoEscolher={escolher}
        forcarVisibilidade={escopo.escopoDesconhecido}
      />

      {!contaRef && (
        <EstadoDoReadModel
          estado={escopo.escopoDesconhecido ? 'ESCOPO_DESCONHECIDO' : 'ESCOPO_OBRIGATORIO'}
        />
      )}
      {campanhas.leitura.fase === 'lendo' && <EsqueletoDoInventario contas={1} linhas={4} />}
      {campanhas.leitura.fase === 'falhou' && (
        <FalhaDoInventario
          ocorrencia={campanhas.leitura.ocorrencia}
          aoTentarDeNovo={campanhas.recarregar}
        />
      )}
      {pagina && pagina.estado !== 'COM_SNAPSHOT' && (
        <EstadoDoReadModel estado={pagina.estado} aoTentarDeNovo={campanhas.recarregar} />
      )}
      {pagina && pagina.estado === 'COM_SNAPSHOT' && (
        <>
          {densidade === 'compacta' ? (
            <ul className="list-none rounded-md border border-border bg-card">
              {pagina.items.map((item, i) => {
                const ref = String(item.entity_ref ?? item.meta_campaign_id ?? '');
                return (
                  <li key={chave(item, i)} className="border-b border-border last:border-b-0 px-3 py-3">
                    <Link to={href(ref)} className="block break-words font-medium text-primary hover:underline">
                      {textoOuAusente(item.nome)}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <SeloDeEstadoMeta estado={item.effective_status} />
                      <span className="text-[11px] text-muted-foreground">
                        {textoOuAusente(item.objetivo)}
                      </span>
                      <span className="tabular text-[11px] text-muted-foreground">
                        {textoOuAusente(item.id_mascarado)}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border bg-card">
              <table className="w-full min-w-[48rem] text-left text-sm">
                <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Estado</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Campanha</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Objetivo</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Identidade</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Observada em</th>
                  </tr>
                </thead>
                <tbody>
                  {pagina.items.map((item, i) => {
                    const ref = String(item.entity_ref ?? item.meta_campaign_id ?? '');
                    return (
                      <tr key={chave(item, i)} className="border-t border-border/60 align-top">
                        <td className="px-3 py-2.5">
                          <SeloDeEstadoMeta estado={item.effective_status} />
                        </td>
                        <td className="px-3 py-2.5">
                          <Link
                            to={href(ref)}
                            className="block max-w-[40ch] break-words font-medium text-primary hover:underline"
                          >
                            {textoOuAusente(item.nome)}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5">{textoOuAusente(item.objetivo)}</td>
                        <td className="px-3 py-2.5 tabular text-[12px] text-muted-foreground">
                          {textoOuAusente(item.id_mascarado)}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap text-[12px] text-muted-foreground">
                          {horaDeLeitura(item.observado_em as string | null) ?? AUSENTE}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <Continuacao
            pagina={pagina}
            quePagina="campanhas"
            carregandoMais={campanhas.carregandoMais}
            carregarMais={campanhas.carregarMais}
          />
        </>
      )}
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════
// A PÁGINA DE CATÁLOGO — `/settings/campaigns?rede=meta`
// ═══════════════════════════════════════════════════════════════════════════

/**
 * O catálogo Meta como PÁGINA, com a espinha de cabeçalho do `design.md`.
 *
 * ⚠️ POR QUE ESTA PÁGINA MORA AQUI E NÃO EM `CampaignsSettings.tsx`.
 *
 * `CampaignsSettings` é a casa do painel do GOOGLE, e o Google não pode se
 * mexer neste marco. O único ponto daquele arquivo que muda é a decisão de
 * montagem — uma linha — e tudo que é Meta fica do lado Meta. É a mesma
 * separação que já existe entre `GoogleCampaignsSettings` e a demonstração.
 *
 * A entrada da demonstração é um LINK, e está escrito o que ela é. Ela deixou
 * de ser o destino automático de `?rede=meta`: um cenário fictício não pode ser
 * o que aparece quando alguém pede a lista real e a leitura ainda não existe —
 * é assim que uma tela de demonstração vira o painel de produção sem que
 * ninguém tenha decidido isso.
 */
export const MetaCampanhasSettingsReal: React.FC<{
  onNetworkChange: (rede: 'google' | 'meta') => void;
  contaRef?: string | null;
  aoEscolherConta?: (contaRef: string) => void;
  hrefDaDemonstracao?: string;
}> = ({
  onNetworkChange,
  contaRef = null,
  aoEscolherConta,
  hrefDaDemonstracao = '/settings/campaigns?rede=meta&modo=demo',
}) => {
  const densidade = useDensidade();
  return (
    <Layout>
      <div
        className={cn(
          densidade === 'compacta' ? 'p-4' : 'p-6',
          'mx-auto max-w-7xl space-y-6 md:space-y-8',
        )}
      >
        <div className="space-y-4">
          <div className="min-w-0">
            <div className="kicker mb-2">Configurações · Campanhas</div>
            <h1
              className={cn(
                'font-display font-bold tracking-tight leading-[1.05]',
                densidade === 'compacta' ? 'text-[1.7rem]' : 'text-4xl',
              )}
            >
              Campanhas
            </h1>
            <div className="mt-3 aurora-rule w-16" />
            <p className="mt-3 max-w-[80ch] text-sm text-muted-foreground">
              O que a leitura da conta Meta persistiu no read model — nada mais. Somente leitura:
              não há ativação, edição nem ato de orçamento neste marco.
            </p>
          </div>

          <SeletorRedeCampanhas rede="meta" onChange={onNetworkChange} />
        </div>

        <MetaCatalogoReal contaRef={contaRef} aoEscolherConta={aoEscolherConta} />

        <p className="text-[12px] leading-relaxed text-muted-foreground">
          <Link
            to={hrefDaDemonstracao}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            abrir o cenário demonstrativo
          </Link>{' '}
          — números inventados, para conhecer a forma da tela. Ele não é lido por engano: só
          abre por este link, e diz na tela que é demonstração.
        </p>
      </div>
    </Layout>
  );
};

export default MetaCampaignReadView;
