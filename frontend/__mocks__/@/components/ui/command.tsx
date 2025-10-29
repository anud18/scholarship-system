import React from "react";

export const Command = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="command">{children}</div>
);

export const CommandInput = (props: any) => (
  <input data-testid="command-input" {...props} />
);

export const CommandList = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="command-list">{children}</div>
);

export const CommandEmpty = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="command-empty">{children}</div>
);

export const CommandGroup = ({ children }: { children: React.ReactNode }) => (
  <div data-testid="command-group">{children}</div>
);

export const CommandItem = ({ children, onSelect, ...props }: any) => (
  <div data-testid="command-item" onClick={onSelect} {...props}>
    {children}
  </div>
);
