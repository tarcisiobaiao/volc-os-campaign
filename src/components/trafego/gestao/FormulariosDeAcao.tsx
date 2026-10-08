/**
 * Um formulário por grupo de ação. Cada um só COLETA e chama a montagem pura
 * (`lib/trafego/gestao/acoes.ts`); o que é válido é decidido lá, com o mesmo
 * critério do contrato. Nada sai daqui para a rede: o formulário entrega a
 * ação montada para a confirmação (antes → depois), que é quem propõe.
 */
import React from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DIAS,
  DISPOSITIVOS,
  ROTULO_DA_ESTRATEGIA,
  ROTULO_DO_PLACEMENT,
  alvoDaEstrategia,
  errosDe,
  estrategiasPermitidas,
  montarAgenda,
  montarAlvo,
  montarEstrategia,
  montarIp,
  montarNegativas,
  montarOrcamento,
  montarPlacements,
  montarStatus,
  semAlvoPorque,
  type ContextoDaCampanha,
  type Erros,
  type FormAgenda,
  type FormEstrategia,
  type FormNegativas,
  type JanelaDoFormulario,
  type Montagem,
  type SubtipoDeAgenda,
  type SubtipoDeNegativa,
} from '@/lib/trafego/gestao/acoes';
import type {
  AcaoDeGestao,
  Correspondencia,
  EscopoDeExclusao,
  EscopoDeNegativa,
  EstrategiaEscrevivel,
  NivelDeStatus,
  StatusGerivel,
  TipoDeLista,
  TipoDePlacement,
} from '@/types/gestao';

import { Campo, Seletor, classeDeEntrada } from './partes';

export interface PropsDoFormulario {
  contexto: ContextoDaCampanha;
  aoRevisar: (acao: AcaoDeGestao) => void;
  /** Valor inicial vindo da caixa de propostas do diagnóstico. */
  statusInicial?: StatusGerivel;
}

function useMontagem() {
  const [erros, setErros] = React.useState<Erros>({});
  const tentar = (m: Montagem, aoRevisar: (a: AcaoDeGestao) => void) => {
    const e = errosDe(m);
    if (e) {
      setErros(e);
    } else if (m.ok) {
      setErros({});
      aoRevisar(m.acao);
    }
  };
  return { erros, tentar };
}

const Revisar: React.FC = () => (
  <Button type="submit" size="sm" className="mt-3">
    Revisar antes de propor
  </Button>
);

const ErroGeral: React.FC<{ erros: Erros }> = ({ erros }) =>
  erros.campaign_id ? (
    <p className="mt-2 text-[11px] text-destructive" role="alert">
      {erros.campaign_id}
    </p>
  ) : null;

// ── 1 · status ──────────────────────────────────────────────────────────────

const NIVEIS: ReadonlyArray<{ valor: NivelDeStatus; rotulo: string }> = [
  { valor: 'campanha', rotulo: 'campanha' },
  { valor: 'grupo', rotulo: 'grupo de anúncios' },
  { valor: 'anuncio', rotulo: 'anúncio' },
  { valor: 'asset_group', rotulo: 'grupo de recursos (PMax)' },
];

export const FormularioStatus: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar, statusInicial }) => {
  const [nivel, setNivel] = React.useState<NivelDeStatus>('campanha');
  const [ident, setIdent] = React.useState(contexto.campaignId);
  const [status, setStatus] = React.useState<StatusGerivel | ''>(statusInicial ?? '');
  const { erros, tentar } = useMontagem();
  return (
    <form
      aria-label="status"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarStatus({ nivel, ident, status }), aoRevisar);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Campo id="g-status-nivel" rotulo="nível">
          <Seletor
            id="g-status-nivel"
            valor={nivel}
            opcoes={NIVEIS}
            aoMudar={(v) => {
              setNivel(v);
              setIdent(v === 'campanha' ? contexto.campaignId : '');
            }}
          />
        </Campo>
        <Campo
          id="g-status-ident"
          rotulo="id no Google"
          ajuda={nivel === 'anuncio' ? '<id do grupo>~<id do anúncio>' : undefined}
          erro={erros.ident}
        >
          <input
            id="g-status-ident"
            className={classeDeEntrada}
            value={ident}
            onChange={(e) => setIdent(e.target.value)}
            inputMode={nivel === 'anuncio' ? 'text' : 'numeric'}
          />
        </Campo>
        <Campo id="g-status-novo" rotulo="novo status" erro={erros.status}>
          <Seletor<StatusGerivel>
            id="g-status-novo"
            valor={status}
            opcoes={[
              { valor: 'ENABLED', rotulo: 'ativar' },
              { valor: 'PAUSED', rotulo: 'pausar' },
            ]}
            aoMudar={setStatus}
          />
        </Campo>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Remover não é gestão: tem fluxo próprio e não volta.
      </p>
      <Revisar />
    </form>
  );
};

