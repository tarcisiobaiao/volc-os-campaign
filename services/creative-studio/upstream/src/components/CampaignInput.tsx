import { Target, Newspaper, Pin } from "lucide-react";
import type { ContentType } from "./ContentTypeSelector";

interface CampaignInputProps {
  value: string;
  onChange: (value: string) => void;
  contentType?: ContentType;
}

const config: Record<ContentType, {
  icon: typeof Target;
  label: string;
  placeholder: string;
  hint: string;
}> = {
  "meta-ads": {
    icon: Target,
    label: "Objetivo da Campanha",
    placeholder: "Ex: Destacar preparatório para Polícia Federal com foco em aprovações reais...",
    hint: "Descreva o objetivo da campanha. Isso guia o estilo visual dos criativos.",
  },
  "news": {
    icon: Newspaper,
    label: "Contexto da Notícia",
    placeholder: "Ex: Concurso da Receita Federal abre 699 vagas com salários de até R$ 21.029...",
    hint: "Descreva o tema ou título da notícia. O visual será uma capa editorial.",
  },
  "pinterest": {
    icon: Pin,
    label: "Ideia Central",
    placeholder: "Ex: Salário e detalhes do Concurso IBGE 2025 — 26.460 vagas, até R$ 4.554...",
    hint: "Descreva os dados ou tema do card. Quanto mais detalhes, melhor o resultado.",
  },
};

export default function CampaignInput({ value, onChange, contentType = "meta-ads" }: CampaignInputProps) {
  const { icon: Icon, label, placeholder, hint } = config[contentType];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-muted-foreground/70" />
        <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-wider">
          {label}
        </h3>
      </div>

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full min-h-[110px] p-4 rounded-xl border border-border/50 bg-muted/20 text-foreground placeholder:text-muted-foreground/40 resize-none transition-all duration-200 focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 focus:bg-card/50 text-sm leading-relaxed"
      />
      <p className="text-xs text-muted-foreground/50">{hint}</p>
    </div>
  );
}
