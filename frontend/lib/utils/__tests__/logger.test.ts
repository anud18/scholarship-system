/**
 * Tests for `lib/utils/logger.ts`.
 *
 * Environment-aware logger. SECURITY contract:
 * - Development: full details to console (debugging aid)
 * - Production: silent (no console output) to prevent information
 *   leakage (e.g., user PII, stack traces, internal endpoints from
 *   accidentally landing in browser DevTools console where a screen-
 *   shared support call could expose them)
 *
 * Regression risks:
 * - Production accidentally calls console.error → information leak
 * - Development silently drops logs → debugging blind spot
 *
 * The Logger class reads `process.env.NODE_ENV` at construction time.
 * Tests instantiate a fresh Logger after setting NODE_ENV to exercise
 * both code paths.
 *
 * 10 cases.
 */

describe("Logger environment-aware behavior", () => {
  const originalNodeEnv = process.env.NODE_ENV;
  let consoleErrorSpy: jest.SpyInstance;
  let consoleWarnSpy: jest.SpyInstance;
  let consoleInfoSpy: jest.SpyInstance;
  let consoleDebugSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    consoleWarnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    consoleInfoSpy = jest.spyOn(console, "info").mockImplementation(() => {});
    consoleDebugSpy = jest.spyOn(console, "debug").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    consoleInfoSpy.mockRestore();
    consoleDebugSpy.mockRestore();
    // Restore NODE_ENV; setupModulesAfterEach to reset module registry
    // so `new Logger()` reads it again.
    (process.env as any).NODE_ENV = originalNodeEnv;
    jest.resetModules();
  });

  function loadLoggerWithEnv(nodeEnv: string) {
    (process.env as any).NODE_ENV = nodeEnv;
    jest.resetModules();
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require("../logger").logger as typeof import("../logger").logger;
  }

  describe("development mode (NODE_ENV=development)", () => {
    it("error() writes to console.error with [ERROR] prefix", () => {
      const logger = loadLoggerWithEnv("development");
      logger.error("Failed to fetch user", { userId: 42 });
      expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
      expect(consoleErrorSpy.mock.calls[0][0]).toContain("[ERROR]");
      expect(consoleErrorSpy.mock.calls[0][0]).toContain("Failed to fetch user");
    });

    it("warn() writes to console.warn with [WARN] prefix", () => {
      const logger = loadLoggerWithEnv("development");
      logger.warn("Deprecated API");
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
      expect(consoleWarnSpy.mock.calls[0][0]).toContain("[WARN]");
    });

    it("info() writes to console.info with [INFO] prefix", () => {
      const logger = loadLoggerWithEnv("development");
      logger.info("User logged in", { userId: 42 });
      expect(consoleInfoSpy).toHaveBeenCalledTimes(1);
      expect(consoleInfoSpy.mock.calls[0][0]).toContain("[INFO]");
    });

    it("debug() writes to console.debug with [DEBUG] prefix", () => {
      const logger = loadLoggerWithEnv("development");
      logger.debug("Cache hit");
      expect(consoleDebugSpy).toHaveBeenCalledTimes(1);
      expect(consoleDebugSpy.mock.calls[0][0]).toContain("[DEBUG]");
    });

    it("passes context through to console", () => {
      const logger = loadLoggerWithEnv("development");
      const ctx = { userId: 42, ip: "10.0.0.1" };
      logger.error("Auth failed", ctx);
      expect(consoleErrorSpy.mock.calls[0][1]).toBe(ctx);
    });

    it("substitutes empty string when context is undefined", () => {
      /** Without context, second arg is '' (not undefined) so the
       * console output is clean. Pin so a refactor doesn't accidentally
       * print '... undefined' lines. */
      const logger = loadLoggerWithEnv("development");
      logger.warn("No context");
      expect(consoleWarnSpy.mock.calls[0][1]).toBe("");
    });
  });

  describe("production mode (NODE_ENV=production)", () => {
    it("error() does NOT write to console (no info leak)", () => {
      /** SECURITY: zero console output in production. */
      const logger = loadLoggerWithEnv("production");
      logger.error("DB query failed", { sql: "SELECT * FROM users", host: "internal" });
      expect(consoleErrorSpy).not.toHaveBeenCalled();
    });

    it("warn() does NOT write to console", () => {
      const logger = loadLoggerWithEnv("production");
      logger.warn("Slow query");
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });

    it("info() does NOT write to console (silent in prod)", () => {
      /** Info is silent in prod — there's no `else { sendToExternalLogger }`
       * branch for info(). Pin so a refactor doesn't accidentally start
       * leaking info logs. */
      const logger = loadLoggerWithEnv("production");
      logger.info("User logged in");
      expect(consoleInfoSpy).not.toHaveBeenCalled();
    });

    it("debug() does NOT write to console (dev-only)", () => {
      const logger = loadLoggerWithEnv("production");
      logger.debug("Cache hit");
      expect(consoleDebugSpy).not.toHaveBeenCalled();
    });
  });
});
