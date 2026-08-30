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
      const data = await secureApi.getSettings(['dollar_exchange_rate']);

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

      // Uma requisição, uma rota nomeada, exigindo ADMIN no servidor. A rota
      // dispara `rpc_set_dollar_exchange_rate` — que grava a taxa e recalcula
      // o mês inteiro na mesma transação — e carimba `last_currency_update`.
      //
      // Antes eram duas chamadas pelos proxies genéricos: o nome da FUNÇÃO e o
      // nome da TABELA saíam daqui, do navegador, e o servidor executava com
      // `service_role` sem perguntar quem era. Sequência de duas escritas a
      // partir do cliente também significa que a segunda podia falhar sozinha,
      // deixando a taxa nova com o carimbo velho.
      await secureApi.setExchangeRate(rateValue);

      setExchangeRate(rateValue);
      setLastUpdate(new Date().toLocaleString('pt-BR'));

      // Clear all currency caches so conversion updates immediately
      clearExchangeRateCache();

      const currentMonth = new Date().toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
      toast({
        title: "Taxa atualizada",
        description: `R$ ${rateValue.toFixed(2)}/USD — mês de ${currentMonth} inteiro recalculado`,
      });

    } catch (error) {
      console.error('Error updating exchange rate:', error);
      const msg = error instanceof Error ? error.message : String(error);
      toast({
        title: "Erro ao atualizar",
        description: msg || "Tente novamente em alguns instantes",
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
      <Card className="relative overflow-hidden shadow-card">
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
    <Card className="relative overflow-hidden shadow-card hover-lift reveal" style={{ ['--i' as any]: 0 }}>
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
              Recalcula o mês inteiro ao alterar
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