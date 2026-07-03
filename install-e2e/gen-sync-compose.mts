/**
 * Headless generator for the admin SYNC / reconcile compose — the OTHER compose
 * generator in the fleet.
 *
 * The install-e2e harness already stands up the INSTALLER's export compose
 * (gen-export-compose.mts). But the 2026-06 fleet-outage bug lived in the ADMIN
 * SYNC/reconcile path's compose (jarvis-admin's compose-generator), which the
 * harness never exercised. This script regenerates THAT compose so the same
 * migrate-entrypoint + migrations-ran assertions can run against it.
 *
 * It imports the real `generateCompose` from the admin server source (the exact
 * function admin's /api/install reconcile calls), so a generator regression is
 * caught here — not by hand on a user's box.
 *
 * The admin server source is resolved from --admin-dir (default: the cwd this
 * script is run from), so it works whether the admin checkout is `jarvis-admin`
 * (CI) or a sibling of the umbrella repo (local). Run it from / point it at the
 * jarvis-admin/server checkout so its deps + tsx resolve:
 *
 *   ( cd jarvis-admin/server && npx tsx \
 *       "$GITHUB_WORKSPACE/install-e2e/gen-sync-compose.mts" \
 *       --out "$GITHUB_WORKSPACE/install-e2e/docker-compose.sync.yaml" )
 */
