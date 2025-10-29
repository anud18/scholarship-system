import React from "react";

export const Popover = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="popover">{children}</div>
);

export const PopoverContent = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="popover-content">{children}</div>
);

export const PopoverTrigger = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="popover-trigger">{children}</div>
);
