/**
 * v6 RBAC — OnboardingWizard
 *
 * Wizard de 3 passos: Usuário → Acesso a campanhas → Comissão.
 *
 * Mudanças vs versão anterior (revisão de UX):
 *
 *   1. Passo 2 deixa de ser "uma campanha por vez" via combobox.
 *      Agora é um picker em lote: escolhe o projeto e marca várias
 *      campanhas com checkbox, com "Selecionar todas", "Limpar",
 *      busca e contador. Aplica um único role funcional para o
 *      lote inteiro (opção mais simples e mais rápida para o caso
 *      real de onboarding admin).
 *
 *   2. Passo 3 (comissão) lista APENAS as campanhas escolhidas no
 *      passo 2 — acompanha o raciocínio do admin. Permite ligar
 *      comissão como um todo, aplicar um percentual comum, ou
 *      ajustar individualmente por campanha.
 *
 *   3. Se o admin não quiser configurar comissão, pode pular o
 *      passo 3 inteiro com um único toggle ("Configurar comissão
 *      agora?" off por padrão se o role não for OPERATOR).
 */
import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  UserPlus,
  Users as UsersIcon,
  Receipt,
  Sparkles,
} from 'lucide-react';
import { UserForm } from '@/v6/components/forms/UserForm';
import { ProjectSelector } from '@/v6/components/forms/ProjectSelector';
import { CampaignMultiPicker } from '@/v6/components/forms/CampaignMultiPicker';
import type {
  CampaignWithContext,
  CampaignRole,
  CreateUserInput,
  OnboardingMembership,
  OnboardingCommission,
  ProjectLite,
} from '@/v6/types/v6';
import type { UserCreateValues } from '@/v6/forms/schemas';

interface OnboardingWizardProps {
  projects: ProjectLite[];
  campaigns: CampaignWithContext[];
  roles: CampaignRole[];
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (input: {
    user: CreateUserInput;
    memberships: OnboardingMembership[];
    commissions: OnboardingCommission[];
  }) => Promise<void> | void;
}

const todayIso = (): string => new Date().toISOString().slice(0, 10);

type Step = 1 | 2 | 3;