import { chmodSync, readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { dirname, join, resolve } from "node:path";

const { values } = parseArgs({
  options: {
    out: { type: "string", default: "docker-compose.sync.yaml" },
    // Where the admin server source lives. Defaults to cwd (run from
    // jarvis-admin/server) so the relative-path imports below resolve.
    "admin-dir": { type: "string", default: process.cwd() },
    // --bundle also writes .env + init-db.sh next to --out, so the (standard-mode)
    // sync compose can actually `docker compose up` in the live lane. Without it
    // (static lane), only the compose is emitted — enough to assert entrypoints.
    bundle: { type: "boolean", default: false },
    // GPU flavor for the reconcile state (state.hardware.gpuType). The GPU
    // install-e2e lanes use this so the ADMIN generator's GPU output (image
    // suffixes + device passthrough) is exercised on a real rented GPU, not
    // just the installer's. Default matches the CPU harness: none.
    gpu: { type: "string", default: "none" },
    // Whisper image variant (state.whisperBackend) — independent of --gpu,
    // same as the wizard's separate whisper choice.
    "whisper-backend": { type: "string", default: "cpu" },
    modules: {
      type: "string",
      // Include jarvis-llm-proxy-api: in the ADMIN registry it's `recommended`
      // (not core, unlike the installer), so it's only emitted when enabled. We
      // enable it so the sync compose covers the FULL migrate-set (the static +
      // live lanes assert llm-proxy's migrate entrypoint / at-head too).
      default:
        "jarvis-llm-proxy-api,jarvis-whisper-api,jarvis-tts,jarvis-notifications,jarvis-web,jarvis-admin",
    },
  },
});

const adminDir = resolve(values["admin-dir"]!);

const GPU_TYPES = new Set(["none", "nvidia", "amd", "amd-rocm"]);
const WHISPER_BACKENDS = new Set(["cpu", "cuda", "vulkan", "rocm"]);
if (!GPU_TYPES.has(values.gpu!)) {
  console.error(`[gen-sync-compose] invalid --gpu "${values.gpu}" (expected none|nvidia|amd|amd-rocm)`);
  process.exit(1);
}
if (!WHISPER_BACKENDS.has(values["whisper-backend"]!)) {
  console.error(
    `[gen-sync-compose] invalid --whisper-backend "${values["whisper-backend"]}" (expected cpu|cuda|vulkan|rocm)`,
  );
  process.exit(1);
}

// Dynamic import by absolute file URL so the admin source resolves regardless of
// where this script file physically lives.
const genUrl = pathToFileURL(
  resolve(adminDir, "src/services/generators/compose-generator.ts"),
).href;
const regUrl = pathToFileURL(
  resolve(adminDir, "src/services/generators/service-registry.ts"),
).href;

const { generateCompose, getAllEnabledServices } = await import(genUrl);
const { parseRegistry } = await import(regUrl);

const registry = parseRegistry(
  JSON.parse(
    readFileSync(resolve(adminDir, "src/data/service-registry.json"), "utf-8"),
  ),
);

const enabledModules = values
  .modules!.split(",")
  .map((m: string) => m.trim())
  .filter(Boolean);

// Deterministic, well-formed placeholder secrets — same shape the installer's
// gen-export-compose uses. They only need to be valid for `docker compose
// config`/up; the CI override supplies the model-backend keys that matter.
const secrets: Record<string, string> = {
  AUTH_SECRET_KEY: "a".repeat(64),
  JARVIS_CONFIG_ADMIN_TOKEN: "b".repeat(64),
  JARVIS_AUTH_ADMIN_TOKEN: "c".repeat(64),
  ADMIN_API_KEY: "d".repeat(64),
  POSTGRES_PASSWORD: "e".repeat(32),
  REDIS_PASSWORD: "f".repeat(32),
};

// A minimally-complete WizardState for a Linux/CPU reconcile (matches the
// harness: GPU-less runner, all recommended modules). Mirrors the admin test's
// makeState defaults. Typed loosely to avoid coupling to the admin type path.
const state = {
  currentStep: 0,
  totalSteps: 7,
  enabledModules,
  portOverrides: {},
  infraPortOverrides: {},
  secrets,
  dbUser: "jarvis",
  whisperModel: "base.en",
  whisperModelPath: "/whisper-models/ggml-base.en.bin",
  whisperBackend: values["whisper-backend"],
  llmInterface: "JarvisToolModel",
  deploymentMode: "local",
  deploymentTarget: "standard",
  remoteLlmUrl: "",
  remoteWhisperUrl: "",
  platform: "linux",
  // This MUST be a concrete hardware object with an explicit gpuType, not
  // `null`. The admin generator treats absent hardware as a legacy install and
  // defaults to nvidia (`const gpuType = detected ?? "nvidia"` in
  // compose-generator.ts), which emits a `deploy.resources.reservations.devices`
  // nvidia block on the GPU-required services (llm-proxy + worker). The env-only
  // CI override can't strip a deploy block, so on a GPU-less runner the sync
  // bring-up dies with "could not select device driver nvidia". The default
  // `--gpu none` makes generateCompose omit the block — mirroring the installer
  // lane's `--gpu none`; the GPU install-e2e lanes pass the lane's real type.
  hardware: {
    platform: "linux",
    arch: "x86_64",
    totalMemoryGb: 16,
    gpuName: null,
    gpuVramMb: null,
    gpuType: values.gpu,
    recommendedBackends: ["REST"],
    recommendedBackend: "REST",
  },
  releaseTrack: "stable",
  relayEnabled: false,
  relayUrl: "",
  nativeServices: [],
};

writeFileSync(values.out!, generateCompose(state, registry));

if (values.bundle) {
  // Standard-mode compose uses ${VAR} refs, so the live lane needs a .env +
  // init-db.sh next to it (same trio gen-export-compose --mode standard emits).
  const outDir = dirname(resolve(values.out!));
  const { generateEnv } = await import(
    pathToFileURL(
      resolve(adminDir, "src/services/generators/env-generator.ts"),
    ).href
  );
  const { generateInitDbScript } = await import(
    pathToFileURL(
      resolve(adminDir, "src/services/generators/init-db-generator.ts"),
    ).href
  );
  writeFileSync(join(outDir, ".env"), generateEnv(state, registry));
  const initDb = join(outDir, "init-db.sh");
  writeFileSync(
    initDb,
    generateInitDbScript(getAllEnabledServices(state, registry), "jarvis_config"),
  );
  chmodSync(initDb, 0o755);
}

console.error(
  `[gen-sync-compose] admin SYNC compose → ${values.out} — modules=[${enabledModules.join(", ")}]` +
    ` gpu=${values.gpu} whisper=${values["whisper-backend"]}` +
    (values.bundle ? " (+ .env + init-db.sh)" : ""),
);
