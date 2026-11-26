import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Layout } from "./Layout";

describe("Layout", () => {
  it("names the current service and keeps the product sections", () => {
    render(
      <MemoryRouter initialEntries={["/files"]}>
        <Layout>
          <h1>Files</h1>
        </Layout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main");
    expect(screen.getByRole("link", { name: "Filenkov" }).getAttribute("href")).toBe("https://filenkov.store");
    expect(screen.getByRole("navigation", { name: "Primary" }).textContent).toContain("Documents");
    expect(screen.getByRole("link", { name: "Files" }).getAttribute("href")).toBe("/files");
    expect(screen.getByRole("link", { name: "Chat" }).getAttribute("href")).toBe("/chat");
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toContain(
      "https://filenkov.store/auth?return_to=",
    );
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeTruthy();
    expect(screen.getByText("Filenkov · Documents")).toBeTruthy();
  });
});
