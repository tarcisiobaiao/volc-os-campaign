import { Layers } from "lucide-react";
import { Slider } from "@/components/ui/slider";

interface QuantitySliderProps {
  value: number;
  onChange: (value: number) => void;
}

export default function QuantitySlider({ value, onChange }: QuantitySliderProps) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-muted-foreground/70" />
          <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-wider">Quantidade</h3>
        </div>
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            min={1}
            max={20}
            value={value}
            onChange={(e) => {
              const v = Math.min(20, Math.max(1, Number(e.target.value) || 1));
              onChange(v);
            }}
            className="w-12 text-center py-1 px-1.5 rounded-lg border border-border/50 bg-muted/20 text-foreground text-sm font-bold focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/10 tabular-nums transition-all"
          />
        </div>
      </div>

      <Slider
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        min={1}
        max={20}
        step={1}
        className="w-full"
      />

      <p className="text-sm text-muted-foreground">
        Serão geradas{" "}
        <span className="font-bold text-primary tabular-nums">
          {value} {value === 1 ? "variação" : "variações"}
        </span>
      </p>
    </div>
  );
}
