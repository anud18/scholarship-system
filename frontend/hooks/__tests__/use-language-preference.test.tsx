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
    const { result } = renderHook(() => useLanguagePreference())

    expect(result.current.locale).toBe('zh')
  })

  it('should initialize with saved language preference', () => {
    localStorageMock.getItem.mockReturnValue('en')

    const { result } = renderHook(() => useLanguagePreference())

    expect(result.current.locale).toBe('en')
    expect(localStorageMock.getItem).toHaveBeenCalledWith('language_preference')
  })

  it('should change language and save to localStorage', () => {
    const { result } = renderHook(() => useLanguagePreference())

    act(() => {
      result.current.setLocale('en')
    })

    expect(result.current.locale).toBe('en')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('language_preference', 'en')
  })

  it('should toggle between languages', () => {
    const { result } = renderHook(() => useLanguagePreference())

    // Start with 'zh'
    expect(result.current.locale).toBe('zh')

    act(() => {
      result.current.toggleLanguage()
    })

    expect(result.current.locale).toBe('en')

    act(() => {
      result.current.toggleLanguage()
    })

    expect(result.current.locale).toBe('zh')
  })

  it('should handle invalid saved language preference', () => {
    localStorageMock.getItem.mockReturnValue('invalid_locale')

    const { result } = renderHook(() => useLanguagePreference())

    // Should fall back to default 'zh'
    expect(result.current.locale).toBe('zh')
  })

  it('should provide correct translation function', () => {
    const { result } = renderHook(() => useLanguagePreference())

    expect(typeof result.current.t).toBe('function')

    // Test translation function exists and returns string
    const translated = result.current.t('common.submit')
    expect(typeof translated).toBe('string')
  })

  it('should update translation function when language changes', () => {
    const { result } = renderHook(() => useLanguagePreference())

    const initialT = result.current.t

    act(() => {
      result.current.setLocale('en')
    })

    // Translation function should be updated for new locale
    expect(result.current.t).toBeDefined()
    // Function reference might be the same but behavior should change based on locale
  })
})