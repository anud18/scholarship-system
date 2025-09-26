import React from 'react'

export const Badge = ({ children, variant, ...props }: any) => (
  <span
    data-testid="badge"
    data-variant={variant}
    {...props}
  >
    {children}
  </span>
)
