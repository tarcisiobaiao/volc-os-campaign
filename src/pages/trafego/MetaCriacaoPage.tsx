/**
 * A bancada de criação Meta.
 *
 * ## Por que ela é irmã da bancada Google, e não um produto novo
 *
 * `design.md` diz duas coisas que decidem esta página: "this file is the only
 * product-UI authority… Do not invent a third visual language" e "Create studio.
 * Creation is a channel-specific operational bench". As duas juntas significam
 * que o Meta tem a SUA jornada, mas no MESMO vocabulário do lançamento Google
 * (`NovaCampanhaPage.tsx`): `bancada-command-deck`, `bancada-route`,
 * `bancada-stage`, `bancada-grid` e as peças de `components/trafego/bancada`.
 *
 * O trilho de etapas é desenhado aqui em vez de reusar `MapaDeParadas` porque
 * aquele componente é tipado por `ParadaDaBancada`, uma união fechada das
 * paradas do Google. Estender a união arrastaria os `Record` exaustivos de
 * `bancada/paradas.ts` para dentro de uma missão que não é sobre o Google. O
 * DESENHO é o mesmo — as classes `.bancada-route*` são as mesmas — e é o
 * desenho que o contrato de UI governa.
 *
 * ## ⚠️ O que esta tela pode e o que ela não pode
 *
 * Ela lê a conta real, compila o plano no backend e — só depois de clique
 * explícito e liberação do servidor — pede à Meta uma validação que não cria
 * nada. Não existe caminho de criação nem de ativação aqui.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, CircleCheck, CircleDot, Copy, Film, Image as ImageIcon,
  Layers3, Lock, Megaphone, Plus, ShieldCheck, Trash2,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import {
  AcaoDominante, BlocoDeEvidencia, ChipDeEstado, LinhaDeFato, PainelDeBloqueio, Pedido,
} from '@/components/trafego/bancada';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import {
  CAPACIDADES_FECHADAS, Draft, EstadoDaEtapa, EtapaId, LIMITE_VARIACOES, MidiaDaVariacao,
  VariacaoDraft, dominioDoDestino, formatarBrl, inicioEmIso, nomeUnico, paraPlano,
  prontidaoDasEtapas, prontoParaCompilar, proximaChave, reaisParaMinor, variacaoCompleta,
  variacaoInicial, variacoesEmitidas, type CapacidadesDaBancada,
} from '@/components/trafego/meta/rascunho';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  AtivoCriacaoMeta, ContaMetaLocal, PautadorApiError, pautadorApi,
  ResultadoCompilacaoMeta, ResultadoValidacaoPlanoMeta,
} from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';
import type { AvisoDoCockpit, LinhaDoPedido } from '@/types/trafego';

const ETAPAS = [
  { id: 'base', nome: 'Base', pergunta: 'De qual conta e Página esta campanha nasce?' },
  { id: 'campanha', nome: 'Campanha', pergunta: 'Que campanha você está autorizando?' },
  { id: 'orcamento', nome: 'Orçamento', pergunta: 'Quanto ela pode gastar por dia?' },
  { id: 'conjunto', nome: 'Conjunto', pergunta: 'Como o conjunto vai entregar?' },
  { id: 'publico', nome: 'Público', pergunta: 'Quem pode ser alcançado?' },
  { id: 'criativo', nome: 'Anúncios', pergunta: 'Quais anúncios vão nascer?' },
  { id: 'mensuracao', nome: 'Mensuração', pergunta: 'Para onde o clique leva?' },
  { id: 'revisao', nome: 'Revisão', pergunta: 'O que exatamente será enviado à Meta?' },
] as const satisfies readonly { id: EtapaId; nome: string; pergunta: string }[];

const DESENHO_DO_ESTADO: Record<
  EstadoDaEtapa,
  { Glifo: React.ComponentType<{ className?: string }>; palavra: string; tinta: string }
> = {
  pronto: { Glifo: CircleCheck, palavra: 'pronto', tinta: 'text-success' },
  pendente: { Glifo: CircleDot, palavra: 'pendente', tinta: 'text-muted-foreground' },
  bloqueado: { Glifo: Lock, palavra: 'bloqueado', tinta: 'text-destructive' },
  validado: { Glifo: ShieldCheck, palavra: 'validado', tinta: 'text-verified' },
};

const CTAS: readonly [string, string][] = [
  ['LEARN_MORE', 'Saiba mais'],
  ['APPLY_NOW', 'Inscreva-se'],
  ['SIGN_UP', 'Cadastre-se'],
  ['GET_QUOTE', 'Solicitar cotação'],
  ['CONTACT_US', 'Fale conosco'],
];

const inicioPadrao = () => {
  const data = new Date(Date.now() + 30 * 60 * 1000);
  data.setSeconds(0, 0);
  const local = new Date(data.getTime() - data.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const DRAFT_INICIAL: Draft = {
  accountRef: '', pageRef: '',
  campaignName: 'VOLC · Meta · Tráfego · LPV',
  adsetName: 'Brasil · Amplo · LPV · Automático',
  destinationUrl: 'https://focogenial.com/',
  budgetBrl: '10,00', startTime: inicioPadrao(),
  categoryConfirmed: false, budgetSharing: false, advantageAudience: false,
  creativeMode: 'single',
  variations: [variacaoInicial('variation-001', 1)],
};

/** Espelha a primitiva `Input` (h-10, rounded-md, anel `ring`) para que um
 *  `<select>` nativo não seja um segundo vocabulário de controle. */
const campo = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground ring-offset-background transition-volc duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';

const Campo: React.FC<{
  id: string; rotulo: string; ajuda?: string; children: React.ReactNode; largo?: boolean;
}> = ({ id, rotulo, ajuda, children, largo }) => (
  <div className={cn('space-y-2', largo && 'md:col-span-2')}>
    <Label htmlFor={id}>{rotulo}</Label>
    {children}
    {ajuda && <p className="max-w-[70ch] text-sm leading-relaxed text-pretty text-muted-foreground">{ajuda}</p>}
  </div>
);

