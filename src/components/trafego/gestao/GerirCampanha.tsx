/**
 * "Gerir campanha" — propor, decidir, aplicar, verificar e reverter mudanças
 * numa campanha Google Ads no ar (contrato GADS-GESTAO v1).
 *
 * Ciclo: propor → aprovar (admin) → aplicar (admin, com a escrita aberta) →
 * verificar → (reverter). Nada é escrito no Google sem uma aprovação humana
 * gravada; esta tela não tem atalho para isso.
 *
 * Cada grupo de ação tem um formulário validado com o critério do contrato e
 * uma confirmação que mostra o antes → depois. A proposta nasce no servidor,
 * que relê o "antes" na conta — é o diff gravado, e não o da confirmação, que
 * a fila mostra e que vai para a aprovação.
 */
import React from 'react';
import { Info } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useCapacidades } from '@/hooks/useCapacidades';
import {
  useImportarCampanha,
  usePropor,
  usePropostasDaConta,
} from '@/hooks/useGestaoDeCampanha';
import {
  GRUPOS,
  ROTULO_DO_TIPO,
  TIPOS_MONETARIOS,
  VALIDADE_PADRAO_HORAS,
  validarMotivo,
  validarValidade,
  type ContextoDaCampanha,
} from '@/lib/trafego/gestao/acoes';
import { previaDaAcao, type LeituraDaCampanha } from '@/lib/trafego/gestao/diff';
import { codigoDoErro, erroLegivel } from '@/lib/trafego/gestao/erros';
import { ESTADO_LEGIVEL, daCampanha, permissoesDe, type Preenchimento } from '@/lib/trafego/gestao/fila';
import type { AcaoDeGestao, GrupoDeAcao } from '@/types/gestao';

import { FilaDePropostas } from './FilaDePropostas';
import {
  FormularioAgenda,
  FormularioAlvo,
  FormularioEstrategia,
  FormularioIp,
  FormularioNegativas,
  FormularioOrcamento,
  FormularioPlacements,
  FormularioStatus,
  type PropsDoFormulario,
} from './FormulariosDeAcao';
import { RecomendacoesDoGoogle } from './RecomendacoesDoGoogle';
import { AntesDepois, AvisoDeErro, classeDeEntrada } from './partes';

export interface GerirCampanhaProps {
  /** Conta Google Ads. `null` = a página não sabe em que conta a campanha vive. */
  customerId: string | null;
  /** Id externo (Google) da campanha. */
  campaignId: string;
  volcCampaignId: string;
  leitura: LeituraDaCampanha;
  canal: string | null;
  /** Procedência do inventário: `desconhecida`/`legado` sugerem importar. */
  procedencia: string | null;
  /** Vindo da caixa de propostas do diagnóstico; `nonce` reabre o mesmo grupo. */
  preenchimento?: (Preenchimento & { nonce: number }) | null;
}

const FORMULARIO: Partial<Record<GrupoDeAcao, React.FC<PropsDoFormulario>>> = {
  status: FormularioStatus,
  orcamento: FormularioOrcamento,
  alvo_de_lance: FormularioAlvo,
  estrategia: FormularioEstrategia,
  negativas_e_listas: FormularioNegativas,
  placements: FormularioPlacements,
  ip: FormularioIp,
  agenda_e_ajustes: FormularioAgenda,
};

const PROCEDENCIA_SEM_IDENTIDADE = new Set(['desconhecida', 'legado']);

