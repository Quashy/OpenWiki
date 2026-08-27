import { HeroUIProvider } from "@heroui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";

vi.mock("./api/health", () => ({
  getHealth: vi.fn(async () => ({ status: "ok" })),
}));

describe("App", () => {
  it("renders the baseline shell", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <HeroUIProvider>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </HeroUIProvider>,
    );

    expect(screen.getByText("OpenWiki V2")).toBeInTheDocument();
    expect(screen.getByText("M0 Baseline")).toBeInTheDocument();
    expect(await screen.findByText("Backend online")).toBeInTheDocument();

    queryClient.clear();
  });
});
