// TypeScript declarations for Jest mocks
declare namespace jest {
  interface Mock<T = any, Y extends any[] = any[]> {
    mockResolvedValue(value: T): this;
    mockResolvedValueOnce(value: T): this;
    mockRejectedValue(value: any): this;
    mockRejectedValueOnce(value: any): this;
    mockReturnValue(value: T): this;
    mockReturnValueOnce(value: T): this;
    mockImplementation(fn: (...args: Y) => T): this;
    mockImplementationOnce(fn: (...args: Y) => T): this;
    mockClear(): this;
    mockReset(): this;
    mockRestore(): void;
  }
}

// Extend the global jest interface
declare global {
  namespace jest {
    interface Matchers<R> {
      toHaveBeenCalled(): R;
      toHaveBeenCalledWith(...args: any[]): R;
      toHaveBeenCalledTimes(expected: number): R;
    }
  }
}
