/**
 * Pure helpers for the admin "new user" published-expert template picker.
 */

import type { PublishedExpert } from "../../../api/modules/publishedExperts";

export interface ExpertTemplateOption {
  id: string;
  label: string;
  description?: string;
  icon_url?: string | null;
  icon_name?: string | null;
  creator_username?: string | null;
  slug?: string;
  updated_at?: string;
}

/** Sort published experts by updated_at descending; keep API order when unparseable. */
export function sortPublishedExpertsByUpdatedAt(
  rows: PublishedExpert[],
): PublishedExpert[] {
  const indexed = rows.map((row, index) => ({ row, index }));
  indexed.sort((a, b) => {
    const ta = Date.parse(a.row.updated_at || "");
    const tb = Date.parse(b.row.updated_at || "");
    const aOk = Number.isFinite(ta);
    const bOk = Number.isFinite(tb);
    if (aOk && bOk && ta !== tb) return tb - ta;
    if (aOk && !bOk) return -1;
    if (!aOk && bOk) return 1;
    return a.index - b.index;
  });
  return indexed.map((item) => item.row);
}

/** Map API PublishedExpert rows to picker options (value = record id, not slug). */
export function mapPublishedExpertsToOptions(
  rows: PublishedExpert[],
): ExpertTemplateOption[] {
  return sortPublishedExpertsByUpdatedAt(rows).map((row) => ({
    id: row.id,
    label: row.name,
    description: row.description || undefined,
    icon_url: row.icon_url,
    icon_name: row.icon_name,
    creator_username: row.creator_username,
    slug: row.slug,
    updated_at: row.updated_at,
  }));
}

/** Filter options by name, description, creator, or slug. */
export function filterExpertTemplateOptions(
  options: ExpertTemplateOption[],
  query: string,
): ExpertTemplateOption[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return options;
  return options.filter((item) =>
    [
      item.label,
      item.description ?? "",
      item.creator_username ?? "",
      item.slug ?? "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle),
  );
}
