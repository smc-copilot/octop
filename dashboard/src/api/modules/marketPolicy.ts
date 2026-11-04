import { request } from "../request";

export type MarketResourceType = "skill" | "skillset";
export type MarketEffect = "allow" | "deny";

export interface MarketPolicyRule {
  id: string;
  resource_type: MarketResourceType;
  slug: string;
  effect: MarketEffect;
  user_group_id: string | null;
  priority: number;
  created_at: number;
  updated_at: number;
}

export interface MarketPolicyResponse {
  market_mode: string;
  valid_modes: string[];
  valid_resource_types: MarketResourceType[];
  valid_effects: MarketEffect[];
  rules: MarketPolicyRule[];
}

export interface CreateMarketPolicyRuleBody {
  resource_type: MarketResourceType;
  slug: string;
  effect: MarketEffect;
  user_group_id?: string | null;
  priority?: number;
}

export const marketPolicyApi = {
  list: () => request<MarketPolicyResponse>("/admin/market-policy"),

  createRule: (body: CreateMarketPolicyRuleBody) =>
    request<MarketPolicyRule>("/admin/market-policy/rules", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteRule: (ruleId: string) =>
    request<void>(`/admin/market-policy/rules/${encodeURIComponent(ruleId)}`, {
      method: "DELETE",
    }),
};
