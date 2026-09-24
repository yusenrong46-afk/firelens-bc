import { expect, test } from "vitest";
import { localBrowserOrigin } from "./localBrowserOrigin";

test("local browser override accepts only explicit loopback origins", () => {
  expect(localBrowserOrigin(undefined)).toBeUndefined();
  for (const origin of ["http://127.0.0.1:8786", "http://localhost:4175", "http://[::1]:4175"])
    expect(localBrowserOrigin(`${origin}/`)).toBe(origin);
});

test.each([
  "https://firelens-bc.vercel.app", "http://example.test", "https://127.0.0.1:8786", "http://127.0.0.1:8786/path",
  "http://user@127.0.0.1:8786", "http://127.0.0.1:8786?x=1", "http://127.0.0.1:8786#x", "",
])("local browser override rejects %s before creating a browser", value => {
  expect(() => localBrowserOrigin(value)).toThrow();
});