export function OnboardingWizard({
  projects,
  campaigns,
  roles,
  isSubmitting,
  onCancel,
  onSubmit,
}: OnboardingWizardProps) {
  const [step, setStep] = useState<Step>(1);
  const [userValues, setUserValues] = useState<UserCreateValues | null>(null);

  // Passo 2 — projeto + campanhas selecionadas + role aplicado ao lote
  const defaultRoleId = useMemo(
    () => roles.find((r) => r.code === 'OPERATOR')?.id ?? roles[0]?.id ?? 0,
    [roles]
  );
  const [m_projectId, setMProjectId] = useState<number | null>(null);
  const [m_selected, setMSelected] = useState<string[]>([]);
  const [m_roleId, setMRoleId] = useState<number>(defaultRoleId);

  // Quando os roles carregam, define o default operacional
  useEffect(() => {
    if (defaultRoleId && m_roleId === 0) setMRoleId(defaultRoleId);
  }, [defaultRoleId, m_roleId]);

  // Passo 3 — controle de comissão
  // Estrutura: por campaign_id selecionada, percentual e vigência.
  //
  // Regra de negócio: comissão SÓ existe para o role funcional
  // OPERATOR. Para OWNER/REVIEWER/VIEWER a comissão é desligada
  // automaticamente — isso reflete a regra real do sistema.
  const [c_enabled, setCEnabled] = useState<boolean>(false);
  const [c_bulkPct, setCBulkPct] = useState<string>('15');
  const [c_validFrom, setCValidFrom] = useState<string>(todayIso());
  const [c_overrides, setCOverrides] = useState<Record<string, string>>({});

  // Lookup do code do role escolhido no passo 2
  const selectedRoleCode = useMemo(
    () => roles.find((r) => r.id === m_roleId)?.code ?? null,
    [roles, m_roleId]
  );
  const commissionAllowed = selectedRoleCode === 'OPERATOR';

  // Se o admin trocar o role para algo que não admite comissão,
  // desliga a chave automaticamente para evitar criar regras inválidas.
  useEffect(() => {
    if (!commissionAllowed && c_enabled) {
      setCEnabled(false);
    }
  }, [commissionAllowed, c_enabled]);

  // Map id → nome para display
  const campaignNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of campaigns) map.set(c.campaign_id, c.campaign_name || c.campaign_id);
    return map;
  }, [campaigns]);

  // Submit final
  const handleFinalize = async () => {
    if (!userValues) return;
    const memberships: OnboardingMembership[] = m_selected.map((cid) => ({
      campaign_id: cid,
      role_id: m_roleId,
    }));
    const commissions: OnboardingCommission[] = c_enabled && commissionAllowed
      ? m_selected.map((cid) => {
          const override = c_overrides[cid];
          const pct = Number(override ?? c_bulkPct);
          return {
            campaign_id: cid,
            percentage: Number.isFinite(pct) ? pct : 0,
            valid_from: c_validFrom,
          };
        })
      : [];
    await onSubmit({ user: userValues, memberships, commissions });
  };

  return (
    <div className="w-full min-w-0 space-y-5 overflow-x-hidden">
      <Stepper step={step} />

      {/* ----------------------------------------------------------------
       * Passo 1 — Usuário
       * ---------------------------------------------------------------- */}
      {step === 1 && (
        <UserForm
          mode="create"
          defaultValues={userValues ?? undefined}
          onCancel={onCancel}
          submitLabel="Próximo"
          onSubmit={(values) => {
            setUserValues(values);
            setStep(2);
          }}
        />
      )}

      {/* ----------------------------------------------------------------
       * Passo 2 — Acesso (memberships) com multi-select
       * ---------------------------------------------------------------- */}
      {step === 2 && (
        <div className="space-y-4">
          <UserSummary userValues={userValues} />

          <div className="min-w-0 rounded-lg border bg-card p-3 sm:p-4">
            <div className="mb-3 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold">Acesso a campanhas</h3>
              <span className="text-xs text-muted-foreground">
                {m_selected.length} selecionada
                {m_selected.length !== 1 ? 's' : ''}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[2fr_1fr]">
              <div className="space-y-1">
                <Label className="text-[11px] text-muted-foreground">Projeto</Label>
                <ProjectSelector
                  projects={projects}
                  value={m_projectId}
                  onChange={(id) => {
                    setMProjectId(id);
                  }}
                  placeholder="Escolha o projeto"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-[11px] text-muted-foreground">
                  Role aplicado a todas
                </Label>
                <Select
                  value={String(m_roleId)}
                  onValueChange={(v) => setMRoleId(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map((r) => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="mt-3">
              <CampaignMultiPicker
                campaigns={campaigns}
                projectId={m_projectId}
                value={m_selected}
                onChange={setMSelected}
              />
            </div>

            {m_selected.length === 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Pode pular este passo se ainda não for atribuir acessos.
              </p>
            )}
          </div>

          <StepNavigation
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
            nextLabel={
              m_selected.length > 0
                ? `Próximo (${m_selected.length} campanha${m_selected.length !== 1 ? 's' : ''})`
                : 'Pular'
            }
          />
        </div>
      )}

      {/* ----------------------------------------------------------------
       * Passo 3 — Comissão (apenas sobre o que foi selecionado no passo 2)
       * ---------------------------------------------------------------- */}
      {step === 3 && (
        <div className="space-y-4">
          <UserSummary userValues={userValues} />

          <div className="min-w-0 rounded-lg border bg-card p-3 sm:p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">
                  Comissão{' '}
                  <span className="text-xs font-normal text-muted-foreground">
                    (opcional)
                  </span>
                </h3>
                <p className="text-[11px] text-muted-foreground">
                  Aplica um percentual às campanhas selecionadas no passo
                  anterior. Você pode ajustar individualmente abaixo.
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Label className="text-xs">Configurar agora</Label>
                <Switch
                  checked={c_enabled}
                  onCheckedChange={setCEnabled}
                  disabled={m_selected.length === 0 || !commissionAllowed}
                />
              </div>
            </div>

            {m_selected.length === 0 ? (
              <div className="rounded-md border border-dashed py-5 text-center text-xs text-muted-foreground">
                Nenhuma campanha selecionada no passo anterior — não há
                onde aplicar comissão.
              </div>
            ) : !commissionAllowed ? (
              <div className="rounded-md border border-dashed bg-muted/20 px-4 py-5 text-center text-xs text-muted-foreground">
                <p className="font-medium text-foreground">
                  Comissão indisponível para este role.
                </p>
                <p className="mt-1">
                  Apenas o role <strong>Operador</strong> recebe comissão.
                  Como você escolheu <strong>{selectedRoleCode ?? 'outro role'}</strong> no
                  passo anterior, esta etapa fica desativada. Para criar com
                  comissão, volte e aplique o role <strong>Operador</strong>.
                </p>
              </div>
            ) : !c_enabled ? (
              <div className="rounded-md border border-dashed py-5 text-center text-xs text-muted-foreground">
                Comissão desligada. O usuário será criado sem regra de
                comissão (pode ser configurada depois na aba "Comissões").
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2 rounded-md border bg-muted/20 p-3 sm:grid-cols-[120px_160px_1fr]">
                  <div className="space-y-1">
                    <Label className="text-[11px] text-muted-foreground">
                      % padrão
                    </Label>
                    <Input
                      type="number"
                      step="0.0001"
                      min={0}
                      max={100}
                      value={c_bulkPct}
                      onChange={(e) => setCBulkPct(e.target.value)}
                      className="h-8"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[11px] text-muted-foreground">
                      Vigência a partir de
                    </Label>
                    <Input
                      type="date"
                      value={c_validFrom}
                      onChange={(e) => setCValidFrom(e.target.value)}
                      className="h-8"
                    />
                  </div>
                  <div className="col-span-2 flex items-end sm:col-span-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 w-full text-[11px]"
                      onClick={() => setCOverrides({})}
                      disabled={Object.keys(c_overrides).length === 0}
                    >
                      <Sparkles className="mr-1 h-3.5 w-3.5" />
                      Aplicar % padrão a todas
                    </Button>
                  </div>
                </div>

                <ScrollArea className="mt-3 h-56 rounded-md border">
                  <ul className="divide-y">
                    {m_selected.map((cid) => {
                      const name = campaignNameById.get(cid) ?? cid;
                      const override = c_overrides[cid];
                      const value = override ?? c_bulkPct;
                      return (
                        <li
                          key={cid}
                          className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium">{name}</div>
                            <div className="truncate font-mono text-[10px] text-muted-foreground">
                              {cid}
                            </div>
                          </div>
                          <div className="flex w-28 items-center gap-1">
                            <Input
                              type="number"
                              step="0.0001"
                              min={0}
                              max={100}
                              value={value}
                              onChange={(e) =>
                                setCOverrides((prev) => ({
                                  ...prev,
                                  [cid]: e.target.value,
                                }))
                              }
                              className="h-7 text-xs"
                            />
                            <span className="text-[11px] text-muted-foreground">%</span>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </ScrollArea>
              </>
            )}
          </div>

          <div className="flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep(2)}
              disabled={isSubmitting}
            >
              <ArrowLeft className="mr-2 h-4 w-4" /> Voltar
            </Button>
            <Button
              type="button"
              onClick={handleFinalize}
              disabled={isSubmitting || !userValues}
            >
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Finalizar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------
// Sub-componentes locais
// ----------------------------------------------------------------

function Stepper({ step }: { step: Step }) {
  const items = [
    { n: 1 as Step, label: 'Usuário', icon: UserPlus },
    { n: 2 as Step, label: 'Acesso', icon: UsersIcon },
    { n: 3 as Step, label: 'Comissão', icon: Receipt },
  ];
  return (
    <ol className="flex w-full items-center justify-between gap-1 sm:justify-start sm:gap-1.5">
      {items.map(({ n, label, icon: Icon }, idx) => {
        const active = step === n;
        const done = step > n;
        return (
          <li key={n} className="flex min-w-0 items-center gap-1.5">
            <div
              className={
                'flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors ' +
                (done
                  ? 'border-primary bg-primary text-primary-foreground'
                  : active
                  ? 'border-primary text-primary'
                  : 'border-muted-foreground/30 text-muted-foreground')
              }
            >
              {done ? <Check className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
            </div>
            <span
              className={
                'truncate text-xs ' +
                (active ? 'font-medium text-foreground' : 'text-muted-foreground')
              }
            >
              {label}
            </span>
            {idx < items.length - 1 && (
              <span className="mx-1 hidden h-px w-5 shrink-0 bg-muted-foreground/20 sm:block" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function UserSummary({ userValues }: { userValues: UserCreateValues | null }) {
  if (!userValues) return null;
  return (
    <div className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-xs">
      <div className="min-w-0">
        <span className="font-medium">{userValues.name}</span>
        <span className="ml-2 text-muted-foreground">{userValues.email}</span>
      </div>
      <Badge variant="outline" className="text-[10px]">
        {userValues.role}
      </Badge>
    </div>
  );
}

function StepNavigation({
  onBack,
  onNext,
  nextLabel,
}: {
  onBack: () => void;
  onNext: () => void;
  nextLabel: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <Button type="button" variant="outline" onClick={onBack}>
        <ArrowLeft className="mr-2 h-4 w-4" /> Voltar
      </Button>
      <Button type="button" onClick={onNext}>
        {nextLabel} <ArrowRight className="ml-2 h-4 w-4" />
      </Button>
    </div>
  );
}
