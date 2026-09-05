import { Injectable, signal } from '@angular/core';
import { RuntimeConfig } from './models/api.models';

const defaultConfig: RuntimeConfig = {
  apiBaseUrl: 'http://127.0.0.1:8000/api',
  assetsBaseUrl: '/assets/images',
  terminalCode: 'POS01',
  tenantName: 'Brew Haven – RS Puram',
  tenantCode: 'BHV-RSP',
  environment: 'development',
};

@Injectable({ providedIn: 'root' })
export class RuntimeConfigService {
  readonly config = signal<RuntimeConfig>(defaultConfig);

  async load(): Promise<void> {
    try {
      const response = await fetch('./runtime-config.json', { cache: 'no-store' });
      if (!response.ok)
        throw new Error(`Runtime configuration request failed (${response.status})`);
      this.config.set({ ...defaultConfig, ...((await response.json()) as Partial<RuntimeConfig>) });
    } catch (error) {
      console.warn('Using built-in BrewBill runtime configuration.', error);
    }
  }

  apiUrl(path: string): string {
    return `${this.config().apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  }

  assetUrl(path: string | null): string {
    if (!path) return `${this.config().assetsBaseUrl.replace(/\/$/, '')}/products/placeholder.svg`;
    if (/^https?:\/\//i.test(path)) return path;
    return `${this.config().assetsBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  }
}
