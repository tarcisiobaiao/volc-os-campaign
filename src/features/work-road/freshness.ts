export type ReadingFreshness = "carregando" | "vivo" | "desatualizado" | "ausente" | "erro";

const STALE_AFTER_MS = 90_000;

export function readingFreshness(input: {
  dataUpdatedAt: number;
  isError: boolean;
  isPending: boolean;
  hasData: boolean;
  now?: number;
}): ReadingFreshness {
  if (input.isPending && !input.hasData) return "carregando";
  if (input.isError && !input.hasData) return "erro";
  if (input.isError && input.hasData) return "desatualizado";
  if (!input.hasData) return "ausente";
  const age = (input.now ?? Date.now()) - input.dataUpdatedAt;
  if (input.dataUpdatedAt > 0 && age > STALE_AFTER_MS) return "desatualizado";
  return "vivo";
}
