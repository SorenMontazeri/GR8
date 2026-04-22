import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import ImageCarousel from "./ImageCarousel";

describe("ImageCarousel", () => {
  it("visar testbilder när searchString saknas", () => {
    render(<ImageCarousel searchString="" />);

    expect(screen.getByRole("img")).toHaveAttribute("src", "/bird.jpg");
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Visar testbilder")).toBeInTheDocument();
  });

  it("visar base64-bilder när de skickas in via props", () => {
    render(<ImageCarousel searchString="cat" images={["abc123abc123abc123", "def456def456def456"]} />);

    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "data:image/jpeg;base64,abc123abc123abc123"
    );
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Visar: cat")).toBeInTheDocument();
  });

  it("respekterar redan färdiga data-url:er", () => {
    render(<ImageCarousel searchString="cat" images={["data:image/jpeg;base64,abc123"]} />);

    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "data:image/jpeg;base64,abc123"
    );
  });

  it("kan bläddra till nästa bild", async () => {
    const user = userEvent.setup();

    render(<ImageCarousel searchString="" />);

    await user.click(screen.getByRole("button", { name: ">" }));

    expect(screen.getByRole("img")).toHaveAttribute("src", "/flower.jpg");
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("visar felmeddelande om listan är tom", () => {
    render(<ImageCarousel searchString="unknown" images={[]} />);

    expect(
      screen.getByText('Ingen sekvens hittades för "unknown"')
    ).toBeInTheDocument();
  });

  it("visar felmeddelande för ogiltigt bildformat", () => {
    render(<ImageCarousel searchString="unknown" images={["not a valid image source"]} />);

    expect(screen.getByText("Ogiltigt bildformat i sekvensen.")).toBeInTheDocument();
  });
});