const Escolha: React.FC<{
  marcado: boolean; onChange: (v: boolean) => void; titulo: string; children: React.ReactNode;
}> = ({ marcado, onChange, titulo, children }) => (
  <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border bg-muted/20 p-3 md:col-span-2">
    <input
      type="checkbox" checked={marcado} onChange={(e) => onChange(e.target.checked)}
      className="mt-0.5 h-4 w-4 shrink-0"
    />
    <span>
      <strong className="block text-sm text-foreground">{titulo}</strong>
      <span className="mt-1 block max-w-[72ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        {children}
      </span>
    </span>
  </label>
);

/** A prévia real da peça, servida pelo proxy autenticado do backend. */
const PreviaDaPeca: React.FC<{ accountRef: string; ativo?: AtivoCriacaoMeta }> = ({
  accountRef, ativo,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setErro(null);
    setUrl(null);
    if (!accountRef || !ativo?.referencia_opaca || !ativo.preview_disponivel) return;
    let vivo = true;
    let criada: string | null = null;
    pautadorApi.previewAtivoMeta(accountRef, ativo.referencia_opaca)
      .then((proxima) => {
        criada = proxima;
        if (vivo) setUrl(proxima);
        else URL.revokeObjectURL(proxima);
      })
      .catch((exc) => vivo && setErro(
        exc instanceof Error ? exc.message : 'Não foi possível carregar a prévia.'));
    return () => {
      vivo = false;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [accountRef, ativo?.referencia_opaca, ativo?.preview_disponivel]);

  const Glifo = ativo?.tipo === 'video_asset' ? Film : ImageIcon;
  return (
    <div className="flex min-h-40 items-center justify-center overflow-hidden rounded-lg border border-border/70 bg-muted/30">
      {url ? (
        <img
          src={url}
          alt={`Prévia de ${ativo?.nome || 'peça selecionada'}`}
          className="h-full max-h-64 w-full object-contain"
        />
      ) : (
        <div className="flex flex-col items-center gap-2 px-5 text-center text-sm text-muted-foreground">
          <Glifo className="h-7 w-7 opacity-50" aria-hidden />
          <span>{erro || (ativo?.preview_disponivel ? 'Carregando prévia…' : 'Prévia indisponível')}</span>
        </div>
      )}
    </div>
  );
};

/** Traduz a recusa do backend sem apagar código e subcódigo da Meta. */
function avisosDoErro(exc: unknown): AvisoDoCockpit[] {
  if (!(exc instanceof PautadorApiError)) {
    return [{
      codigo: 'ERRO_LOCAL', severidade: 'alta',
      titulo: 'A bancada não completou a operação',
      detalhe: exc instanceof Error ? exc.message : 'causa desconhecida',
    }];
  }
  const corpo = (exc.corpo ?? {}) as {
    codigo?: string;
    provedor?: { code?: string; error_subcode?: string; messages?: string[] };
  };
  const provedor = corpo.provedor;
  const avisos: AvisoDoCockpit[] = [{
    codigo: corpo.codigo || `HTTP_${exc.status}`,
    severidade: 'alta',
    titulo: exc.message,
    detalhe: provedor?.code
      ? `A Meta recusou com o código ${provedor.code}${provedor.error_subcode ? `/${provedor.error_subcode}` : ''}.`
      : 'Nenhum detalhe adicional foi devolvido.',
  }];
  for (const mensagem of provedor?.messages ?? []) {
    if (mensagem && mensagem !== exc.message) {
      avisos.push({
        codigo: `META_${provedor?.code ?? 'MSG'}`, severidade: 'alta',
        titulo: 'Explicação da Meta', detalhe: mensagem,
      });
    }
  }
  return avisos;
}

const MetaCriacaoPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const pedida = params.get('etapa') as EtapaId | null;
  const etapa: EtapaId = ETAPAS.some((item) => item.id === pedida) ? pedida! : 'base';
  const indice = ETAPAS.findIndex((item) => item.id === etapa);

  const [draft, setDraft] = useState<Draft>(DRAFT_INICIAL);
  const [contas, setContas] = useState<ContaMetaLocal[]>([]);
  const [paginas, setPaginas] = useState<AtivoCriacaoMeta[]>([]);
  const [imagens, setImagens] = useState<AtivoCriacaoMeta[]>([]);
  const [videos, setVideos] = useState<AtivoCriacaoMeta[]>([]);
  const [capacidades, setCapacidades] = useState<CapacidadesDaBancada>(CAPACIDADES_FECHADAS);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState<'ativos' | 'compilar' | 'validar' | null>(null);
  const [avisos, setAvisos] = useState<AvisoDoCockpit[]>([]);
  const [compilacao, setCompilacao] = useState<ResultadoCompilacaoMeta | null>(null);
  const [validacao, setValidacao] = useState<ResultadoValidacaoPlanoMeta | null>(null);

  // ⚠️ Toda resposta assíncrona carrega o selo do rascunho que a pediu. Sem
  // isso, o operador troca a URL enquanto a Meta responde e a resposta antiga
  // marca como validado um plano que já não existe.
  const selo = useRef(0);
  const invalidar = useCallback(() => {
    selo.current += 1;
    setCompilacao(null);
    setValidacao(null);
    setAvisos([]);
  }, []);

  useEffect(() => {
    let vivo = true;
    Promise.all([pautadorApi.contasMetaLocal(), pautadorApi.capacidadesCriacaoMeta()])
      .then(([inventario, cap]) => {
        if (!vivo) return;
        setContas(inventario.contas);
        const bloqueios = (cap.bloqueios ?? {}) as Record<string, string>;
        setCapacidades({
          validateOnly: cap.validate_only === 'ENABLED',
          loteEstatico: String(cap.static_batch ?? '').startsWith('AVAILABLE'),
          video: cap.video_creative === 'AVAILABLE',
          videoMotivo: bloqueios.video_creative ?? null,
          flexivel: cap.flexible_creative === 'AVAILABLE',
          flexivelMotivo: bloqueios.flexible_creative ?? null,
        });
        if (inventario.contas.length === 1) {
          setDraft((atual) => ({ ...atual, accountRef: inventario.contas[0].referencia_opaca }));
        }
      })
      .catch((exc) => vivo && setAvisos(avisosDoErro(exc)))
      .finally(() => vivo && setCarregando(false));
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    if (!draft.accountRef) { setPaginas([]); setImagens([]); setVideos([]); return; }
    let vivo = true;
    setOcupado('ativos');
    pautadorApi.ativosCriacaoMeta(draft.accountRef)
      .then((resultado) => {
        if (!vivo) return;
        setPaginas(resultado.paginas);
        setImagens(resultado.imagens);
        setVideos(resultado.videos ?? []);
        // A releitura pode trocar Página e peça do rascunho. Isso é mudança
        // material: a compilação anterior deixa de valer.
        invalidar();
        setDraft((atual) => ({
          ...atual,
          pageRef: resultado.paginas.some((item) => item.referencia_opaca === atual.pageRef)
            ? atual.pageRef : (resultado.paginas[0]?.referencia_opaca || ''),
          variations: atual.variations.map((variacao) => ({
            ...variacao,
            assetRef: resultado.imagens.some((item) => item.referencia_opaca === variacao.assetRef)
              ? variacao.assetRef : (resultado.imagens[0]?.referencia_opaca || ''),
            videoRef: (resultado.videos ?? []).some(
              (item) => item.referencia_opaca === variacao.videoRef)
              ? variacao.videoRef : ((resultado.videos ?? [])[0]?.referencia_opaca || ''),
          })),
        }));
      })
      .catch((exc) => vivo && setAvisos(avisosDoErro(exc)))
      .finally(() => vivo && setOcupado(null));
    return () => { vivo = false; };
  }, [draft.accountRef, invalidar]);

  const mudar = <K extends keyof Draft>(chave: K, valor: Draft[K]) => {
    setDraft((atual) => ({ ...atual, [chave]: valor }));
    invalidar();
  };
  const mudarVariacao = <K extends keyof VariacaoDraft>(
    posicaoAlvo: number, chave: K, valor: VariacaoDraft[K],
  ) => {
    setDraft((atual) => ({
      ...atual,
      variations: atual.variations.map((item, posicao) => (
        posicao === posicaoAlvo ? { ...item, [chave]: valor } : item
      )),
    }));
    invalidar();
  };
  const adicionarVariacao = (origem?: number) => {
    setDraft((atual) => {
      if (atual.variations.length >= LIMITE_VARIACOES) return atual;
      const chave = proximaChave(atual.variations.map((item) => item.key));
      const numero = atual.variations.length + 1;
      const base = origem === undefined
        ? { ...variacaoInicial(chave, numero), ...pecaPadrao(atual) }
        : { ...atual.variations[origem], key: chave };
      return {
        ...atual,
        creativeMode: 'batch',
        variations: [...atual.variations, {
          ...base,
          key: chave,
          creativeName: nomeUnico(base.creativeName, atual.variations.map((i) => i.creativeName)),
          adName: nomeUnico(base.adName, atual.variations.map((i) => i.adName)),
        }],
      };
    });
    invalidar();
  };
  const removerVariacao = (posicaoAlvo: number) => {
    setDraft((atual) => {
      const restantes = atual.variations.filter((_, posicao) => posicao !== posicaoAlvo);
      return {
        ...atual,
        creativeMode: restantes.length === 1 ? 'single' : atual.creativeMode,
        variations: restantes,
      };
    });
    invalidar();
  };
  /** Trocar de modo muda o que será emitido, então o rascunho acompanha. */
  const mudarModo = (modo: Draft['creativeMode']) => {
    setDraft((atual) => ({
      ...atual,
      creativeMode: modo,
      variations: modo === 'single' ? atual.variations.slice(0, 1) : atual.variations,
    }));
    invalidar();
  };
  function pecaPadrao(atual: Draft): Partial<VariacaoDraft> {
    const ultima = atual.variations.at(-1);
    return { assetRef: ultima?.assetRef ?? '', videoRef: ultima?.videoRef ?? '', midia: ultima?.midia ?? 'image' };
  }

  const navegar = (proxima: EtapaId) => {
    const novos = new URLSearchParams(params);
    novos.set('etapa', proxima);
    setParams(novos);
    const reduzido = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduzido ? 'auto' : 'smooth' });
  };

  const conta = contas.find((item) => item.referencia_opaca === draft.accountRef);
  const pagina = paginas.find((item) => item.referencia_opaca === draft.pageRef);
  const emitidas = variacoesEmitidas(draft);
  const estados = useMemo(
    () => prontidaoDasEtapas(draft, {
      capacidades, compilado: Boolean(compilacao), validado: Boolean(validacao?.ok),
    }),
    [draft, capacidades, compilacao, validacao],
  );
  const podeCompilar = prontoParaCompilar(draft, capacidades);

  /** O que ainda impede o próximo ato — inteiro, em linguagem de operador. */
  const faltas = useMemo(() => {
    const lista: string[] = [];
    if (!draft.accountRef) lista.push('Escolha a conta de anúncios.');
    if (!draft.pageRef) lista.push('Escolha a Página que assina os anúncios.');
    if (!draft.campaignName.trim()) lista.push('Dê um nome à campanha.');
    if (!draft.categoryConfirmed) lista.push('Confirme o enquadramento de categoria especial.');
    if (reaisParaMinor(draft.budgetBrl) <= 0) lista.push('Informe um orçamento diário maior que zero.');
    if (!inicioEmIso(draft.startTime)) lista.push('Informe uma data e hora de início válidas.');
    if (!draft.adsetName.trim()) lista.push('Dê um nome ao conjunto.');
    if (estados.mensuracao !== 'pronto') lista.push('Informe uma URL de destino HTTPS válida.');
    if (draft.creativeMode === 'flexible') {
      lista.push('O criativo flexível não emite payload: escolha Individual ou Lote.');
    } else {
      if (emitidas.some((item) => item.midia === 'video') && !capacidades.video) {
        lista.push('Um anúncio usa vídeo, e o criativo de vídeo está bloqueado.');
      }
      emitidas.forEach((item, posicao) => {
        if (!variacaoCompleta(item)) lista.push(`O anúncio ${posicao + 1} está incompleto.`);
      });
    }
    return lista;
  }, [draft, estados, emitidas, capacidades]);

  const compilar = async () => {
    const meu = ++selo.current;
    setOcupado('compilar');
    setAvisos([]);
    try {
      const resultado = await pautadorApi.compilarPlanoMeta(paraPlano(draft));
      if (meu !== selo.current) return;
      setCompilacao(resultado);
      setValidacao(null);
    } catch (exc) {
      if (meu === selo.current) setAvisos(avisosDoErro(exc));
    } finally {
      if (meu === selo.current) setOcupado(null);
    }
  };
  const validar = async () => {
    const meu = ++selo.current;
    setOcupado('validar');
    setAvisos([]);
    try {
      const resultado = await pautadorApi.validarPlanoMeta(paraPlano(draft));
      if (meu !== selo.current) return;
      setValidacao(resultado);
    } catch (exc) {
      if (meu === selo.current) setAvisos(avisosDoErro(exc));
    } finally {
      if (meu === selo.current) setOcupado(null);
    }
  };

  const linhasDoPedido: LinhaDoPedido[] = [
    { rotulo: 'Conta', valor: conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : null, fonte: 'a Meta, agora' },
    { rotulo: 'Página', valor: pagina?.nome ?? null, fonte: 'a Meta, agora' },
    { rotulo: 'Campanha', valor: draft.campaignName || null, fonte: 'você, agora' },
    { rotulo: 'Objetivo', valor: 'Tráfego para site', fonte: 'a receita provada' },
    { rotulo: 'Orçamento diário', valor: reaisParaMinor(draft.budgetBrl) > 0 ? `${formatarBrl(reaisParaMinor(draft.budgetBrl))} · no conjunto` : null, fonte: 'você, agora' },
    { rotulo: 'Compartilhar verba entre conjuntos', valor: draft.budgetSharing ? 'Sim · até 20%' : 'Não', fonte: 'você, agora' },
    { rotulo: 'Advantage+ público', valor: draft.advantageAudience ? 'Aceito' : 'Recusado', fonte: 'você, agora' },
    { rotulo: 'Estrutura', valor: `1 campanha · 1 conjunto · ${emitidas.length} criativo${emitidas.length === 1 ? '' : 's'} · ${emitidas.length} anúncio${emitidas.length === 1 ? '' : 's'}`, fonte: 'o compilador' },
    { rotulo: 'Estado ao nascer', valor: 'Pausada em todos os níveis veiculáveis', fonte: 'a receita provada' },
    { rotulo: 'Plano compilado', valor: compilacao ? `${compilacao.plano.plano_sha256.slice(0, 16)}…` : null, fonte: 'o backend' },
    { rotulo: 'Validação na Meta', valor: validacao?.ok ? `Aceita · ${validacao.operacoes_validadas.length} de ${validacao.operacoes_validadas.length + validacao.operacoes_dependentes_pendentes.length} operações` : null, fonte: 'a Meta' },
  ];

  const proximoAto = validacao?.ok
    ? 'Nada mais nesta bancada: criar de fato é um ato separado, ainda não montado.'
    : compilacao
      ? 'Validar na Meta, sem criar nenhum objeto.'
      : faltas.length > 0 ? null : 'Conferir o plano no backend.';

  const conteudo = (() => {
    switch (etapa) {
      case 'base': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-conta" rotulo="Conta de anúncios" ajuda="Só contas ativas em reais entram nesta receita. O navegador recebe uma referência, nunca o identificador da conta.">
              <select id="meta-conta" className={campo} value={draft.accountRef} disabled={carregando}
                onChange={(e) => mudar('accountRef', e.target.value)}>
                <option value="">Selecione uma conta real</option>
                {contas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado || 'ID protegido'} · {item.moeda || 'moeda não lida'}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo id="meta-pagina" rotulo="Página do Facebook" ajuda="A Página assina os anúncios e precisa estar disponível para promoção nesta conta.">
              <select id="meta-pagina" className={campo} value={draft.pageRef}
                disabled={!draft.accountRef || ocupado === 'ativos'}
                onChange={(e) => mudar('pageRef', e.target.value)}>
                <option value="">Selecione uma Página desta conta</option>
                {paginas.map((item) => (
                  <option key={item.referencia_opaca} value={item.referencia_opaca}>
                    {item.nome} · {item.id_mascarado}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
          <BlocoDeEvidencia titulo="O que foi lido da conta" tom="verificado">
            <LinhaDeFato rotulo="Moeda" valor={conta?.moeda ?? null} fonte="a Meta" ausencia="não lida" />
            <LinhaDeFato rotulo="Fuso da conta" valor={conta?.fuso ?? null} fonte="a Meta" ausencia="não lido" />
            <LinhaDeFato rotulo="Imagens disponíveis" valor={draft.accountRef ? imagens.length : null} fonte="a Meta" ausencia="não lidas" />
            <LinhaDeFato rotulo="Vídeos disponíveis" valor={draft.accountRef ? videos.length : null} fonte="a Meta" ausencia="não lidos" />
          </BlocoDeEvidencia>
        </>
      );
      case 'campanha': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-nome" rotulo="Nome da campanha" largo>
              <Input id="meta-nome" value={draft.campaignName}
                onChange={(e) => mudar('campaignName', e.target.value)} />
            </Campo>
            <Escolha marcado={draft.categoryConfirmed} onChange={(v) => mudar('categoryConfirmed', v)}
              titulo="Confirmo que esta campanha não é de crédito, emprego, moradia nem política">
              Declarar a ausência de categoria especial também é uma declaração. Campanhas dessas
              categorias exigem público, texto e conferência próprios que esta receita ainda não prova.
            </Escolha>
          </div>
          <BlocoDeEvidencia titulo="O que a receita fixa nesta campanha" tom="info">
            <LinhaDeFato rotulo="Objetivo" valor="Tráfego (OUTCOME_TRAFFIC)" fonte="a receita provada" />
            <LinhaDeFato rotulo="Compra" valor="Leilão (AUCTION)" fonte="a receita provada" />
            <LinhaDeFato rotulo="Categoria especial" valor="Nenhuma" fonte="você, agora" />
            <LinhaDeFato rotulo="Estado ao nascer" valor="PAUSED" fonte="a receita provada" />
          </BlocoDeEvidencia>
        </>
      );
      case 'orcamento': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-budget" rotulo="Orçamento diário em reais"
              ajuda={reaisParaMinor(draft.budgetBrl) > 0
                ? `A bancada entendeu ${formatarBrl(reaisParaMinor(draft.budgetBrl))} por dia.`
                : 'Informe um valor maior que zero. Use vírgula ou ponto para os centavos.'}>
              <Input id="meta-budget" inputMode="decimal" value={draft.budgetBrl}
                onChange={(e) => mudar('budgetBrl', e.target.value)} />
            </Campo>
            <Campo id="meta-start" rotulo="Início"
              ajuda={conta?.fuso
                ? `A conta opera em ${conta.fuso}. A bancada envia o instante com fuso explícito.`
                : 'O fuso da conta ainda não foi lido; o instante viaja com fuso explícito mesmo assim.'}>
              <Input id="meta-start" type="datetime-local" value={draft.startTime}
                onChange={(e) => mudar('startTime', e.target.value)} />
            </Campo>
            <Escolha marcado={draft.budgetSharing} onChange={(v) => mudar('budgetSharing', v)}
              titulo="Permitir que a Meta compartilhe verba entre conjuntos desta campanha">
              Desativado, cada conjunto preserva integralmente a própria verba. Ativado, a Meta pode
              mover até 20% do orçamento para outro conjunto elegível da mesma campanha. Esta escolha
              é obrigatória quando a verba fica no conjunto, e não é o mesmo que orçamento
              inteligente de campanha — que esta receita não usa.
            </Escolha>
          </div>
          <BlocoDeEvidencia titulo="Como a verba é aplicada" tom="info">
            <LinhaDeFato rotulo="Onde a verba mora" valor="No conjunto de anúncios" fonte="a receita provada" />
            <LinhaDeFato rotulo="Lance" valor="Maior volume dentro da verba, sem teto de lance" fonte="a receita provada" />
            <LinhaDeFato rotulo="Valor enviado" valor={reaisParaMinor(draft.budgetBrl) > 0 ? `${reaisParaMinor(draft.budgetBrl)} centavos` : null} fonte="o compilador" ausencia="ainda não informado" />
          </BlocoDeEvidencia>
        </>
      );
      case 'conjunto': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-adset-name" rotulo="Nome do conjunto" largo>
              <Input id="meta-adset-name" value={draft.adsetName}
                onChange={(e) => mudar('adsetName', e.target.value)} />
            </Campo>
          </div>
          <BlocoDeEvidencia titulo="Como este conjunto entrega" tom="info">
            <LinhaDeFato rotulo="Meta de desempenho" valor="Visualizações da página de destino" fonte="a receita provada" />
            <LinhaDeFato rotulo="Cobrança" valor="Por impressão" fonte="a receita provada" />
            <LinhaDeFato rotulo="Tipo de destino" valor="Não declarado" fonte="a documentação Meta v26" />
            <LinhaDeFato rotulo="Objeto promovido" valor="Nenhum" fonte="a receita provada" />
          </BlocoDeEvidencia>
          <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            A Meta só aceita mensagem, WhatsApp e ligação como tipo de destino declarado no objetivo
            Tráfego. Tráfego para site é o comportamento padrão do objetivo, então a bancada não
            declara nenhum tipo de destino — declarar um inválido seria recusado na validação.
          </p>
        </>
      );
      case 'publico': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Escolha marcado={draft.advantageAudience} onChange={(v) => mudar('advantageAudience', v)}
              titulo="Aceitar o público Advantage+, deixando a Meta ampliar além do público definido">
              Esta escolha viaja sempre explícita. Se a bancada omitisse o campo, a Meta assumiria
              que você aceitou e ampliaria o público sozinha — por isso não existe estado “não
              declarado” aqui. Recusado, o conjunto entrega dentro do público que você definiu.
            </Escolha>
          </div>
          <BlocoDeEvidencia titulo="O público desta receita" tom="info">
            <LinhaDeFato rotulo="País" valor="Brasil" fonte="a receita provada" />
            <LinhaDeFato rotulo="Idade" valor="18 a 65+" fonte="a receita provada" />
            <LinhaDeFato rotulo="Posicionamentos" valor="Automáticos, sem lista manual" fonte="a receita provada" />
            <LinhaDeFato rotulo="Públicos salvos" valor="Nenhum incluído ou excluído" fonte="a receita provada" />
            <LinhaDeFato rotulo="Advantage+ público" valor={draft.advantageAudience ? 'Aceito (1)' : 'Recusado (0)'} fonte="você, agora" />
          </BlocoDeEvidencia>
        </>
      );
      case 'criativo': return (
        <>
          <div>
            <div className="grid gap-2 rounded-lg border border-border bg-muted p-1 sm:grid-cols-3"
              role="radiogroup" aria-label="Modo de criativo">
              {([
                ['single', 'Individual', 'um anúncio'],
                ['batch', 'Lote controlado', `até ${LIMITE_VARIACOES} anúncios`],
                ['flexible', 'Flexível', 'inspeção do contrato'],
              ] as const).map(([id, nome, detalhe]) => (
                <button key={id} type="button" role="radio" aria-checked={draft.creativeMode === id}
                  onClick={() => mudarModo(id)}
                  className={cn(
                    'min-h-14 rounded-md px-3 py-2 text-left transition-volc duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    draft.creativeMode === id
                      ? 'bg-card text-foreground shadow-card'
                      : 'text-muted-foreground hover:text-foreground',
                  )}>
                  <strong className="block text-sm">{nome}</strong>
                  <span className="block text-sm">{detalhe}</span>
                </button>
              ))}
            </div>
            <p id="meta-limite-lote" className="mt-2 text-sm text-muted-foreground">
              <strong>{emitidas.length} de {LIMITE_VARIACOES}</strong> anúncios serão emitidos.
              Cada linha vira exatamente um criativo e um anúncio; não existe combinação implícita.
              O limite de {LIMITE_VARIACOES} é uma contenção operacional da VOLC, não um limite da Meta.
            </p>
          </div>

          {draft.creativeMode === 'flexible' ? (
            <>
              <PainelDeBloqueio
                titulo="Criativo flexível não emite payload"
                bloqueios={[{
                  codigo: 'META_ASSET_FEED_SPEC_UNPROVEN', severidade: 'alta',
                  titulo: 'Falta uma prova oficial para montar o criativo dinâmico',
                  detalhe: capacidades.flexivelMotivo
                    || 'O servidor não informou a causa do bloqueio.',
                }]}
              />
              <BlocoDeEvidencia titulo="O que já está provado do contrato flexível" tom="verificado">
                <LinhaDeFato rotulo="Formato do anúncio" valor="Obrigatório, um único formato por conjunto de peças" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="URLs de destino" valor="Obrigatórias, até 5" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Chamadas para ação" valor="Obrigatórias neste objetivo, até 5" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Imagens" valor="Obrigatórias no formato de imagem única, até 10" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Textos, títulos e descrições" valor="Opcionais, até 5 cada" fonte="documentação Meta v26" />
                <LinhaDeFato rotulo="Chave interna da Meta e o resto" valor="Ainda sem prova pública" fonte="documentação Meta v26" ausencia="não comprovado" />
              </BlocoDeEvidencia>
            </>
          ) : (
            <div className="space-y-5">
              {!capacidades.video && (
                <PainelDeBloqueio
                  titulo="Anúncio em vídeo não pode ser emitido"
                  bloqueios={[{
                    codigo: 'META_VIDEO_THUMBNAIL_UNPROVEN', severidade: 'alta',
                    titulo: 'A miniatura exigida pelo criativo de vídeo não tem caminho seguro',
                    detalhe: capacidades.videoMotivo
                      || 'O servidor não informou a causa do bloqueio.',
                  }]}
                />
              )}
              {draft.variations.slice(0, draft.creativeMode === 'single' ? 1 : undefined).map((variacao, posicao) => {
                const lista = variacao.midia === 'video' ? videos : imagens;
                const escolhida = variacao.midia === 'video' ? variacao.videoRef : variacao.assetRef;
                const ativo = lista.find((item) => item.referencia_opaca === escolhida);
                return (
                  <section key={variacao.key} className="overflow-hidden rounded-lg border border-border bg-muted/20">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                      <div className="min-w-0">
                        <p className="kicker">Anúncio {posicao + 1}</p>
                        <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
                          {variacao.headline || 'Sem título'}
                        </p>
                        <p className="sr-only" data-testid="variacao-chave">{variacao.key}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <ChipDeEstado
                          glifo={variacaoCompleta(variacao) ? CircleCheck : CircleDot}
                          palavra={variacaoCompleta(variacao) ? 'completo' : 'incompleto'}
                          descricao={variacaoCompleta(variacao)
                            ? 'este anúncio tem peça, textos e chamada para ação'
                            : 'falta preencher pelo menos um campo deste anúncio'}
                          tom={variacaoCompleta(variacao) ? 'bom' : 'atencao'}
                        />
                        {draft.creativeMode === 'batch' && (
                          <>
                            <Button type="button" variant="ghost" size="sm"
                              aria-describedby="meta-limite-lote"
                              disabled={draft.variations.length >= LIMITE_VARIACOES}
                              onClick={() => adicionarVariacao(posicao)}>
                              <Copy className="mr-1.5 h-4 w-4" aria-hidden />Duplicar
                            </Button>
                            <Button type="button" variant="ghost" size="sm"
                              disabled={draft.variations.length === 1}
                              onClick={() => removerVariacao(posicao)}>
                              <Trash2 className="mr-1.5 h-4 w-4" aria-hidden />Remover
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="grid gap-5 p-4 lg:grid-cols-[minmax(190px,30%)_1fr]">
                      <div>
                        <PreviaDaPeca accountRef={draft.accountRef} ativo={ativo} />
                        <p className="mt-2 break-words text-sm font-medium text-foreground">
                          {ativo?.nome || 'Escolha uma peça'}
                        </p>
                        {ativo?.largura && ativo?.altura && (
                          <p className="text-sm text-muted-foreground">{ativo.largura} × {ativo.altura} px</p>
                        )}
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        <Campo id={`meta-midia-${posicao}`} rotulo="Tipo de peça">
                          <select id={`meta-midia-${posicao}`} className={campo} value={variacao.midia}
                            onChange={(e) => mudarVariacao(posicao, 'midia', e.target.value as MidiaDaVariacao)}>
                            <option value="image">Imagem existente</option>
                            <option value="video">
                              Vídeo existente{capacidades.video ? '' : ' · emissão bloqueada'}
                            </option>
                          </select>
                        </Campo>
                        <Campo id={`meta-peca-${posicao}`} rotulo={variacao.midia === 'video' ? 'Vídeo da conta' : 'Imagem da conta'}>
                          <select id={`meta-peca-${posicao}`} className={campo} value={escolhida}
                            disabled={!draft.accountRef || ocupado === 'ativos'}
                            onChange={(e) => mudarVariacao(
                              posicao, variacao.midia === 'video' ? 'videoRef' : 'assetRef', e.target.value)}>
                            <option value="">
                              {lista.length === 0
                                ? `Nenhum ${variacao.midia === 'video' ? 'vídeo' : 'imagem'} nesta conta`
                                : 'Selecione uma peça existente'}
                            </option>
                            {lista.map((item) => (
                              <option key={item.referencia_opaca} value={item.referencia_opaca}>
                                {item.nome}{item.largura && item.altura ? ` · ${item.largura}×${item.altura}` : ''}
                              </option>
                            ))}
                          </select>
                        </Campo>
                        <Campo id={`meta-ad-name-${posicao}`} rotulo="Nome do anúncio">
                          <Input id={`meta-ad-name-${posicao}`} value={variacao.adName}
                            onChange={(e) => mudarVariacao(posicao, 'adName', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-creative-name-${posicao}`} rotulo="Nome do criativo">
                          <Input id={`meta-creative-name-${posicao}`} value={variacao.creativeName}
                            onChange={(e) => mudarVariacao(posicao, 'creativeName', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-primary-${posicao}`} rotulo="Texto principal" largo>
                          <Textarea id={`meta-primary-${posicao}`} rows={3} value={variacao.message}
                            onChange={(e) => mudarVariacao(posicao, 'message', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-headline-${posicao}`} rotulo="Título">
                          <Input id={`meta-headline-${posicao}`} value={variacao.headline}
                            onChange={(e) => mudarVariacao(posicao, 'headline', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-description-${posicao}`} rotulo="Descrição">
                          <Input id={`meta-description-${posicao}`} value={variacao.description}
                            onChange={(e) => mudarVariacao(posicao, 'description', e.target.value)} />
                        </Campo>
                        <Campo id={`meta-cta-${posicao}`} rotulo="Chamada para ação" largo>
                          <select id={`meta-cta-${posicao}`} className={campo} value={variacao.cta}
                            onChange={(e) => mudarVariacao(posicao, 'cta', e.target.value)}>
                            {CTAS.map(([valor, rotulo]) => (
                              <option key={valor} value={valor}>{rotulo}</option>
                            ))}
                          </select>
                        </Campo>
                      </div>
                    </div>
                  </section>
                );
              })}
              {draft.creativeMode === 'batch' && (
                <Button type="button" variant="outline" className="w-full border-dashed"
                  aria-describedby="meta-limite-lote"
                  disabled={draft.variations.length >= LIMITE_VARIACOES}
                  onClick={() => adicionarVariacao()}>
                  <Plus className="mr-2 h-4 w-4" aria-hidden />Adicionar outro anúncio ao lote
                </Button>
              )}
            </div>
          )}
        </>
      );
      case 'mensuracao': return (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Campo id="meta-url" rotulo="URL final HTTPS" largo
              ajuda="Inclua os parâmetros de campanha diretamente nesta URL. A bancada não injeta marcação por conta própria.">
              <Input id="meta-url" type="url" value={draft.destinationUrl}
                onChange={(e) => mudar('destinationUrl', e.target.value)} />
            </Campo>
          </div>
          <BlocoDeEvidencia titulo="O que será medido" tom="info">
            <LinhaDeFato rotulo="Domínio do destino" valor={dominioDoDestino(draft.destinationUrl)} fonte="você, agora" ausencia="URL ainda inválida" />
            <LinhaDeFato rotulo="Otimização" valor="Visualizações da página de destino" fonte="a receita provada" />
            <LinhaDeFato rotulo="Pixel, conjunto de dados ou conversão personalizada" valor="Nenhum" fonte="a receita provada" />
            <LinhaDeFato rotulo="Janela de atribuição" valor="Padrão efetivo da conta" fonte="a Meta" />
            <LinhaDeFato rotulo="Domínio de conversão" valor="Não enviado" fonte="documentação Meta v26" />
          </BlocoDeEvidencia>
          <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            A Meta exige o domínio de conversão quando a campanha compartilha dados com um pixel.
            Esta receita não promove nenhum pixel, então o campo não é enviado. Receitas de venda e
            de cadastro, quando forem provadas, trarão pixel, evento e domínio juntos.
          </p>
        </>
      );
      case 'revisao': return (
        <>
          <BlocoDeEvidencia titulo="O que será enviado à Meta" tom="verificado">
            <LinhaDeFato rotulo="Operações compiladas" valor={compilacao ? compilacao.plano.operacoes.length : null} fonte="o backend" ausencia="plano ainda não compilado" />
            <LinhaDeFato rotulo="Identidade do plano" valor={compilacao?.plano.plano_sha256 ?? null} fonte="o backend" ausencia="plano ainda não compilado" />
            <LinhaDeFato rotulo="Efeito externo da conferência" valor={compilacao ? 'Nenhum' : null} fonte="o backend" ausencia="—" />
          </BlocoDeEvidencia>

          {compilacao && (
            <div className="overflow-x-auto rounded-lg border border-border/70">
              <table className="w-full min-w-[520px] text-sm">
                <caption className="sr-only">Operações que compõem o plano compilado</caption>
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Operação</th>
                    <th scope="col" className="px-3 py-2 font-medium">Objeto</th>
                    <th scope="col" className="px-3 py-2 font-medium">Estado ao nascer</th>
                    <th scope="col" className="px-3 py-2 font-medium">Validável sem criar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {compilacao.plano.operacoes.map((op) => (
                    <tr key={op.nome}>
                      <th scope="row" className="px-3 py-2 text-left font-medium text-foreground">{op.nome}</th>
                      <td className="px-3 py-2 text-muted-foreground">{op.tipo ?? '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{op.status ?? 'não veiculável'}</td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {op.validavel_sem_criar_pai ? 'Sim' : 'Não · depende de um objeto real'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {validacao && (
            <BlocoDeEvidencia titulo="Resultado da validação remota" tom={validacao.ok ? 'verificado' : 'atencao'}>
              <LinhaDeFato rotulo="Cobertura" valor="Parcial · apenas as operações que não dependem de um objeto real" fonte="a Meta" />
              <LinhaDeFato rotulo="Validadas" valor={validacao.operacoes_validadas.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              <LinhaDeFato rotulo="Ainda não validadas" valor={validacao.operacoes_dependentes_pendentes.join(', ') || null} fonte="a Meta" ausencia="nenhuma" />
              <LinhaDeFato rotulo="Objetos criados" valor={String(validacao.objetos_criados)} fonte="a Meta" />
            </BlocoDeEvidencia>
          )}

          <div className="space-y-4">
            <AcaoDominante
              pode={podeCompilar && ocupado === null}
              enviando={ocupado === 'compilar'}
              faltas={faltas}
              onClick={compilar}
            >
              Conferir o plano
            </AcaoDominante>
            <div className="border-t border-border pt-4">
              <AcaoDominante
                pode={Boolean(compilacao) && capacidades.validateOnly && ocupado === null}
                enviando={ocupado === 'validar'}
                faltas={[
                  ...(compilacao ? [] : ['Confira o plano antes de falar com a Meta.']),
                  ...(capacidades.validateOnly ? [] : ['A validação remota está fechada neste servidor; um administrador precisa liberá-la.']),
                ]}
                onClick={validar}
              >
                Validar na Meta, sem criar nada
              </AcaoDominante>
            </div>
          </div>

          <div className="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
            <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
            <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-foreground">
              <strong>Criar de verdade é outro ato, e ele não existe nesta rota.</strong> O compilador
              e o executor pausado já estão prontos e provados, mas o transporte final espera uma
              autorização separada. Nada nesta tela cria, altera ou ativa uma campanha.
            </p>
          </div>
        </>
      );
    }
  })();

  return (
    <Layout>
      <div className="bancada-shell mx-auto max-w-[1480px] px-4 pb-24 pt-4 md:px-6 md:pt-6">
        <section className="bancada-command-deck">
          <div className="bancada-command-topline" aria-hidden />
          <header className="bancada-command-header">
            <div className="min-w-0">
              <Link to="/trafego?rede=meta&aba=preparar" className="bancada-back-link">
                <ArrowLeft className="h-4 w-4" aria-hidden /> Tráfego · Meta Ads
              </Link>
              <div className="mt-5 flex items-center gap-2">
                <span className="bancada-command-icon">
                  <Megaphone className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="kicker text-slate-400">Nascimento controlado · Meta v26</span>
              </div>
              <h1 className="mt-2 max-w-[22ch] font-display text-[2rem] font-bold leading-[1.02] tracking-[-0.035em] text-white text-balance md:text-[2.5rem]">
                Nova campanha Meta
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <div className="bancada-safety-contract">
                <span className="bancada-safety-dot" aria-hidden />
                <div>
                  <p className="font-semibold text-white">Criação segura</p>
                  <p>Tudo que veicula nasce pausado</p>
                </div>
              </div>
              <MetaConfiguracaoLocal />
            </div>
          </header>

          <nav className="bancada-route" aria-label="Etapas da criação Meta">
            <div className="bancada-route-heading">
              <span>Plano de criação</span>
              <span>etapa {indice + 1} de {ETAPAS.length}</span>
            </div>
            <ol className="bancada-route-track">
              {ETAPAS.map((item, posicao) => {
                const estado = estados[item.id];
                const desenho = DESENHO_DO_ESTADO[estado];
                const atual = item.id === etapa;
                return (
                  <li key={item.id} className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => navegar(item.id)}
                      aria-current={atual ? 'step' : undefined}
                      className={cn(
                        'bancada-route-step transition-volc duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                        atual ? 'bancada-route-step-active' : 'bancada-route-step-idle',
                      )}
                    >
                      <span className="bancada-route-index" aria-hidden>
                        {estado === 'pronto' || estado === 'validado'
                          ? <desenho.Glifo className="h-3.5 w-3.5" />
                          : String(posicao + 1).padStart(2, '0')}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">{item.nome}</span>
                        <span className={cn('block truncate text-[0.6875rem]', desenho.tinta)}>
                          {desenho.palavra}
                        </span>
                      </span>
                      <span className="sr-only"> — {desenho.palavra}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </section>

        <div className="bancada-grid mt-6 grid gap-6">
          <main className="bancada-stage min-w-0">
            <header className="bancada-stage-header">
              <div>
                <p className="kicker text-primary">Etapa {indice + 1} de {ETAPAS.length}</p>
                <h2 className="mt-2 max-w-[30ch] font-display text-2xl font-semibold leading-tight tracking-tight text-balance text-foreground md:text-[2rem]">
                  {ETAPAS[indice].pergunta}
                </h2>
              </div>
              <p className="bancada-stage-hint">
                Uma decisão por vez. O contrato técnico fica disponível sem disputar a sua atenção.
              </p>
            </header>

            <div className="space-y-5 p-4 md:p-6">
              <PainelDeBloqueio bloqueios={avisos} titulo="A operação não foi concluída" />
              {conteudo}
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
                <Button type="button" variant="outline" disabled={indice === 0}
                  onClick={() => navegar(ETAPAS[indice - 1].id)}>
                  <ArrowLeft className="mr-2 h-4 w-4" aria-hidden /> Voltar
                </Button>
                {indice < ETAPAS.length - 1 && (
                  <Button type="button" variant="outline"
                    onClick={() => navegar(ETAPAS[indice + 1].id)}>
                    Continuar <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                  </Button>
                )}
              </div>
            </div>
          </main>

          <aside className="min-w-0">
            <Pedido
              linhas={linhasDoPedido}
              faltas={faltas}
              proximoAto={proximoAto}
              lidoEm={null}
            />
          </aside>
        </div>
      </div>
    </Layout>
  );
};

export default MetaCriacaoPage;
