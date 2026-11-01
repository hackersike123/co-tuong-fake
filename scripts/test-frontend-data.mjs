import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, rmSync } from "node:fs";

const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = mkdtempSync(join(process.env.TMPDIR || tmpdir(), "ky-tien-hoi-tests-"));
try {
  execFileSync(
    process.execPath,
    [
      require.resolve("typescript/bin/tsc"),
      "--target",
      "ES2022",
      "--module",
      "CommonJS",
      "--moduleResolution",
      "Node",
      "--strict",
      "--esModuleInterop",
      "--skipLibCheck",
      "--types",
      "node",
      "--rootDir",
      root,
      "--outDir",
      output,
      "src/data.ts",
      "src/game-clock.ts",
      "src/ranks.ts",
      "src/room-interactions.ts",
      "src/room-join.ts",
      "tests/frontend/data.test.ts",
      "tests/frontend/game-clock.test.ts",
      "tests/frontend/api-base.test.ts",
      "tests/frontend/ranks.test.ts",
      "tests/frontend/room-interactions.test.ts",
      "src/config/api-base.ts",
    ],
    { cwd: root, stdio: "inherit" },
  );
  execFileSync(
    process.execPath,
    [
      "--test",
      join(output, "tests", "frontend", "data.test.js"),
      join(output, "tests", "frontend", "game-clock.test.js"),
      join(output, "tests", "frontend", "api-base.test.js"),
      join(output, "tests", "frontend", "ranks.test.js"),
      join(output, "tests", "frontend", "room-interactions.test.js"),
    ],
    {
      cwd: root,
      stdio: "inherit",
    },
  );
} finally {
  rmSync(output, { recursive: true, force: true });
}
