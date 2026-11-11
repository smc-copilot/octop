import type { PluginSetupHost } from "./host";
import { BusinessCard } from "./BusinessCard";
import { ConfigCard } from "./ConfigCard";

export function setup(host: PluginSetupHost): void {
  host.registerRenderer({
    id: "business_ui_card",
    tools: ["business_ui_draft"],
    component: BusinessCard,
  });
  host.registerRenderer({
    id: "business_ui_config",
    tools: ["business_ui_connections"],
    component: ConfigCard,
  });
}
