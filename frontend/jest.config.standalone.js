// Standalone Jest configuration for CI compatibility
// Use this if the Next.js Jest configuration fails in CI

// const { pathsToModuleNameMapper } = require('ts-jest'); // No longer using for this test
// const { compilerOptions } = require('./tsconfig.json'); // No longer using for this test

module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],

  // Module name mapping - Only specific literal mappings, no generic fallback
  moduleNameMapper: {
    // CSS and static assets
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "\\.(jpg|jpeg|png|gif|eot|otf|webp|svg|ttf|woff|woff2|mp4|webm|wav|mp3|m4a|aac|oga)$":
      "jest-transform-stub",

    // Specific literal mappings only
    "^@/lib/api$": "<rootDir>/lib/api",
    "^@/lib/utils$": "<rootDir>/lib/utils",
    "^@/lib/validation$": "<rootDir>/lib/validation",
    "^@/lib/i18n$": "<rootDir>/lib/i18n",

    // Common component paths
    "^@/components/ui/card$": "<rootDir>/components/ui/card",
    "^@/components/ui/button$": "<rootDir>/components/ui/button",
    "^@/components/ui/input$": "<rootDir>/components/ui/input",
    "^@/components/ui/form$": "<rootDir>/components/ui/form",
    "^@/components/ui/label$": "<rootDir>/components/ui/label",
    "^@/components/ui/textarea$": "<rootDir>/components/ui/textarea",
    "^@/components/ui/select$": "<rootDir>/components/ui/select",
    "^@/components/ui/badge$": "<rootDir>/components/ui/badge",
    "^@/components/ui/tabs$": "<rootDir>/components/ui/tabs",
    "^@/components/ui/progress$": "<rootDir>/components/ui/progress",
    "^@/components/progress-timeline$":
      "<rootDir>/components/progress-timeline",
    "^@/components/file-upload$": "<rootDir>/components/file-upload",

    // Common hook paths
    "^@/hooks/use-auth$": "<rootDir>/hooks/use-auth",
    "^@/hooks/use-applications$": "<rootDir>/hooks/use-applications",
    "^@/hooks/use-toast$": "<rootDir>/hooks/use-toast",
  },

  // Module directories
  moduleDirectories: ["node_modules", "<rootDir>/"],

  // Module file extensions
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json", "node"],

  // Test configuration
  testMatch: [
    "<rootDir>/components/__tests__/**/*.{js,jsx,ts,tsx}",
    "<rootDir>/**/__tests__/**/*.{js,jsx,ts,tsx}",
    "<rootDir>/**/*.(test|spec).{js,jsx,ts,tsx}",
  ],

  testPathIgnorePatterns: [
    "<rootDir>/.next/",
    "<rootDir>/node_modules/",
    "<rootDir>/e2e/",
  ],

  // Transform configuration
  transform: {
    "^.+\\.(ts|tsx|js|jsx)$": "babel-jest",
  },

  // Coverage configuration
  collectCoverageFrom: [
    "**/*.{js,jsx,ts,tsx}",
    "!**/*.d.ts",
    "!**/node_modules/**",
    "!<rootDir>/.next/**",
    "!<rootDir>/e2e/**",
    "!<rootDir>/coverage/**",
    "!<rootDir>/playwright-report/**",
    "!<rootDir>/test-results/**",
    "!<rootDir>/*.config.*",
    "!<rootDir>/next.config.js",
  ],

  // Other settings
  clearMocks: true,
  automock: false,

  // Transform ignore patterns
  transformIgnorePatterns: ["node_modules/(?!(.*\\.mjs$))"],
};
