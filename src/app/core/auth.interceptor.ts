import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthTokenStoreService } from './auth-token-store.service';
import { RuntimeConfigService } from './runtime-config.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const tokens = inject(AuthTokenStoreService);
  const runtime = inject(RuntimeConfigService);
  // Never attach credentials to image/CDN/other-origin requests.
  if(!request.url.startsWith(runtime.apiUrl('/')))return next(request);
  const isAuthRequest = /\/auth\//.test(request.url);
  const accessToken = tokens.accessToken();
  const authenticatedRequest =
    !isAuthRequest && accessToken && !request.headers.has('Authorization')
      ? request.clone({ setHeaders: { Authorization: `Bearer ${accessToken}` } })
      : request;

  return next(authenticatedRequest).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401 || isAuthRequest || !tokens.refreshToken()) {
        return throwError(() => error);
      }
      const current=tokens.accessToken();
      // Another concurrent request may already have renewed this old token.
      if(current && authenticatedRequest.headers.get('Authorization')!==`Bearer ${current}`)
        return next(request.clone({setHeaders:{Authorization:`Bearer ${current}`}}));
      return from(tokens.refresh()).pipe(
        switchMap((newToken) =>
          next(request.clone({ setHeaders: { Authorization: `Bearer ${newToken}` } })),
        ),
        catchError((refreshError) => throwError(() => refreshError)),
      );
    }),
  );
};