// ── 2 · orçamento ───────────────────────────────────────────────────────────

export const FormularioOrcamento: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [valor, setValor] = React.useState('');
  const [budgetId, setBudgetId] = React.useState('');
  const [ciente, setCiente] = React.useState(false);
  const { erros, tentar } = useMontagem();
  return (
    <form
      aria-label="orçamento diário"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarOrcamento({ valor, budgetId, compartilhadoCiente: ciente }, contexto), aoRevisar);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo id="g-orc-valor" rotulo="nova verba diária" ajuda="em moeda da conta, até 2 casas (ex.: 33,50)" erro={erros.valor}>
          <input
            id="g-orc-valor"
            className={classeDeEntrada}
            value={valor}
            inputMode="decimal"
            onChange={(e) => setValor(e.target.value)}
          />
        </Campo>
        <Campo
          id="g-orc-budget"
          rotulo="id do orçamento (opcional)"
          ajuda="vazio = o orçamento que a campanha usa hoje, lido na conta"
          erro={erros.budgetId}
        >
          <input
            id="g-orc-budget"
            className={classeDeEntrada}
            value={budgetId}
            inputMode="numeric"
            onChange={(e) => setBudgetId(e.target.value)}
          />
        </Campo>
      </div>
      <label className="mt-3 flex items-start gap-2 text-[12px]">
        <input type="checkbox" checked={ciente} onChange={(e) => setCiente(e.target.checked)} className="mt-0.5" />
        <span>
          Sei que, se o orçamento for compartilhado, a verba muda para todas as campanhas que o usam.
        </span>
      </label>
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};

// ── 3 · alvo de lance ───────────────────────────────────────────────────────

export const FormularioAlvo: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [valor, setValor] = React.useState('');
  const { erros, tentar } = useMontagem();
  const alvo = alvoDaEstrategia(contexto.estrategia);
  if (!alvo) {
    return (
      <p className="text-[12px] leading-relaxed text-muted-foreground" role="note">
        {semAlvoPorque(contexto.estrategia)}
      </p>
    );
  }
  return (
    <form
      aria-label="alvo de lance"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarAlvo({ valor }, contexto), aoRevisar);
      }}
    >
      <p className="text-[12px] text-muted-foreground">
        Estratégia lida: {ROTULO_DA_ESTRATEGIA[contexto.estrategia as string] ?? contexto.estrategia}. O campo
        ajustável é o {alvo.rotulo}. Ajustar o alvo não troca a estratégia.
      </p>
      <Campo
        id="g-alvo-valor"
        className="mt-3 max-w-xs"
        rotulo={`novo ${alvo.rotulo}`}
        ajuda={
          alvo.unidade === 'percentual'
            ? `em % (450 = 450%)${alvo.aceitaZero ? '; 0 remove o alvo' : ''}`
            : `em moeda da conta${alvo.aceitaZero ? '; 0 remove o alvo' : ''}`
        }
        erro={erros.valor}
      >
        <input
          id="g-alvo-valor"
          className={classeDeEntrada}
          value={valor}
          inputMode="decimal"
          onChange={(e) => setValor(e.target.value)}
        />
      </Campo>
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};

// ── 4 · troca de estratégia ─────────────────────────────────────────────────

