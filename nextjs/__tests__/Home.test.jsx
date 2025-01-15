import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "@jest/globals";
import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders the main title", () => {
    render(<HomePage />);
    const headingElement = screen.getByRole("heading", {
      name: /Create T3 App/i,
    });
    expect(headingElement).toBeInTheDocument();
  });

  it("renders the First Steps link with description", () => {
    render(<HomePage />);
    const firstStepsLink = screen.getByRole("link", {
      name: /First Steps/i,
    });
    expect(firstStepsLink).toBeInTheDocument();
    expect(firstStepsLink).toHaveAttribute(
      "href",
      "https://create.t3.gg/en/usage/first-steps",
    );
    expect(screen.getByText(/Just the basics/i)).toBeInTheDocument();
  });

  it("renders the Documentation link with description", () => {
    render(<HomePage />);
    const docsLink = screen.getByRole("link", {
      name: /Documentation/i,
    });
    expect(docsLink).toBeInTheDocument();
    expect(docsLink).toHaveAttribute(
      "href",
      "https://create.t3.gg/en/introduction",
    );
    expect(
      screen.getByText(/Learn more about Create T3 App/i),
    ).toBeInTheDocument();
  });
});
