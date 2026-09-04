import { Injectable, inject, signal } from '@angular/core';

import { RuntimeConfigService } from './runtime-config.service';

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

@Injectable({ providedIn: 'root' })
export class AuthTokenStoreService {
  private readonly runtime = inject(RuntimeConfigService);
  readonly accessToken = signal<string | null>(null);
  readonly refreshToken = signal<string | null>(null);
  private refreshInFlight: Promise<string> | null = null;

  set(tokens: TokenPair): void {
    this.accessToken.set(tokens.access_token);
    this.refreshToken.set(tokens.refresh_token);
  }

  clear(): void {
    this.accessToken.set(null);
    this.refreshToken.set(null);
  }

  refresh(): Promise<string> {
    if (this.refreshInFlight) return this.refreshInFlight;
    const refreshToken = this.refreshToken();
    if (!refreshToken) return Promise.reject(new Error('Your session has expired. Sign in again.'));

    this.refreshInFlight = fetch(this.runtime.apiUrl('/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail.detail ?? 'Your session has expired. Sign in again.');
        }
        const tokens = (await response.json()) as TokenPair;
        this.set(tokens);
        return tokens.access_token;
      })
      .catch((error) => {
        this.clear();
        throw error;
      })
      .finally(() => {
        this.refreshInFlight = null;
      });
    return this.refreshInFlight;
  }
}
