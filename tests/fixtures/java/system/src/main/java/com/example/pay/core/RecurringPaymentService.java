package com.example.pay.core;

import com.example.pay.crypto.ReceiptSigner;

/** Synthetic: a payment taken on a schedule. */
public class RecurringPaymentService extends PaymentService {
    public RecurringPaymentService(Ledger ledger, ReceiptSigner signer) {
        super(ledger, signer);
    }

    public byte[] payMonthly(Payment payment) throws Exception {
        return pay(payment);
    }
}
