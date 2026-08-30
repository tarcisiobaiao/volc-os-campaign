import React, { useState } from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Info } from "lucide-react";
import { formatBrlCurrency } from "@/utils/currencyUtils";
import { useIsMobile } from "@/hooks/useIsMobile";

interface RevenueTooltipProps {
  netRevenue: number; // revenue_converted_revshare (valor líquido após revshare)
  grossRevenue?: number; // revenue_converted (valor bruto antes do revshare)
  revsharePercentage?: number; // Porcentagem do revshare (ex: 0.1 para 10%)
  projectType?: 'ADSENSE' | 'GAM' | string; // Tipo do projeto para exibir informações corretas
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  showInfo?: boolean;
}

export const RevenueTooltip: React.FC<RevenueTooltipProps> = ({
  netRevenue,
  grossRevenue,
  revsharePercentage = 0.1,
  projectType,
  children,
  side = "top",
  showInfo = true
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const isMobile = useIsMobile();
  
  // Para projetos ADSENSE, não há revshare, então netRevenue = grossRevenue
  const isAdSenseProject = projectType === 'ADSENSE';
  const calculatedGrossRevenue = isAdSenseProject ? netRevenue : (grossRevenue || (netRevenue / (1 - revsharePercentage)));
  const revshareAmount = isAdSenseProject ? 0 : (calculatedGrossRevenue - netRevenue);

  const tooltipContent = (
    <div className="space-y-2 text-sm">
      <div className="font-medium text-primary mb-2">
        Detalhamento do {isAdSenseProject ? 'Revenue' : 'Faturamento'}
      </div>
      <div className="space-y-1">
        {isAdSenseProject ? (
          // Para projetos ADSENSE: mostrar apenas o revenue total
          <>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Revenue Total (AdSense):</span>
              <span className="font-mono text-success">{formatBrlCurrency(netRevenue)}</span>
            </div>
            <div className="text-xs text-muted-foreground italic mt-2">
              * Projeto AdSense: Revenue sem desconto de RevShare
            </div>
          </>
        ) : (
          // Para projetos GAM: mostrar cálculo com revshare
          <>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Faturamento Bruto (GAM):</span>
              <span className="font-mono">{formatBrlCurrency(calculatedGrossRevenue)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Revenue Share ({(revsharePercentage * 100).toFixed(1)}%):</span>
              <span className="font-mono text-warning">-{formatBrlCurrency(revshareAmount)}</span>
            </div>
            <div className="border-t pt-1 border-border">
              <div className="flex justify-between font-medium">
                <span className="text-primary">Faturamento Líquido:</span>
                <span className="font-mono text-success">{formatBrlCurrency(netRevenue)}</span>
              </div>
            </div>
          </>
        )}
      </div>
      <div className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border">
        {isAdSenseProject
          ? 'Revenue total do AdSense, usado diretamente para cálculos de lucro e ROI.'
          : 'Este é o valor líquido após desconto do revenue share, usado para cálculos de lucro e ROI.'
        }
      </div>
    </div>
  );

  // Mobile: usar Dialog em vez de Tooltip
  if (isMobile && showInfo) {
    return (
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogTrigger asChild>
          <div className="flex items-center gap-1 cursor-pointer touch-target">
            {children}
            <Info className="h-4 w-4 text-muted-foreground opacity-70 hover:opacity-100 transition-opacity" />
          </div>
        </DialogTrigger>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Detalhamento do {isAdSenseProject ? 'Revenue' : 'Faturamento'}</DialogTitle>
          </DialogHeader>
          {tooltipContent}
        </DialogContent>
      </Dialog>
    );
  }

  // Desktop: usar Tooltip normal
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
          {tooltipContent}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};