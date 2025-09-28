import React from "react";

export const Checkbox = ({ checked, onCheckedChange, ...props }: any) => (
  <input
    data-testid="checkbox"
    type="checkbox"
    checked={checked}
    onChange={e => onCheckedChange?.(e.target.checked)}
    {...props}
  />
);
