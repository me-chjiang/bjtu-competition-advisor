export const delay = (ms = 300) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export const clone = <T>(value: T): T => structuredClone(value);
