import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CAMPAIGN_SORT_OPTIONS,
  type CampaignSortKey,
} from "@/lib/campaignSort";

interface CampaignSortSelectProps {
  value: CampaignSortKey;
  onChange: (value: CampaignSortKey) => void;
  className?: string;
}

export function CampaignSortSelect({
  value,
  onChange,
  className,
}: CampaignSortSelectProps) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as CampaignSortKey)}>
      <SelectTrigger className={className ?? "w-44"}>
        <span className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="kicker shrink-0">Ordenar</span>
          <SelectValue />
        </span>
      </SelectTrigger>
      <SelectContent>
        {CAMPAIGN_SORT_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
