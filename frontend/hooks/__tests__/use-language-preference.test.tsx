import { renderHook, act } from '@testing-library/react'
import { useLanguagePreference } from '../use-language-preference'

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock
})

describe('useLanguagePreference', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.getItem.mockReturnValue(null)
  })

  it('should initialize with default language (zh)', () => {
    const { result } = renderHook(() => useLanguagePreference('student'))

    expect(result.current.locale).toBe('zh')
  })

  it('should initialize with saved language preference', () => {
    localStorageMock.getItem.mockReturnValue('en')

    const { result } = renderHook(() => useLanguagePreference('student'))

    expect(result.current.locale).toBe('en')
    expect(localStorageMock.getItem).toHaveBeenCalledWith('scholarship-system-language')
  })

  it('should change language and save to localStorage', () => {
    const { result } = renderHook(() => useLanguagePreference('student'))

    act(() => {
      result.current.changeLocale('en')
    })

    expect(result.current.locale).toBe('en')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('scholarship-system-language', 'en')
  })

  it('should change between languages', () => {
    const { result } = renderHook(() => useLanguagePreference('student'))

    // Start with 'zh'
    expect(result.current.locale).toBe('zh')

    act(() => {
      result.current.changeLocale('en')
    })

    expect(result.current.locale).toBe('en')

    act(() => {
      result.current.changeLocale('zh')
    })

    expect(result.current.locale).toBe('zh')
  })

  it('should handle invalid saved language preference', () => {
    localStorageMock.getItem.mockReturnValue('invalid_locale')

    const { result } = renderHook(() => useLanguagePreference('student'))

    // Should fall back to stored value or default
    expect(result.current.locale).toBe('invalid_locale')
  })

  it('should provide language switch enabled flag', () => {
    const { result } = renderHook(() => useLanguagePreference('student'))

    expect(typeof result.current.isLanguageSwitchEnabled).toBe('boolean')
    expect(result.current.isLanguageSwitchEnabled).toBe(true)
  })

  it('should disable language preference for non-student roles', () => {
    const { result } = renderHook(() => useLanguagePreference('admin'))

    expect(result.current.locale).toBe('zh')
    expect(result.current.isLanguageSwitchEnabled).toBe(false)

    act(() => {
      result.current.changeLocale('en')
    })

    // Language should not change for non-student roles
    expect(result.current.locale).toBe('zh')
  })
})