export const FormularioEstrategia: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [f, setF] = React.useState<FormEstrategia>({ nova: '', tcpa: '', troas: '', tetoCpc: '', portfolio: '' });
  const { erros, tentar } = useMontagem();
  const opcoes = estrategiasPermitidas(contexto.canal).map((v) => ({ valor: v, rotulo: ROTULO_DA_ESTRATEGIA[v] ?? v }));
  return (
    <form
      aria-label="troca de estratégia"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarEstrategia(f, contexto), aoRevisar);
      }}
    >
      <p className="text-[12px] leading-relaxed text-muted-foreground" role="note">
        Trocar a estratégia reinicia o aprendizado do lance automático: espere dias de entrega instável.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Campo id="g-est-nova" rotulo="nova estratégia" erro={erros.nova}>
          <Seletor<EstrategiaEscrevivel>
            id="g-est-nova"
            valor={f.nova}
            opcoes={opcoes}
            aoMudar={(v) => setF({ ...f, nova: v })}
          />
        </Campo>
        {f.nova === 'MAXIMIZE_CONVERSIONS' && (
          <Campo id="g-est-tcpa" rotulo="CPA desejado (opcional)" erro={erros.tcpa}>
            <input id="g-est-tcpa" className={classeDeEntrada} value={f.tcpa} onChange={(e) => setF({ ...f, tcpa: e.target.value })} />
          </Campo>
        )}
        {f.nova === 'MAXIMIZE_CONVERSION_VALUE' && (
          <Campo id="g-est-troas" rotulo="ROAS desejado em % (opcional)" erro={erros.troas}>
            <input id="g-est-troas" className={classeDeEntrada} value={f.troas} onChange={(e) => setF({ ...f, troas: e.target.value })} />
          </Campo>
        )}
        {f.nova === 'TARGET_SPEND' && (
          <Campo id="g-est-teto" rotulo="teto de CPC (opcional)" erro={erros.tetoCpc}>
            <input id="g-est-teto" className={classeDeEntrada} value={f.tetoCpc} onChange={(e) => setF({ ...f, tetoCpc: e.target.value })} />
          </Campo>
        )}
        {f.nova === 'PORTFOLIO' && (
          <Campo id="g-est-port" rotulo="estratégia de portfólio" ajuda="customers/<conta>/biddingStrategies/<id>" erro={erros.portfolio}>
            <input id="g-est-port" className={classeDeEntrada} value={f.portfolio} onChange={(e) => setF({ ...f, portfolio: e.target.value })} />
          </Campo>
        )}
      </div>
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};

// ── 5 · negativas e listas ──────────────────────────────────────────────────

const SUBTIPOS_NEGATIVA: ReadonlyArray<{ valor: SubtipoDeNegativa; rotulo: string }> = [
  { valor: 'negativa.keyword', rotulo: 'negativas na campanha ou grupo' },
  { valor: 'lista.criar', rotulo: 'nova lista compartilhada' },
  { valor: 'lista.adicionar', rotulo: 'itens numa lista existente' },
  { valor: 'lista.anexar', rotulo: 'anexar lista a campanhas' },
];

const CORRESPONDENCIAS: ReadonlyArray<{ valor: Correspondencia; rotulo: string }> = [
  { valor: 'PHRASE', rotulo: 'frase' },
  { valor: 'EXACT', rotulo: 'exata' },
  { valor: 'BROAD', rotulo: 'ampla' },
];

const TIPOS_PLACEMENT: ReadonlyArray<{ valor: TipoDePlacement; rotulo: string }> = (
  Object.keys(ROTULO_DO_PLACEMENT) as TipoDePlacement[]
).map((v) => ({ valor: v, rotulo: ROTULO_DO_PLACEMENT[v] }));

