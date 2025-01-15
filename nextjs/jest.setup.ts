import "@testing-library/jest-dom";

// Add any other setup (like mocks) here
jest.mock("next/navigation", () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
    };
  },
  useSearchParams: () => jest.fn(),
}));
