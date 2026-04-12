import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import LikeButton from "./LikeButton";

describe("LikeButton", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("visar texten Like från början", () => {
    render(<LikeButton searchString="img-1" imageType="fullframe" />);
    expect(screen.getByRole("button", { name: "Like" })).toBeInTheDocument();
  });

  it("byter till Liked och skickar POST-anrop vid klick", async () => {
    const user = userEvent.setup();

    render(<LikeButton searchString="img-1" imageType="fullframe" />);

    await user.click(screen.getByRole("button", { name: "Like" }));

    expect(screen.getByRole("button", { name: "Liked" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/like", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        imageId: "img-1",
        type: "fullframe",
        isLiked: true,
      }),
    });
  });

  it("skickar inget anrop om searchString saknas", async () => {
    const user = userEvent.setup();

    render(<LikeButton searchString="" imageType="fullframe" />);

    await user.click(screen.getByRole("button", { name: "Like" }));

    expect(fetch).not.toHaveBeenCalled();
  });
});