export const FormularioNegativas: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [f, setF] = React.useState<FormNegativas>({
    subtipo: 'negativa.keyword',
    escopo: 'campanha',
    alvo: contexto.campaignId,
    termos: '',
    correspondencia: 'PHRASE',
    tipoLista: 'NEGATIVE_KEYWORDS',
    nome: '',
    tipoPlacement: 'site',
    placements: '',
    sharedSetId: '',
    campanhas: contexto.campaignId,
  });
  const { erros, tentar } = useMontagem();
  const set = (parcial: Partial<FormNegativas>) => setF({ ...f, ...parcial });
  const comItens = f.subtipo === 'lista.criar' || f.subtipo === 'lista.adicionar';
  const ehKeyword = f.subtipo === 'negativa.keyword' || (comItens && f.tipoLista === 'NEGATIVE_KEYWORDS');

  return (
    <form
      aria-label="negativas e listas"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarNegativas(f), aoRevisar);
      }}
    >
      <Campo id="g-neg-sub" rotulo="o que fazer" className="max-w-sm">
        <Seletor id="g-neg-sub" valor={f.subtipo} opcoes={SUBTIPOS_NEGATIVA} aoMudar={(v) => set({ subtipo: v })} />
      </Campo>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {f.subtipo === 'negativa.keyword' && (
          <>
            <Campo id="g-neg-escopo" rotulo="onde">
              <Seletor<EscopoDeNegativa>
                id="g-neg-escopo"
                valor={f.escopo}
                opcoes={[
                  { valor: 'campanha', rotulo: 'campanha' },
                  { valor: 'grupo', rotulo: 'grupo de anúncios' },
                ]}
                aoMudar={(v) => set({ escopo: v, alvo: v === 'campanha' ? contexto.campaignId : '' })}
              />
            </Campo>
            <Campo id="g-neg-alvo" rotulo={f.escopo === 'grupo' ? 'id do grupo' : 'id da campanha'} erro={erros.alvo}>
              <input id="g-neg-alvo" className={classeDeEntrada} value={f.alvo} onChange={(e) => set({ alvo: e.target.value })} />
            </Campo>
          </>
        )}
        {f.subtipo === 'lista.criar' && (
          <Campo id="g-neg-nome" rotulo="nome da lista" erro={erros.nome}>
            <input id="g-neg-nome" className={classeDeEntrada} value={f.nome} onChange={(e) => set({ nome: e.target.value })} />
          </Campo>
        )}
        {(f.subtipo === 'lista.adicionar' || f.subtipo === 'lista.anexar') && (
          <Campo id="g-neg-lista" rotulo="id da lista compartilhada" erro={erros.sharedSetId}>
            <input id="g-neg-lista" className={classeDeEntrada} value={f.sharedSetId} onChange={(e) => set({ sharedSetId: e.target.value })} />
          </Campo>
        )}
        {comItens && (
          <Campo id="g-neg-tipolista" rotulo="tipo de lista">
            <Seletor<TipoDeLista>
              id="g-neg-tipolista"
              valor={f.tipoLista}
              opcoes={[
                { valor: 'NEGATIVE_KEYWORDS', rotulo: 'palavras-chave negativas' },
                { valor: 'NEGATIVE_PLACEMENTS', rotulo: 'placements excluídos' },
              ]}
              aoMudar={(v) => set({ tipoLista: v })}
            />
          </Campo>
        )}
      </div>
      {ehKeyword && f.subtipo !== 'lista.anexar' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
          <Campo
            id="g-neg-termos"
            rotulo="negativas, uma por linha"
            ajuda='"frase" e [exata] valem; sem marca, vale a correspondência ao lado. Até 80 caracteres e 10 palavras.'
            erro={erros.termos ?? erros.itens}
          >
            <textarea id="g-neg-termos" rows={4} className={classeDeEntrada} value={f.termos} onChange={(e) => set({ termos: e.target.value })} />
          </Campo>
          <Campo id="g-neg-corr" rotulo="correspondência padrão">
            <Seletor<Correspondencia> id="g-neg-corr" valor={f.correspondencia} opcoes={CORRESPONDENCIAS} aoMudar={(v) => set({ correspondencia: v })} />
          </Campo>
        </div>
      )}
      {comItens && f.tipoLista === 'NEGATIVE_PLACEMENTS' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
          <Campo id="g-neg-plac" rotulo="placements, um por linha" erro={erros.itens}>
            <textarea id="g-neg-plac" rows={4} className={classeDeEntrada} value={f.placements} onChange={(e) => set({ placements: e.target.value })} />
          </Campo>
          <Campo id="g-neg-tipoplac" rotulo="tipo">
            <Seletor<TipoDePlacement> id="g-neg-tipoplac" valor={f.tipoPlacement} opcoes={TIPOS_PLACEMENT} aoMudar={(v) => set({ tipoPlacement: v })} />
          </Campo>
        </div>
      )}
      {(f.subtipo === 'lista.criar' || f.subtipo === 'lista.anexar') && (
        <Campo
          id="g-neg-camp"
          className="mt-3"
          rotulo={f.subtipo === 'lista.criar' ? 'anexar às campanhas (opcional)' : 'campanhas'}
          ajuda="ids do Google separados por vírgula"
          erro={erros.campanhas}
        >
          <input id="g-neg-camp" className={classeDeEntrada} value={f.campanhas} onChange={(e) => set({ campanhas: e.target.value })} />
        </Campo>
      )}
      <Revisar />
    </form>
  );
};

