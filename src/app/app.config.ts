import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { RuntimeConfigService } from './core/runtime-config.service';
import { provideEchartsCore } from 'ngx-echarts';
import { authInterceptor } from './core/auth.interceptor';
import { SessionService } from './core/session.service';

async function loadEcharts() {
  const [echarts, charts, components, renderers] = await Promise.all([
    import('echarts/core'),
    import('echarts/charts'),
    import('echarts/components'),
    import('echarts/renderers'),
  ]);
  echarts.use([
    charts.LineChart,
    charts.PieChart,
    components.GridComponent,
    components.LegendComponent,
    components.TooltipComponent,
    renderers.CanvasRenderer,
  ]);
  return echarts;
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideRouter(routes),
    provideEchartsCore({ echarts: loadEcharts }),
    provideAppInitializer(() => {
      const runtime=inject(RuntimeConfigService),session=inject(SessionService);
      // Routing starts only after credentials and current tenant/outlet are verified.
      return runtime.load().then(()=>session.restore());
    }),
  ],
};
