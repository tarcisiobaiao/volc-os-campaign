import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { DollarSign, RefreshCw, CheckCircle, Settings } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { useToast } from "@/hooks/use-toast";
import { currencyConversionService } from "@/services/currencyConversionService";

interface CompactExchangeRateManagerProps {
  className?: string;
}

export const CompactExchangeRateManager: React.FC<CompactExchangeRateManagerProps> = ({ className }) => {
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);
  const [newRate, setNewRate] = useState<string>("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const { toast } = useToast();

  // Load current exchange rate from database
  const loadExchangeRate = async () => {
    try {
      setLoading(true);
      const { data, error } = await supabase
        .from('system_settings')
        .select('value')
        .eq('key', 'dollar_exchange_rate')
        .single();

      if (error) throw error;

      if (data) {
        const rate = parseFloat(data.value);
        setExchangeRate(rate);
        setNewRate(rate.toFixed(2));
      }
    } catch (error) {
      console.error('Error loading exchange rate:', error);
    } finally {
      setLoading(false);
    }
  };

  // Update exchange rate
  const updateExchangeRate = async () => {
    if (!newRate || parseFloat(newRate) <= 0) {
      toast({
        title: "Valor inválido",
        description: "Por favor, insira um valor válido maior que zero",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsUpdating(true);
      const rateValue = parseFloat(newRate);

      // Update system settings
      const { error: settingsError } = await supabase
        .from('system_settings')
        .update({
          value: rateValue.toString(),
          updated_at: new Date().toISOString()
        })
        .eq('key', 'dollar_exchange_rate');

      if (settingsError) throw settingsError;

      setExchangeRate(rateValue);

      // Clear cache in currency conversion service
      currencyConversionService.clearCache();

      // Update all revenue_converted values in database
      try {
        await currencyConversionService.updateDatabaseConversions();
      } catch (dbError) {
        console.warn('⚠️ Warning: Failed to update database conversions:', dbError);
      }

      toast({
        title: "Taxa atualizada!",
        description: `Nova taxa: R$ ${rateValue.toFixed(2)}`,
        variant: "default",
      });

      setIsOpen(false);
    } catch (error) {
      console.error('Error updating exchange rate:', error);
      toast({
        title: "Erro ao atualizar taxa",
        description: "Não foi possível salvar a nova taxa",
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
      <div className={`flex items-center gap-2 ${className}`}>
        <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Carregando...</span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 gap-2 hover-lift">
            <DollarSign className="h-3 w-3 text-success" />
            <span className="kicker">USD/BRL</span>
            <Badge variant="secondary" className="text-xs px-1.5 py-0.5">
              <span className="font-display tabular">{exchangeRate.toFixed(2)}</span>
            </Badge>
            <Settings className="h-3 w-3" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-3 shadow-elevated" align="end">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-success/10 text-success p-1.5">
                <DollarSign className="h-4 w-4" />
              </span>
              <div>
                <span className="kicker block">Taxa de Câmbio USD → BRL</span>
                <p className="text-xs text-muted-foreground">
                  Configurar conversão automática de revenue
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <span className="absolute left-2 top-1/2 transform -translate-y-1/2 text-xs text-muted-foreground">
                  R$
                </span>
                <Input
                  type="number"
                  aria-label="Nova taxa de câmbio, em reais por dólar"
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
                className="h-8 px-3"
              >
                {isUpdating ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCircle className="h-3 w-3" />
                )}
              </Button>
            </div>
            
            <p className="text-xs text-muted-foreground">
              Atualiza automaticamente todos os valores de revenue no sistema
            </p>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};

export default CompactExchangeRateManager;




