import { signal, WritableSignal } from '@angular/core';

/** A signal whose non-empty value is cleared after the requested delay. */
export function timedSignal(delayMs = 3000): WritableSignal<string> {
  const value = signal('');
  const write = value.set.bind(value);
  let timer: number | undefined;

  value.set = (next: string): void => {
    if (timer !== undefined) window.clearTimeout(timer);
    write(next);
    timer = next
      ? window.setTimeout(() => {
          write('');
          timer = undefined;
        }, delayMs)
      : undefined;
  };

  return value;
}