export const GerirCampanha: React.FC<GerirCampanhaProps> = ({
  customerId,
  campaignId,
  volcCampaignId,
  leitura,
  canal,
  procedencia,
  preenchimento,
}) => {
  const { capacidades } = useCapacidades();
  const permissoes = permissoesDe(capacidades);

  const [grupo, setGrupo] = React.useState<GrupoDeAcao>('status');
  const [emRevisao, setEmRevisao] = React.useState<AcaoDeGestao | null>(null);
  const [motivo, setMotivo] = React.useState('');
  const [validade, setValidade] = React.useState('');
  const [errosDoEnvio, setErrosDoEnvio] = React.useState<{ motivo?: string; validade?: string }>({});
  const [todaAConta, setTodaAConta] = React.useState(false);
  const [versaoDoForm, setVersaoDoForm] = React.useState(0);
  const raiz = React.useRef<HTMLElement>(null);

  const propor = usePropor(customerId);
  const importar = useImportarCampanha(customerId);
  const fila = usePropostasDaConta(customerId);

  const contexto: ContextoDaCampanha = {
    customerId: customerId ?? '',
    campaignId,
    estrategia: leitura.estrategia,
    canal,
  };

  // A caixa do diagnóstico pediu: abre o grupo, traz o motivo e rola até aqui.
  React.useEffect(() => {
    if (!preenchimento) return;
    setGrupo(preenchimento.grupo);
    setMotivo(preenchimento.motivo);
    setEmRevisao(null);
    setVersaoDoForm((v) => v + 1);
    const el = raiz.current;
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [preenchimento]);

  const pedeImportar =
    (procedencia != null && PROCEDENCIA_SEM_IDENTIDADE.has(procedencia)) ||
    codigoDoErro(propor.error) === 'campanha_nao_importada';

  const enviar = () => {
    if (!emRevisao || !customerId) return;
    const eMotivo = validarMotivo(motivo);
    const eValidade = validarValidade(validade);
    if (eMotivo || eValidade) {
      setErrosDoEnvio({ motivo: eMotivo ?? undefined, validade: eValidade ?? undefined });
      return;
    }
    setErrosDoEnvio({});
    propor.mutate(
      {
        customer_id: customerId,
        acao: emRevisao,
        motivo: motivo.trim(),
        ...(validade.trim() ? { validade_horas: Number(validade) } : {}),
      },
      {
        onSuccess: () => {
          setEmRevisao(null);
          setMotivo('');
          setValidade('');
          setVersaoDoForm((v) => v + 1);
        },
      },
    );
  };

  const propostas = (fila.data?.propostas ?? []).filter(
    (p) => todaAConta || daCampanha(p, { volcCampaignId, campaignId, customerId: customerId ?? '' }),
  );

  if (!customerId) {
    return (
      <p className="text-[13px] leading-relaxed text-muted-foreground" role="status">
        A conta desta campanha ainda não foi identificada. Sem ela não há como propor nem aplicar
        mudança — a gestão confere a conta antes de qualquer leitura.
      </p>
    );
  }

  const Formulario = FORMULARIO[grupo];
  const rotuloDoGrupo = GRUPOS.find((g) => g.grupo === grupo)?.rotulo ?? grupo;
  const tiposDoGrupo = GRUPOS.find((g) => g.grupo === grupo)?.tipos ?? [];
  const monetario = tiposDoGrupo.some((t) => TIPOS_MONETARIOS.has(t));

  return (
    <section ref={raiz} aria-label="gerir campanha" className="scroll-mt-6">
      <p className="max-w-[72ch] text-[12px] leading-relaxed text-muted-foreground">
        Toda mudança nasce como proposta, é aprovada por um administrador e só então é aplicada no
        Google. {permissoes.decidir ? 'Você pode aprovar e recusar.' : 'Aprovar e aplicar são de administrador.'}
      </p>

      {pedeImportar && (
        <div className="mt-3 rounded-md border border-border px-3 py-2.5" role="note" aria-label="importar campanha">
          <p className="text-[12px] font-medium">Esta campanha não nasceu pelo VOLC.</p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Para gerir, ela precisa de identidade na gestão (procedência “descoberta”, declarada por você).
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="mt-2"
            disabled={importar.isPending}
            onClick={() => importar.mutate({ customer_id: customerId, campaign_id: campaignId })}
          >
            Importar campanha para a gestão
          </Button>
          {importar.data && (
            <p className="mt-2 text-[12px]" role="status">
              {importar.data.ja_existia
                ? importar.data.procedencia_resolvida
                  ? 'Identidade já existia; a procedência foi declarada agora.'
                  : 'A campanha já tinha identidade na gestão.'
                : 'Campanha importada. Pode propor.'}{' '}
              ({importar.data.google.nome} · {importar.data.google.status})
            </p>
          )}
          {importar.error && <AvisoDeErro className="mt-2" erro={erroLegivel(importar.error)} />}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-1.5" role="group" aria-label="grupos de ação">
        {GRUPOS.map((g) => (
          <button
            key={g.grupo}
            type="button"
            aria-pressed={grupo === g.grupo}
            onClick={() => {
              setGrupo(g.grupo);
              setEmRevisao(null);
            }}
            className={cn(
              'min-h-9 rounded-md border px-2.5 text-[12px] transition-colors duration-150',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              grupo === g.grupo ? 'border-primary bg-primary/10 font-semibold' : 'border-border hover:bg-muted/50',
            )}
          >
            {g.rotulo}
          </button>
        ))}
      </div>

      <div className="mt-4 rounded-md border border-border px-3 py-3">
        <p className="text-[13px] font-semibold">{rotuloDoGrupo}</p>
        {!monetario && (
          <p className="mt-1 flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground" role="note">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Ação sem tamanho numérico: só nasce se a regra vigente a listar entre as operações sem delta
            e o pedido couber no teto dela. Se não listar, a resposta é “Este tipo de ação ainda não é
            aceito pelo ledger”.
          </p>
        )}

        <div className="mt-3">
          {grupo === 'recomendacoes' ? (
            <RecomendacoesDoGoogle customerId={customerId} campaignId={campaignId} moeda={leitura.moeda} />
          ) : emRevisao ? (
            <Confirmacao
              acao={emRevisao}
              leitura={leitura}
              motivo={motivo}
              validade={validade}
              erros={errosDoEnvio}
              enviando={propor.isPending}
              aoMudarMotivo={setMotivo}
              aoMudarValidade={setValidade}
              aoEnviar={enviar}
              aoVoltar={() => setEmRevisao(null)}
            />
          ) : (
            Formulario && (
              <Formulario
                key={`${grupo}-${versaoDoForm}`}
                contexto={contexto}
                aoRevisar={(a) => {
                  propor.reset();
                  setEmRevisao(a);
                }}
                statusInicial={preenchimento?.grupo === 'status' ? preenchimento.status : undefined}
              />
            )
          )}
        </div>

        {propor.data && !emRevisao && (
          <p className="mt-3 text-[12px]" role="status">
            {!propor.data.ja_existia
              ? 'Proposta registrada. Aguarda decisão de um administrador na fila abaixo.'
              : propor.data.proposta.estado === 'aguardando_aprovacao'
                ? 'Esta proposta já existia — mesmo pedido sobre o mesmo estado da conta.'
                : // A chave de idempotência não olha o estado: o mesmo pedido sobre o
                  // mesmo "antes" devolve a proposta antiga, mesmo recusada ou vencida.
                  `Este mesmo pedido já existe na fila como “${ESTADO_LEGIVEL[propor.data.proposta.estado] ?? propor.data.proposta.estado}”, e o ledger não registra o mesmo pedido duas vezes sobre o mesmo estado da conta.`}
          </p>
        )}
        {propor.error && grupo !== 'recomendacoes' && (
          <AvisoDeErro className="mt-3" erro={erroLegivel(propor.error)} />
        )}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[12px]">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={todaAConta} onChange={(e) => setTodaAConta(e.target.checked)} />
          mostrar propostas de toda a conta
        </label>
      </div>
      <FilaDePropostas
        customerId={customerId}
        propostas={propostas}
        permissoes={permissoes}
        carregando={fila.isLoading}
        erro={fila.error}
        aoRecarregar={() => fila.refetch()}
      />
    </section>
  );
};

const Confirmacao: React.FC<{
  acao: AcaoDeGestao;
  leitura: LeituraDaCampanha;
  motivo: string;
  validade: string;
  erros: { motivo?: string; validade?: string };
  enviando: boolean;
  aoMudarMotivo: (v: string) => void;
  aoMudarValidade: (v: string) => void;
  aoEnviar: () => void;
  aoVoltar: () => void;
}> = ({ acao, leitura, motivo, validade, erros, enviando, aoMudarMotivo, aoMudarValidade, aoEnviar, aoVoltar }) => (
  <div role="group" aria-label="confirmar proposta">
    <p className="text-[12px] font-medium">Confirme: {ROTULO_DO_TIPO[acao.tipo]}</p>
    <AntesDepois linhas={previaDaAcao(acao, leitura)} legenda="o que esta proposta muda" />
    <p className="mt-1.5 text-[11px] text-muted-foreground">
      O “antes” que vale é o que o servidor lê na conta ao propor; é ele que a fila mostra e que vai para a
      aprovação. Nada é enviado ao Google agora.
    </p>
    <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
      <div>
        <label htmlFor="g-motivo" className="text-[12px] font-medium">
          motivo
        </label>
        <textarea
          id="g-motivo"
          rows={2}
          className={cn(classeDeEntrada, 'mt-1')}
          value={motivo}
          aria-invalid={erros.motivo ? true : undefined}
          onChange={(e) => aoMudarMotivo(e.target.value)}
        />
        {erros.motivo && (
          <p className="mt-1 text-[11px] text-destructive" role="alert">
            {erros.motivo}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="g-validade" className="text-[12px] font-medium">
          vale por (horas)
        </label>
        <input
          id="g-validade"
          inputMode="numeric"
          placeholder={String(VALIDADE_PADRAO_HORAS)}
          className={cn(classeDeEntrada, 'mt-1')}
          value={validade}
          onChange={(e) => aoMudarValidade(e.target.value)}
        />
        {erros.validade && (
          <p className="mt-1 text-[11px] text-destructive" role="alert">
            {erros.validade}
          </p>
        )}
      </div>
    </div>
    <div className="mt-3 flex gap-2">
      <Button type="button" size="sm" disabled={enviando} onClick={aoEnviar}>
        {enviando ? 'Enviando proposta' : 'Enviar proposta'}
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={aoVoltar}>
        Voltar ao formulário
      </Button>
    </div>
  </div>
);

export default GerirCampanha;