// ── 6 · exclusão de placement ───────────────────────────────────────────────

const ESCOPOS_EXCLUSAO: ReadonlyArray<{ valor: EscopoDeExclusao; rotulo: string }> = [
  { valor: 'campanha', rotulo: 'só esta campanha' },
  { valor: 'conta', rotulo: 'a conta inteira' },
];

export const FormularioPlacements: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [escopo, setEscopo] = React.useState<EscopoDeExclusao>('campanha');
  const [tipo, setTipo] = React.useState<TipoDePlacement>('site');
  const [valores, setValores] = React.useState('');
  const { erros, tentar } = useMontagem();
  return (
    <form
      aria-label="exclusão de placement"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarPlacements({ escopo, tipo, valores }, contexto), aoRevisar);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo id="g-plac-escopo" rotulo="onde excluir">
          <Seletor<EscopoDeExclusao> id="g-plac-escopo" valor={escopo} opcoes={ESCOPOS_EXCLUSAO} aoMudar={setEscopo} />
        </Campo>
        <Campo id="g-plac-tipo" rotulo="tipo">
          <Seletor<TipoDePlacement> id="g-plac-tipo" valor={tipo} opcoes={TIPOS_PLACEMENT} aoMudar={setTipo} />
        </Campo>
      </div>
      <Campo id="g-plac-valores" className="mt-3" rotulo="placements, um por linha" ajuda="site sem https:// (exemplo.com.br)" erro={erros.valores}>
        <textarea id="g-plac-valores" rows={4} className={classeDeEntrada} value={valores} onChange={(e) => setValores(e.target.value)} />
      </Campo>
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};

// ── 7 · exclusão de IP ──────────────────────────────────────────────────────

export const FormularioIp: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [escopo, setEscopo] = React.useState<EscopoDeExclusao>('campanha');
  const [ips, setIps] = React.useState('');
  const { erros, tentar } = useMontagem();
  return (
    <form
      aria-label="exclusão de IP"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarIp({ escopo, ips }, contexto), aoRevisar);
      }}
    >
      <Campo id="g-ip-escopo" rotulo="onde excluir" className="max-w-sm">
        <Seletor<EscopoDeExclusao> id="g-ip-escopo" valor={escopo} opcoes={ESCOPOS_EXCLUSAO} aoMudar={setEscopo} />
      </Campo>
      <Campo
        id="g-ip-lista"
        className="mt-3"
        rotulo="IPs, um por linha"
        ajuda="endereço único ou faixa IPv4 de /24 a /32 (203.0.113.0/24); até 500"
        erro={erros.ips}
      >
        <textarea id="g-ip-lista" rows={4} className={classeDeEntrada} value={ips} onChange={(e) => setIps(e.target.value)} />
      </Campo>
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};

// ── 8 · agenda e ajustes ────────────────────────────────────────────────────

const SUBTIPOS_AGENDA: ReadonlyArray<{ valor: SubtipoDeAgenda; rotulo: string }> = [
  { valor: 'programacao.anuncios', rotulo: 'programação de anúncios' },
  { valor: 'ajuste.dispositivo', rotulo: 'ajuste por dispositivo' },
  { valor: 'ajuste.horario', rotulo: 'ajuste de uma janela existente' },
];

const janelaVazia = (): JanelaDoFormulario => ({ dia: 'MONDAY', inicio: '08:00', fim: '18:00', ajuste: '' });

