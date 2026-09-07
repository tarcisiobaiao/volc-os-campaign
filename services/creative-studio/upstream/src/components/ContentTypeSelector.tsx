import { Megaphone, Newspaper, Pin } from "lucide-react";

export type ContentType = "meta-ads" | "news" | "pinterest";

interface Option {
  id: ContentType;
  label: string;
  description: string;
  icon: typeof Megaphone;
  badge: string;
}

const options: Option[] = [
  {
    id: "meta-ads",
    label: "Meta Ads",
    description: "Criativos para campanhas",
    icon: Megaphone,
    badge: "Feed · Stories · Reels",
  },
  {
    id: "news",
    label: "Notícias",
    description: "Editorial estilo revista",
    icon: Newspaper,
    badge: "4:5 · Instagram",
  },
  {
    id: "pinterest",
    label: "Pinterest",
    description: "Cards informativos",
    icon: Pin,
    badge: "9:16 · Pinterest",
  },
];

interface ContentTypeSelectorProps {
  selected: ContentType;
  onSelect: (type: ContentType) => void;
}

export default function ContentTypeSelector({ selected, onSelect }: ContentTypeSelectorProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-wider">
          Tipo de Postagem
        </h3>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {options.map((opt) => {
          const Icon = opt.icon;
          const isActive = selected === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => onSelect(opt.id)}
              className={`relative flex flex-col items-center gap-2.5 p-4 rounded-xl border transition-all duration-300 text-center
                ${isActive
                  ? "border-primary bg-primary/[0.06] card-glow-selected"
                  : "border-border/60 bg-card/50 hover:border-primary/30 hover:bg-card hover:shadow-md"
                }`}
            >
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300
                  ${isActive
                    ? "bg-primary text-primary-foreground shadow-md shadow-primary/30"
                    : "bg-muted/50 text-muted-foreground"
                  }`}
              >
                <Icon className="w-5 h-5" />
              </div>

              <div className="space-y-0.5">
                <p className={`text-sm font-semibold transition-colors ${isActive ? "text-primary" : "text-foreground/80"}`}>
                  {opt.label}
                </p>
                <p className="text-[10px] text-muted-foreground/60 leading-tight">
                  {opt.description}
                </p>
              </div>

              <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full transition-colors
                ${isActive
                  ? "bg-primary/10 text-primary/80"
                  : "bg-muted/60 text-muted-foreground/50"
                }`}>
                {opt.badge}
              </span>

              {isActive && (
                <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-primary border-2 border-background animate-scale-in" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
