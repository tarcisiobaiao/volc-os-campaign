import React from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { formatBrlCurrency } from "@/utils/currencyUtils";

interface RevenueTooltipProps {
  netRevenue: number; // revenue_converted_revshare (valor líquido após revshare)
  grossRevenue?: number; // revenue_converted (valor bruto antes do revshare)
  revsharePercentage?: number; // Porcentagem do revshare (ex: 0.1 para 10%)
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  showInfo?: boolean;
}

export const RevenueTooltip: React.FC<RevenueTooltipProps> = ({
  netRevenue,
  grossRevenue,
  revsharePercentage = 0.1,
  children,
  side = "top",
  showInfo = true
}) => {
  // Calcular valor bruto se não fornecido
  const calculatedGrossRevenue = grossRevenue || (netRevenue / (1 - revsharePercentage));
  const revshareAmount = calculatedGrossRevenue - netRevenue;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1">
            {children}
            {showInfo && <Info className="h-3 w-3 text-muted-foreground opacity-50 hover:opacity-100 transition-opacity" />}
          </div>
        </TooltipTrigger>
        <TooltipContent side={side} className="max-w-xs p-3">
          <div className="space-y-2 text-sm">
            <div className="font-medium text-primary mb-2">
              💰 Detalhamento do Faturamento
            </div>
            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Faturamento Bruto (GAM):</span>
                <span className="font-mono">{formatBrlCurrency(calculatedGrossRevenue)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Revenue Share ({(revsharePercentage * 100).toFixed(1)}%):</span>
                <span className="font-mono text-orange-600">-{formatBrlCurrency(revshareAmount)}</span>
              </div>
              <div className="border-t pt-1 border-border">
                <div className="flex justify-between font-medium">
                  <span className="text-primary">Faturamento Líquido:</span>
                  <span className="font-mono text-green-600">{formatBrlCurrency(netRevenue)}</span>
                </div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border">
              Este é o valor líquido após desconto do revenue share, usado para cálculos de lucro e ROI.
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};