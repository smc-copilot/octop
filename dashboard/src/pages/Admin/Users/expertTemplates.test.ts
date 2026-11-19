import { describe, expect, it, vi } from "vitest";

import type { PublishedExpert } from "../../../api/modules/publishedExperts";
import {
  filterExpertTemplateOptions,
  mapPublishedExpertsToOptions,
  sortPublishedExpertsByUpdatedAt,
} from "./expertTemplates";

function expert(
  overrides: Partial<PublishedExpert> & Pick<PublishedExpert, "id" | "name">,
): PublishedExpert {
  return {
    slug: overrides.slug ?? overrides.id,
    description: overrides.description ?? "",
    created_by: overrides.created_by ?? "1",
    creator_username: overrides.creator_username ?? "alice",
    source_agent_id: overrides.source_agent_id ?? null,
    icon_name: overrides.icon_name ?? null,
    icon_url: overrides.icon_url ?? null,
    color: overrides.color ?? null,
    created_at: overrides.created_at ?? "2026-01-01T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("mapPublishedExpertsToOptions", () => {
  it("uses PublishedExpert.id as the option value, not slug", () => {
    const options = mapPublishedExpertsToOptions([
      expert({
        id: "01J_PUBLISHED",
        slug: "ops-engineer",
        name: "Ops",
        description: "Linux",
        creator_username: "bob",
        icon_name: "terminal",
      }),
    ]);
    expect(options).toEqual([
      {
        id: "01J_PUBLISHED",
        label: "Ops",
        description: "Linux",
        icon_url: null,
        icon_name: "terminal",
        creator_username: "bob",
        slug: "ops-engineer",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
  });

  it("sorts by updated_at descending and keeps API order when timestamps are missing", () => {
    const sorted = sortPublishedExpertsByUpdatedAt([
      expert({ id: "a", name: "A", updated_at: "2026-01-01T00:00:00Z" }),
      expert({ id: "b", name: "B", updated_at: "2026-02-01T00:00:00Z" }),
      expert({ id: "c", name: "C", updated_at: "not-a-date" }),
    ]);
    expect(sorted.map((row) => row.id)).toEqual(["b", "a", "c"]);
  });
});

describe("filterExpertTemplateOptions", () => {
  const options = mapPublishedExpertsToOptions([
    expert({
      id: "1",
      name: "Ops Engineer",
      description: "Kubernetes",
      creator_username: "alice",
      slug: "ops-k8s",
    }),
    expert({
      id: "2",
      name: "Writer",
      description: "Docs",
      creator_username: "carol",
      slug: "writer",
    }),
  ]);

  it("matches name, description, creator_username, and slug", () => {
    expect(filterExpertTemplateOptions(options, "kube").map((o) => o.id)).toEqual([
      "1",
    ]);
    expect(filterExpertTemplateOptions(options, "carol").map((o) => o.id)).toEqual([
      "2",
    ]);
    expect(filterExpertTemplateOptions(options, "ops-k8s").map((o) => o.id)).toEqual([
      "1",
    ]);
  });
});

describe("publishedExpertsApi list path", () => {
  it("loads templates from /experts/published", async () => {
    const request = vi.fn().mockResolvedValue([]);
    vi.doMock("../../../api/request", () => ({ request }));
    const { publishedExpertsApi } = await import(
      "../../../api/modules/publishedExperts"
    );
    await publishedExpertsApi.list();
    expect(request).toHaveBeenCalledWith("/experts/published");
  });
});
