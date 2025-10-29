const { TextEncoder, TextDecoder } = require("util");

// Polyfills for jsdom environment
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock URL.createObjectURL if not available
if (typeof global.URL.createObjectURL === "undefined") {
  global.URL.createObjectURL = jest.fn(() => "mock-url");
}

// Mock File API
if (typeof global.File === "undefined") {
  global.File = class MockFile {
    constructor(chunks, filename, options) {
      this.name = filename;
      this.size = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
      this.type = options?.type || "";
    }
  };
}

// Mock Blob API
if (typeof global.Blob === "undefined") {
  global.Blob = class MockBlob {
    constructor(chunks, options) {
      this.size = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
      this.type = options?.type || "";
    }
  };
}

module.exports = {};
