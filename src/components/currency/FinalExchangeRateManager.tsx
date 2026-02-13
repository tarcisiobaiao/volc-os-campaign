import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { Badge } from "@/components/ui/badge";
import { DollarSign, TrendingUp, RefreshCw, Clock, CheckCircle } from "lucide-react";
import { secureApi } from "@/lib/secureApi";
import { useToast } from "@/hooks/use-toast";
import { clearExchangeRateCache } from "@/utils/currencyUtils";

export const FinalExchangeRateManager: React.FC = () => {
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
      const data = await secureApi.query<{ value: string; updated_at: string }>({
        table: 'system_settings',
        select: 'value, updated_at',
        filters: [{ field: 'key', operator: 'eq', value: 'dollar_exchange_rate' }]
      });

      if (data && data.length > 0) {
        const record = data[0];
        const rate = parseFloat(record.value);
        setExchangeRate(rate);
        setNewRate(rate.toFixed(2));

        if (record.updated_at) {
          const updateDate = new Date(record.updated_at);
          setLastUpdate(updateDate.toLocaleString('pt-BR'));
        }
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

      await secureApi.update({
        table: 'system_settings',
        data: {
          value: rateValue.toString(),
          updated_at: new Date().toISOString()
        },
        filters: [{ field: 'key', operator: 'eq', value: 'dollar_exchange_rate' }]
      });

      setExchangeRate(rateValue);
      setLastUpdate(new Date().toLocaleString('pt-BR'));

      // Clear all currency caches so conversion updates immediately
      clearExchangeRateCache();

      toast({
        title: "Taxa atualizada!",
        description: `Nova taxa: R$ ${rateValue.toFixed(2)} por USD`,
      });

    } catch (error) {
      console.error('Error updating exchange rate:', error);
      toast({
        title: "Erro ao atualizar",
        description: "Tente novamente em alguns instantes",
        variant: "destructive",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  useEffect(() => {
    loadExchangeRate();
  }, []);



  if (loading) {
    return (
      <Card className="shadow-sm border-gray-200 bg-white">
        <CardContent className="flex items-center justify-center p-4">
          <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground mr-2" />
          <span className="text-sm text-muted-foreground">Carregando...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-sm border-gray-200 bg-white">
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded bg-gray-100 text-gray-600">
              <DollarSign className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-medium text-gray-800">Taxa de Câmbio</CardTitle>
              <CardDescription className="text-xs text-gray-500">
                USD → BRL
              </CardDescription>
            </div>
          </div>
          <Badge variant="secondary" className="text-xs px-2 py-0.5">
            <TrendingUp className="h-3 w-3 mr-1" />
            R$ {exchangeRate.toFixed(2)}
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
              className="pl-6 h-8 text-sm border-gray-200 focus:border-blue-400"
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