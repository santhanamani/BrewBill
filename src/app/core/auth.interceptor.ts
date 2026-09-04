import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthTokenStoreService } from './auth-token-store.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const tokens = inject(AuthTokenStoreService);
  const isAuthRequest = /\/auth\/(login|refresh|logout)$/.test(request.url);
  const accessToken = tokens.accessToken();
  const authenticatedRequest =
    !isAuthRequest && accessToken
      ? request.clone({ setHeaders: { Authorization: `Bearer ${accessToken}` } })
      : request;

  return next(authenticatedRequest).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401 || isAuthRequest) {
        return throwError(() => error);
      }
      return from(tokens.refresh()).pipe(
        switchMap((newToken) =>
          next(request.clone({ setHeaders: { Authorization: `Bearer ${newToken}` } })),
        ),
        catchError((refreshError) => throwError(() => refreshError)),
      );
    }),
  );
};
