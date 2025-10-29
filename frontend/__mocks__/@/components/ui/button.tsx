import React from "react";

export const Button = ({ children, onClick, variant, size, ...props }: any) => (
  <button
    data-testid="button"
    onClick={onClick}
    data-variant={variant}
    data-size={size}
    {...props}
  >
    {children}
  </button>
);
