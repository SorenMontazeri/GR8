import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import ImageCarousel from "./ImageCarousel";

describe("ImageCarousel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("visar testbilder när searchString saknas", () => {
    render(<ImageCarousel searchString="" />);

    expect(screen.getByRole("img")).toHaveAttribute("src", "/bird.jpg");
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Visar testbilder")).toBeInTheDocument();
  });

  it("hämtar bilder från API när searchString finns", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        images: ["abc123", "def456"],
      }),
    });

    render(<ImageCarousel searchString="cat" />);

    expect(screen.getByText("Laddar sekvens...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("img")).toHaveAttribute(
        "src",
        "data:image/jpeg;base64,abc123"
      );
    });

    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/sequence/cat");
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Visar: cat")).toBeInTheDocument();
  });

  it("kan bläddra till nästa bild", async () => {
    const user = userEvent.setup();

    render(<ImageCarousel searchString="" />);

    await user.click(screen.getByRole("button", { name: ">" }));

    expect(screen.getByRole("img")).toHaveAttribute("src", "/flower.jpg");
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("visar felmeddelande om API returnerar tom lista", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        images: [],
      }),
    });

    render(<ImageCarousel searchString="unknown" />);

    await waitFor(() => {
      expect(
        screen.getByText('Ingen sekvens hittades för "unknown"')
      ).toBeInTheDocument();
    });
  });
});
