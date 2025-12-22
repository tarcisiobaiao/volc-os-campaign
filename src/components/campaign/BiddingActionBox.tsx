import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/lib/supabase';
import { TrendingUp, TrendingDown, Minus, Zap, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { formatCostCurrency } from '@/utils/currencyUtils';

interface BiddingActionBoxProps {
  campaignId: string;
  currentBid: number;
  suggestedBid: number;
  action: 'AUMENTAR' | 'REDUZIR' | 'MANTER';
  risk: 'BAIXO' | 'MEDIO' | 'ALTO';
  variationPercent: number;
  dataReferencia: string;
}

export function BiddingActionBox({
  campaignId,
  currentBid,
  suggestedBid,
  action,
  risk,
  variationPercent,
  dataReferencia
}: BiddingActionBoxProps) {
  const { toast } = useToast();
  const [editedValue, setEditedValue] = useState<string>(suggestedBid.toFixed(4));
  const [isApplying, setIsApplying] = useState(false);
  const [hasApplied, setHasApplied] = useState(false);

  // Determinar cor e ícone baseado na ação
  const getActionConfig = () => {
    switch (action) {
      case 'AUMENTAR':
        return {
          icon: <TrendingUp className="h-5 w-5" />,
          color: 'text-green-600 dark:text-green-400',
          bgColor: 'bg-green-50 dark:bg-green-950/20',
          borderColor: 'border-green-200 dark:border-green-800'
        };
      case 'REDUZIR':
        return {
          icon: <TrendingDown className="h-5 w-5" />,
          color: 'text-red-600 dark:text-red-400',
          bgColor: 'bg-red-50 dark:bg-red-950/20',
          borderColor: 'border-red-200 dark:border-red-800'
        };
      default:
        return {
          icon: <Minus className="h-5 w-5" />,
          color: 'text-blue-600 dark:text-blue-400',
          bgColor: 'bg-blue-50 dark:bg-blue-950/20',
          borderColor: 'border-blue-200 dark:border-blue-800'
        };
    }
  };

  const getRiskBadge = () => {
    switch (risk) {
      case 'BAIXO':
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">🟢 Baixo Risco</Badge>;
      case 'MEDIO':
        return <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">🟡 Médio Risco</Badge>;
      case 'ALTO':
        return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300">🔴 Alto Risco</Badge>;
    }
  };

  const handleApply = async () => {
    const valueToApply = parseFloat(editedValue);

    // Validação
    if (isNaN(valueToApply) || valueToApply <= 0) {
      toast({
        title: "Valor inválido",
        description: "Por favor, insira um valor maior que zero.",
        variant: "destructive"
      });
      return;
    }

    setIsApplying(true);

    try {
      // 1. Salvar na tabela bid_actions
      const { data: bidActionData, error: insertError } = await supabase
        .from('bid_actions')
        .insert({
          campaign_id: campaignId,
          data_referencia: dataReferencia,
          valor_anterior: currentBid,
          valor_sugerido: suggestedBid,
          valor_aplicado: valueToApply,
          aplicado_por: 'user', // Você pode pegar do contexto de autenticação se tiver
          aplicado_com_sucesso: null, // Será atualizado pelo webhook
          erro_msg: null
        })
        .select('id')
        .single();

      if (insertError) {
        throw new Error(`Erro ao salvar no banco: ${insertError.message}`);
      }

      const bidActionId = bidActionData.id;

      // 2. Disparar webhook N8N
      const webhookUrl = 'https://n8n.srv860769.hstgr.cloud/webhook/1cb2069d-ae6b-4bdc-8773-c1c7fcbf54f3';
      const webhookPayload = {
        bid_action_id: bidActionId,
        campaign_id: campaignId,
        valor_aplicado: valueToApply
      };

      const webhookResponse = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(webhookPayload)
      });

      if (!webhookResponse.ok) {
        throw new Error(`Webhook falhou: ${webhookResponse.status} ${webhookResponse.statusText}`);
      }

      // Sucesso!
      setHasApplied(true);
      toast({
        title: "Bidding aplicado com sucesso!",
        description: `Novo valor: ${formatCostCurrency(valueToApply)}. A alteração será processada em breve.`,
        variant: "default"
      });

    } catch (error) {
      console.error('❌ Erro ao aplicar bidding:', error);

      toast({
        title: "Erro ao aplicar bidding",
        description: error instanceof Error ? error.message : "Ocorreu um erro desconhecido",
        variant: "destructive"
      });
    } finally {
      setIsApplying(false);
    }
  };

  const actionConfig = getActionConfig();
  const valueDiff = parseFloat(editedValue) - currentBid;
  const percentDiff = currentBid > 0 ? ((valueDiff / currentBid) * 100) : 0;

  return (
    <Card className={`border-2 ${actionConfig.borderColor} ${actionConfig.bgColor}`}>
      <CardHeader>
        <CardTitle className={`flex items-center gap-2 ${actionConfig.color}`}>
          <Zap className="h-6 w-6" />
          Ajuste de Bidding Sugerido
          {getRiskBadge()}
        </CardTitle>
        <CardDescription>
          O sistema analisou sua campanha e sugere a seguinte ação
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Ação recomendada */}
        <div className={`flex items-center gap-3 p-4 rounded-lg border ${actionConfig.borderColor} bg-white/60 dark:bg-gray-900/40`}>
          <div className={actionConfig.color}>
            {actionConfig.icon}
          </div>
          <div className="flex-1">
            <div className="font-semibold text-sm text-gray-600 dark:text-gray-400">Ação Recomendada</div>
            <div className={`text-lg font-bold ${actionConfig.color}`}>{action}</div>
          </div>
          <div className="text-right">
            <div className="font-semibold text-sm text-gray-600 dark:text-gray-400">Variação</div>
            <div className={`text-lg font-bold ${variationPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {variationPercent >= 0 ? '+' : ''}{variationPercent.toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Valores */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Bidding Atual</Label>
            <div className="text-2xl font-bold text-gray-800 dark:text-gray-200">
              {formatCostCurrency(currentBid)}
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Valor Sugerido</Label>
            <div className={`text-2xl font-bold ${actionConfig.color}`}>
              {formatCostCurrency(suggestedBid)}
            </div>
          </div>
        </div>

        {/* Input de edição */}
        <div className="space-y-2">
          <Label htmlFor="bid-value" className="flex items-center gap-2">
            Valor a Aplicar
            {parseFloat(editedValue) !== suggestedBid && (
              <Badge variant="secondary" className="text-xs">Editado</Badge>
            )}
          </Label>
          <div className="flex items-center gap-2">
            <span className="text-gray-600 dark:text-gray-400">R$</span>
            <Input
              id="bid-value"
              type="number"
              step="0.0001"
              min="0"
              value={editedValue}
              onChange={(e) => setEditedValue(e.target.value)}
              disabled={hasApplied || isApplying}
              className="text-lg font-mono"
            />
          </div>
          {valueDiff !== 0 && (
            <div className={`text-sm ${valueDiff > 0 ? 'text-green-600' : 'text-red-600'}`}>
              {valueDiff > 0 ? '+' : ''}{formatCostCurrency(Math.abs(valueDiff))} ({percentDiff >= 0 ? '+' : ''}{percentDiff.toFixed(1)}%) em relação ao atual
            </div>
          )}
        </div>

        {/* Aviso de risco alto */}
        {risk === 'ALTO' && (
          <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg">
            <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5" />
            <div className="text-sm text-red-700 dark:text-red-400">
              <strong>Atenção:</strong> Esta ação tem alto risco. Certifique-se de revisar os dados antes de aplicar.
            </div>
          </div>
        )}

        {/* Botão de aplicar */}
        <Button
          onClick={handleApply}
          disabled={hasApplied || isApplying}
          className="w-full gap-2"
          size="lg"
        >
          {isApplying ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Aplicando...
            </>
          ) : hasApplied ? (
            <>
              <CheckCircle2 className="h-5 w-5" />
              Aplicado com Sucesso
            </>
          ) : (
            <>
              <Zap className="h-5 w-5" />
              Aplicar Bidding
            </>
          )}
        </Button>

        {hasApplied && (
          <div className="text-xs text-center text-muted-foreground">
            A alteração foi enviada para processamento. Aguarde alguns minutos para que seja aplicada na campanha.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
