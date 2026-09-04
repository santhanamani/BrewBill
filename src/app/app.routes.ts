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

export const routes: Routes = [
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
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(
            (module) => module.DashboardComponent,
          ),
      },
      {
        path: 'pos',
        loadComponent: () =>
          import('./features/pos/pos.component').then((module) => module.PosComponent),
      },
      {
        path: 'products',
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
        loadComponent: () =>
          import('./features/operations/operations.component').then(
            (module) => module.OperationsComponent,
          ),
      },
      {
        path: 'management/:module',
        loadComponent: () =>
          import('./features/management/management.component').then(
            (module) => module.ManagementComponent,
          ),
      },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },
  { path: '**', redirectTo: '' },
];
