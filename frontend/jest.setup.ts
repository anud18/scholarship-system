import '@testing-library/jest-dom'
import React from 'react'

// Make React available globally
global.React = React

// Set up environment variables
// @ts-ignore - Allow NODE_ENV assignment in test environment
process.env.NODE_ENV = 'test'
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000'
process.env.NEXTAUTH_SECRET = 'test-secret'
process.env.NEXTAUTH_URL = 'http://localhost:3000'

// Load environment setup
require('./jest.env.js')

// Mock Next.js router
jest.mock('next/router', () => ({
  useRouter() {
    return {
      route: '/',
      pathname: '/',
      query: {},
      asPath: '/',
      push: jest.fn(() => Promise.resolve(true)),
      replace: jest.fn(() => Promise.resolve(true)),
      reload: jest.fn(),
      back: jest.fn(),
      prefetch: jest.fn(() => Promise.resolve()),
      beforePopState: jest.fn(),
      events: {
        on: jest.fn(),
        off: jest.fn(),
        emit: jest.fn(),
      },
      isFallback: false,
      isLocaleDomain: true,
      isReady: true,
      defaultLocale: 'en',
      domainLocales: [],
      isPreview: false,
    }
  },
}))

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
      refresh: jest.fn(),
    }
  },
  useSearchParams() {
    return new URLSearchParams()
  },
  usePathname() {
    return '/'
  },
}))

// Mock Next.js Image component
jest.mock('next/image', () => ({
  __esModule: true,
  default: function MockImage(props: any) {
    // eslint-disable-next-line jsx-a11y/alt-text
    return require('react').createElement('img', props)
  },
}))

// API mocking is handled by __mocks__ directory structure
// Individual test files can override specific mocks as needed

// Suppress React act warnings and test API errors from test scenarios
const originalError = console.error
beforeAll(() => {
  console.error = (...args: any[]) => {
    if (
      args[0] &&
      typeof args[0] === 'string' &&
      (
        (args[0].includes('Warning: An update to') && args[0].includes('act(...)')) ||
        args[0].includes('@radix-ui') ||
        args[0].includes('not wrapped in act') ||
        args[0].includes('API request failed') || // Suppress intentional test API errors
        args[0].includes('The above error occurred in the <TestComponent> component') ||
        args[0].includes('Consider adding an error boundary')
      )
    ) {
      return
    }
    // Don't suppress errors that are part of test assertions
    if (args[0] && typeof args[0] === 'string' && args[0].includes('useAuth must be used within AuthProvider')) {
      return
    }
    originalError.call(console, ...args)
  }
})

afterAll(() => {
  console.error = originalError
})

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  root = null
  rootMargin = ""
  thresholds = []
  disconnect() {}
  observe() {}
  unobserve() {}
  takeRecords() { return [] }
} as any

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
}

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

// Mock window.scrollTo
global.scrollTo = jest.fn()

// Deterministic localStorage for Node - stable across tests
const localStorageStore = new Map<string, string>()
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: (key: string) => (localStorageStore.has(key) ? localStorageStore.get(key)! : null),
    setItem: (key: string, value: string) => { localStorageStore.set(key, String(value)) },
    removeItem: (key: string) => { localStorageStore.delete(key) },
    clear: () => { localStorageStore.clear() },
    length: 0,
    key: jest.fn(),
  },
  writable: true,
})

// Minimal default fetch mock; tests can override per-case
global.fetch = jest.fn(async () => {
  const body = JSON.stringify([])
  const headers = new Map([['content-type', 'application/json']])
  return Promise.resolve({
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: {
      get: (key: string) => headers.get(key.toLowerCase()) ?? null,
      has: (key: string) => headers.has(key.toLowerCase()),
      forEach: (callback: (value: string, key: string) => void) => headers.forEach(callback),
    },
    json: async () => JSON.parse(body),
    text: async () => body,
  })
}) as jest.Mock