export const FormularioAgenda: React.FC<PropsDoFormulario> = ({ contexto, aoRevisar }) => {
  const [f, setF] = React.useState<FormAgenda>({
    subtipo: 'programacao.anuncios',
    janelas: [janelaVazia()],
    remover: '',
    substituir: false,
    dispositivo: 'MOBILE',
    ajuste: '',
    criterionId: '',
  });
  const { erros, tentar } = useMontagem();
  const set = (p: Partial<FormAgenda>) => setF({ ...f, ...p });
  const mudarJanela = (i: number, p: Partial<JanelaDoFormulario>) =>
    set({ janelas: f.janelas.map((j, k) => (k === i ? { ...j, ...p } : j)) });

  return (
    <form
      aria-label="agenda e ajustes"
      onSubmit={(e) => {
        e.preventDefault();
        tentar(montarAgenda(f, contexto), aoRevisar);
      }}
    >
      <Campo id="g-ag-sub" rotulo="o que fazer" className="max-w-sm">
        <Seletor id="g-ag-sub" valor={f.subtipo} opcoes={SUBTIPOS_AGENDA} aoMudar={(v) => set({ subtipo: v })} />
      </Campo>

      {f.subtipo === 'programacao.anuncios' && (
        <fieldset className="mt-3">
          <legend className="text-[12px] font-medium">janelas novas (grade de 15 min)</legend>
          <ul className="mt-1 space-y-2">
            {f.janelas.map((j, i) => (
              <li key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[8rem_6rem_6rem_7rem_auto]">
                <select
                  aria-label={`dia da janela ${i + 1}`}
                  className={classeDeEntrada}
                  value={j.dia}
                  onChange={(e) => mudarJanela(i, { dia: e.target.value as JanelaDoFormulario['dia'] })}
                >
                  {DIAS.map((d) => (
                    <option key={d.dia} value={d.dia}>
                      {d.rotulo}
                    </option>
                  ))}
                </select>
                <input aria-label={`início da janela ${i + 1}`} className={classeDeEntrada} value={j.inicio} onChange={(e) => mudarJanela(i, { inicio: e.target.value })} />
                <input aria-label={`fim da janela ${i + 1}`} className={classeDeEntrada} value={j.fim} onChange={(e) => mudarJanela(i, { fim: e.target.value })} />
                <input
                  aria-label={`ajuste da janela ${i + 1} em %`}
                  placeholder="ajuste %"
                  className={classeDeEntrada}
                  value={j.ajuste}
                  onChange={(e) => mudarJanela(i, { ajuste: e.target.value })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`tirar a janela ${i + 1}`}
                  onClick={() => set({ janelas: f.janelas.filter((_, k) => k !== i) })}
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
          <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => set({ janelas: [...f.janelas, janelaVazia()] })}>
            <Plus aria-hidden /> mais uma janela
          </Button>
          {erros.janelas && (
            <p className="mt-1 text-[11px] text-destructive" role="alert">
              {erros.janelas}
            </p>
          )}
          <label className="mt-3 flex items-start gap-2 text-[12px]">
            <input type="checkbox" className="mt-0.5" checked={f.substituir} onChange={(e) => set({ substituir: e.target.checked })} />
            <span>Substituir: remove todas as janelas atuais e deixa só as de cima.</span>
          </label>
          {!f.substituir && (
            <Campo id="g-ag-remover" className="mt-3" rotulo="remover janelas existentes (opcional)" ajuda="ids de critério, separados por vírgula" erro={erros.remover}>
              <input id="g-ag-remover" className={classeDeEntrada} value={f.remover} onChange={(e) => set({ remover: e.target.value })} />
            </Campo>
          )}
        </fieldset>
      )}

      {f.subtipo === 'ajuste.dispositivo' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Campo id="g-ag-disp" rotulo="dispositivo">
            <Seletor
              id="g-ag-disp"
              valor={f.dispositivo}
              opcoes={DISPOSITIVOS.map((d) => ({ valor: d.dispositivo, rotulo: d.rotulo }))}
              aoMudar={(v) => set({ dispositivo: v })}
            />
          </Campo>
          <Campo id="g-ag-ajuste" rotulo="ajuste em %" ajuda="−90 a +900; −100 para não exibir" erro={erros.ajuste}>
            <input id="g-ag-ajuste" className={classeDeEntrada} value={f.ajuste} onChange={(e) => set({ ajuste: e.target.value })} />
          </Campo>
        </div>
      )}

      {f.subtipo === 'ajuste.horario' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Campo id="g-ag-crit" rotulo="id da janela (critério)" erro={erros.criterionId}>
            <input id="g-ag-crit" className={classeDeEntrada} value={f.criterionId} onChange={(e) => set({ criterionId: e.target.value })} />
          </Campo>
          <Campo id="g-ag-ajuste-h" rotulo="ajuste em %" ajuda="−90 a +900" erro={erros.ajuste}>
            <input id="g-ag-ajuste-h" className={classeDeEntrada} value={f.ajuste} onChange={(e) => set({ ajuste: e.target.value })} />
          </Campo>
        </div>
      )}
      <ErroGeral erros={erros} />
      <Revisar />
    </form>
  );
};
