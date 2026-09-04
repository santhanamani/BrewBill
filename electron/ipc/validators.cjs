const { z } = require('zod');

const receiptSchema = z.object({
  cafeName: z.string().min(1).max(120),
  address: z.string().max(300),
  invoiceNumber: z.string().min(1).max(100),
  cashier: z.string().min(1).max(120),
  items: z
    .array(
      z.object({
        name: z.string().min(1).max(180),
        quantity: z.number().int().positive().max(999),
        amountMinor: z.number().int().nonnegative(),
      }),
    )
    .min(1)
    .max(100),
  subtotalMinor: z.number().int().nonnegative(),
  discountMinor: z.number().int().nonnegative().default(0),
  taxMinor: z.number().int().nonnegative(),
  roundOffMinor: z.number().int().default(0),
  grandTotalMinor: z.number().int().positive(),
  paymentMode: z.enum(['CASH', 'UPI', 'CARD', 'SPLIT']),
  orderType: z.enum(['DIRECT', 'KOT', 'TAKEAWAY']).default('DIRECT'),
  serviceReference: z.string().max(80).nullable().default(null),
});

function parse(schema, value) {
  return schema.parse(value);
}

module.exports = {
  receiptSchema,
  parse,
};
