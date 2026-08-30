import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { DollarSign, TrendingUp, RefreshCw, Clock, CheckCircle } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { useToast } from "@/hooks/use-toast";
import { currencyConversionService } from "@/services/currencyConversionService";

interface ExchangeRateManagerProps {
  className?: string;
}

export const ExchangeRateManager: React.FC<ExchangeRateManagerProps> = ({ className }) => {
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);
  const [newRate, setNewRate] = useState<string>("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const { toast } = useToast();

  // Load current exchange rate from database
  const loadExchangeRate = async () => {
    try {
      setLoading(true);
      const { data, error } = await supabase
        .from('system_settings')
        .select('value, updated_at')
        .eq('key', 'dollar_exchange_rate')
        .single();

      if (error) throw error;

      if (data) {
        const rate = parseFloat(data.value);
        setExchangeRate(rate);
        setNewRate(rate.toFixed(2));
        
        // Format last update time
        if (data.updated_at) {
          const updateDate = new Date(data.updated_at);
          setLastUpdate(updateDate.toLocaleString('pt-BR'));
        }
      }
    } catch (error) {
      console.error('Error loading exchange rate:', error);
      toast({
        title: "Erro ao carregar taxa de câmbio",
        description: "Não foi possível carregar a taxa atual",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Update exchange rate
  const updateExchangeRate = async () => {
    const normalized = newRate.replace(',', '.').trim();
    const rateValue = parseFloat(normalized);
    if (!Number.isFinite(rateValue) || rateValue <= 0 || rateValue >= 100) {
      toast({
        title: "Valor inválido",
        description: "Informe um valor > 0 e < 100 (ex: 4.90)",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsUpdating(true);

      const { error: rpcError } = await supabase.rpc('rpc_set_dollar_exchange_rate', { p_rate: rateValue });
      if (rpcError) throw rpcError;

      // Update timestamp of last manual update
      await supabase
        .from('system_settings')
        .update({
          value: new Date().toISOString()
        })
        .eq('key', 'last_currency_update');

      setExchangeRate(rateValue);
      setLastUpdate(new Date().toLocaleString('pt-BR'));

      // Clear cache in currency conversion service
      currencyConversionService.clearCache();

      // Update all revenue_converted values in database
      try {
        await currencyConversionService.updateDatabaseConversions();
        console.log('✅ Database revenue conversions updated successfully');
      } catch (dbError) {
        console.warn('⚠️ Warning: Failed to update database conversions:', dbError);
        // Don't fail the whole operation if database update fails
      }

      toast({
        title: "Taxa atualizada com sucesso!",
        description: `Nova taxa: R$ ${rateValue.toFixed(2)} por USD. Conversões atualizadas no banco de dados.`,
        variant: "default",
      });

    } catch (error) {
      console.error('Error updating exchange rate:', error);
      const msg = error instanceof Error ? error.message : String(error);
      toast({
        title: "Erro ao atualizar taxa",
        description: msg || "Não foi possível salvar a nova taxa de câmbio",
        variant: "destructive",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // Load on component mount
  useEffect(() => {
    loadExchangeRate();
  }, []);



  if (loading) {
    return (
      <Card className={`${className} relative overflow-hidden shadow-card`}>
        <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
        <CardHeader className="pb-2 pt-3 px-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-success/10 text-success p-1.5"><DollarSign className="h-4 w-4" /></span>
              <div className="space-y-1.5">
                <div className="skeleton h-3 w-24 rounded" />
                <div className="skeleton h-2.5 w-14 rounded" />
              </div>
            </div>
            <div className="skeleton h-6 w-16 rounded-full" />
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3 pt-1">
          <div className="skeleton h-8 w-full rounded-md" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={`${className} relative overflow-hidden shadow-card hover-lift reveal`} style={{ ['--i' as any]: 0 }}>
      <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-success/10 text-success p-1.5">
              <DollarSign className="h-4 w-4" />
            </span>
            <div>
              <span className="kicker block">Taxa de Câmbio</span>
              <p className="text-xs text-muted-foreground">USD → BRL</p>
            </div>
          </div>
          <Badge variant="secondary" className="text-xs px-2 py-0.5">
            <TrendingUp className="h-3 w-3 mr-1 text-success" />
            <span className="font-display tabular">R$ {exchangeRate.toFixed(2)}</span>
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-3 pt-1">
        {/* Compact Update Rate Form */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <span className="absolute left-2 top-1/2 transform -translate-y-1/2 text-xs text-muted-foreground">
              R$
            </span>
            <Input
              id="newRate"
              type="number"
              value={newRate}
              onChange={(e) => setNewRate(e.target.value)}
              placeholder="5.50"
              step="0.01"
              min="0.01"
              className="pl-6 h-8 text-sm tabular"
            />
          </div>
          <Button 
            onClick={updateExchangeRate}
            disabled={isUpdating || !newRate}
            size="sm"
            className="h-8 px-3 text-xs"
          >
            {isUpdating ? (
              <>
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                Salvando
              </>
            ) : (
              <>
                <CheckCircle className="h-3 w-3 mr-1" />
                Atualizar
              </>
            )}
          </Button>
        </div>
        
        {lastUpdate && (
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-muted-foreground">
              Atualiza conversões automáticas USD → BRL
            </p>
            <div className="flex items-center text-xs text-muted-foreground">
              <Clock className="h-3 w-3 mr-1" />
              {lastUpdate}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ExchangeRateManager;