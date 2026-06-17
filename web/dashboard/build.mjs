import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = resolve(__dirname, "../..");
const outFile = resolve(__dirname, "app.bundle.js");
const fontTargets = [
  ["@fontsource/fraunces", "fraunces"],
  ["@fontsource/ibm-plex-sans", "ibm-plex-sans"],
  ["@fontsource/ibm-plex-mono", "ibm-plex-mono"],
];

function syncFonts() {
  const destRoot = resolve(__dirname, "fonts");
  mkdirSync(destRoot, { recursive: true });

  for (const [packageName, folderName] of fontTargets) {
    const source = resolve(rootDir, "node_modules", packageName);
    const target = resolve(destRoot, folderName);

    if (!existsSync(source)) {
      throw new Error(`Missing font package: ${packageName}`);
    }

    rmSync(target, { recursive: true, force: true });
    cpSync(source, target, { recursive: true });
  }
}

async function main() {
  syncFonts();

  await build({
    entryPoints: [resolve(__dirname, "app.js")],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: ["es2022"],
    outfile: outFile,
    sourcemap: true,
    minify: true,
    logLevel: "info",
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
