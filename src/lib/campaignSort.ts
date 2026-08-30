import { calculateROAS } from "@/utils/roasCalculations";

export type CampaignSortKey = "roas" | "spend" | "revenue" | "name";

export const CAMPAIGN_SORT_OPTIONS: { value: CampaignSortKey; label: string }[] = [
  { value: "roas", label: "ROAS" },
  { value: "spend", label: "Gasto" },
  { value: "revenue", label: "Faturamento" },
  { value: "name", label: "A-Z" },
];

interface SortableCampaign {
  name?: string;
  revenue?: number;
  investment?: number;
}

const num = (x: unknown): number =>
  typeof x === "number" && Number.isFinite(x) ? x : 0;

export function sortCampaigns<T extends SortableCampaign>(
  list: T[],
  key: CampaignSortKey,
): T[] {
  const arr = [...list];
  switch (key) {
    case "roas":
      return arr.sort(
        (a, b) =>
          calculateROAS(num(b.revenue), num(b.investment)) -
          calculateROAS(num(a.revenue), num(a.investment)),
      );
    case "spend":
      return arr.sort((a, b) => num(b.investment) - num(a.investment));
    case "revenue":
      return arr.sort((a, b) => num(b.revenue) - num(a.revenue));
    case "name":
      return arr.sort((a, b) =>
        (a.name ?? "").localeCompare(b.name ?? "", "pt-BR", {
          sensitivity: "base",
        }),
      );
  }
}
