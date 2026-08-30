import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface MetricDeltaProps {
  current: number;
  previous: number | undefined;
  label: string;
  isLoading: boolean;
}

export const MetricDelta: React.FC<MetricDeltaProps> = ({ current, previous, label, isLoading }) => {
  if (isLoading) {
    return <div className="skeleton h-3 w-16 mt-0.5 mx-auto" />;
  }

  if (previous === undefined) return null;

  if (current > 0 && previous === 0) {
    return (
      <div className="flex items-center justify-center gap-0.5 mt-0.5">
        <span className="text-[10px] font-medium leading-none text-info">Novo</span>
      </div>
    );
  }

  if (previous === 0) return null;

  const delta = ((current - previous) / Math.abs(previous)) * 100;

  if (delta > 0.5) {
    return (
      <div className="flex items-center justify-center gap-0.5 mt-0.5">
        <TrendingUp className="h-3 w-3 text-success flex-shrink-0" />
        <span className="text-[10px] font-medium leading-none text-success tabular">
          +{delta.toFixed(1)}% {label}
        </span>
      </div>
    );
  }

  if (delta < -0.5) {
    return (
      <div className="flex items-center justify-center gap-0.5 mt-0.5">
        <TrendingDown className="h-3 w-3 text-destructive flex-shrink-0" />
        <span className="text-[10px] font-medium leading-none text-destructive tabular">
          {delta.toFixed(1)}% {label}
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center gap-0.5 mt-0.5">
      <Minus className="h-3 w-3 text-muted-foreground flex-shrink-0" />
      <span className="text-[10px] font-medium leading-none text-muted-foreground tabular">
        estável {label}
      </span>
    </div>
  );
};
