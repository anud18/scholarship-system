import { useEffect, useState } from 'react'

/**
 * Hook to check if component is mounted on client side
 * Useful for preventing SSR mismatches with useLayoutEffect
 */
export function useIsMounted() {
  const [isMounted, setIsMounted] = useState(false)

  useEffect(() => {
    setIsMounted(true)
  }, [])

  return isMounted
}