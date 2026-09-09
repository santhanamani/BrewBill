import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { ShellComponent } from './features/shell/shell.component';
import { SessionService } from './core/session.service';

const authenticated: CanActivateFn = () => {
  const session = inject(SessionService);
  return session.isAuthenticated() || inject(Router).createUrlTree(['/login']);
};

const superAdmin: CanActivateFn = () => {
  const session = inject(SessionService);
  return session.isSuperAdmin() || inject(Router).createUrlTree(['/dashboard']);
};

const operationalUser: CanActivateFn = () => {
  const session = inject(SessionService);
  return !session.isSuperAdmin() || inject(Router).createUrlTree(['/administration']);
};

const ultraOperationalUser: CanActivateFn = () => {
  const session = inject(SessionService);
  return !session.isSuperAdmin() && session.context()?.plan_code === 'ULTRA_PROFESSIONAL'
    ? true
    : inject(Router).createUrlTree(['/dashboard']);
};

const landing: CanActivateFn = () => {
  const session = inject(SessionService);
  return inject(Router).createUrlTree([session.isSuperAdmin() ? '/administration' : '/dashboard']);
};

export const routes: Routes = [
  {
    path: 'subscribe',
    loadComponent: () =>
      import('./features/subscription/subscription.component').then((module) => module.SubscriptionComponent),
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/login/login.component').then((module) => module.LoginComponent),
  },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authenticated],
    children: [
      {
        path: 'dashboard',
        canActivate: [operationalUser],
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(
            (module) => module.DashboardComponent,
          ),
      },
      {
        path: 'pos',
        canActivate: [operationalUser],
        loadComponent: () =>
          import('./features/pos/pos.component').then((module) => module.PosComponent),
      },
      {
        path: 'marketplace',
        canActivate: [ultraOperationalUser],
        loadComponent: () => import('./features/marketplace/marketplace.component').then(module => module.MarketplaceComponent),
      },
      {
        path: 'products',
        canActivate: [operationalUser],
        loadComponent: () =>
          import('./features/products/products.component').then(
            (module) => module.ProductsComponent,
          ),
      },
      {
        path: 'administration',
        canActivate: [superAdmin],
        loadComponent: () =>
          import('./features/administration/administration.component').then(
            (module) => module.AdministrationComponent,
          ),
      },
      {
        path: 'operations/:module',
        canActivate: [operationalUser],
        loadComponent: () =>
          import('./features/operations/operations.component').then(
            (module) => module.OperationsComponent,
          ),
      },
      {
        path: 'management/:module',
        canActivate: [operationalUser],
        loadComponent: () =>
          import('./features/management/management.component').then(
            (module) => module.ManagementComponent,
          ),
      },
      { path: '', pathMatch: 'full', canActivate: [landing], children: [] },
    ],
  },
  { path: '**', redirectTo: '' },
];
