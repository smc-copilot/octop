import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConnectorsPage from "./index";

const { useConnectorInstances } = vi.hoisted(() => ({
  useConnectorInstances: vi.fn(),
}));

vi.mock("./useConnectors", () => ({ useConnectorInstances }));
vi.mock("../../../api/modules/connectors", () => ({
  connectorsApi: {
    oauthPending: vi.fn(),
  },
}));
vi.mock("../../../layouts/PageShell", () => ({
  default: {
    Tabbed: ({
      tabBar,
      children,
    }: {
      tabBar: ReactNode;
      children: ReactNode;
    }) => (
      <div>
        {tabBar}
        <main>{children}</main>
      </div>
    ),
  },
}));
vi.mock("./ConnectorCard", () => ({
  ConnectorCard: ({ entry }: { entry: { name: string } }) => (
    <div>{entry.name} built-in connector</div>
  ),
}));
vi.mock("./ConnectorInstanceCard", () => ({
  ConnectorInstanceCard: ({
    instance,
  }: {
    instance: { display_name: string };
  }) => <div>{instance.display_name} enabled connector</div>,
}));
vi.mock("./CustomMcpTab", () => ({
  CustomMcpTab: () => <div>Custom MCP servers</div>,
}));
vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1, role: "admin" }),
}));

function renderPage(initialEntry = "/connectors") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ConnectorsPage />
    </MemoryRouter>,
  );
}

describe("connector tab content isolation", () => {
  beforeEach(() => {
    useConnectorInstances.mockReturnValue({
      catalog: [{ kind: "builtin-a", name: "Calendar" }],
      instances: [
        {
          instance_id: "instance-1",
          kind: "builtin-a",
          display_name: "Work calendar",
          has_credentials: true,
        },
      ],
      loading: false,
      refresh: vi.fn(),
    });
  });

  it("switches among enabled, builtin, and custom tabs", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByText("Work calendar enabled connector")).toBeVisible();

    await user.click(
      screen.getByRole("tab", { name: "connectors.tabBuiltin" }),
    );
    await waitFor(() =>
      expect(screen.getByText("Calendar built-in connector")).toBeVisible(),
    );

    await user.click(screen.getByRole("tab", { name: "connectors.tabCustom" }));
    await waitFor(() =>
      expect(screen.getByText("Custom MCP servers")).toBeVisible(),
    );

    await user.click(
      screen.getByRole("tab", { name: "connectors.tabEnabled" }),
    );
    await waitFor(() =>
      expect(screen.getByText("Work calendar enabled connector")).toBeVisible(),
    );
  });
});
