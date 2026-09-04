export {};

declare global {
  interface Window {
    brewBill?: {
      app: {
        status: () => Promise<{ name: string; cloudOnly: boolean; deviceStoreReady: boolean }>;
      };
      license: {
        status: () => Promise<{
          state: string;
          canCreateBills: boolean;
          offlineValidUntil: string | null;
          message: string;
        }>;
        identity: () => Promise<{ installationId: string; terminalCode: string }>;
        install: (envelope: {
          payload: Record<string, unknown>;
          signature: string;
          public_key: string;
        }) => Promise<{
          state: string;
          canCreateBills: boolean;
          offlineValidUntil: string | null;
          message: string;
        }>;
      };
      settings: {
        get: (key: string) => Promise<string | null>;
        set: (key: string, value: string) => Promise<void>;
      };
      secure: {
        store: (key: string, value: string) => Promise<void>;
        read: (key: string) => Promise<string | null>;
      };
      printer: {
        list: () => Promise<Array<{ name: string; displayName: string; isDefault: boolean }>>;
        printReceipt: (
          receipt: {
            cafeName: string;
            address: string;
            invoiceNumber: string;
            cashier: string;
            items: Array<{ name: string; quantity: number; amountMinor: number }>;
            subtotalMinor: number;
            discountMinor: number;
            taxMinor: number;
            roundOffMinor: number;
            grandTotalMinor: number;
            paymentMode: 'CASH' | 'UPI' | 'CARD' | 'SPLIT';
            orderType: 'DIRECT' | 'KOT' | 'TAKEAWAY';
            serviceReference: string | null;
          },
          printerName?: string,
        ) => Promise<{ success: boolean }>;
      };
      payment: {
        status: () => Promise<{ connected: boolean; provider: string; message: string }>;
        collect: (request: {
          mode: 'UPI' | 'CARD';
          amountMinor: number;
          invoiceHint: string;
        }) => Promise<{
          status: 'APPROVED' | 'DECLINED' | 'UNAVAILABLE';
          provider: string;
          reference: string | null;
          message: string;
        }>;
      };
    };
  }
}
