import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppErrorBoundary } from "./ErrorBoundary";

function BrokenChild(): never {
  throw new Error("render failed");
}

describe("AppErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("shows a recoverable fallback when a child render fails", () => {
    render(
      <AppErrorBoundary>
        <BrokenChild />
      </AppErrorBoundary>
    );

    expect(screen.getByRole("alert")).toHaveTextContent("画布界面加载失败");
  });
});
