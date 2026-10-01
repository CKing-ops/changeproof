package com.example.pay.core;

import com.example.pay.crypto.ReceiptSigner;

/** Synthetic: takes a payment, charges the fee and signs a receipt. */
public class PaymentService {
    private final Ledger ledger;
    private final ReceiptSigner signer;

    public PaymentService(Ledger ledger, ReceiptSigner signer) {
        this.ledger = ledger;
        this.signer = signer;
    }

    public byte[] pay(Payment payment) throws Exception {
        long fee = FeeCalculator.fee(payment.amount());
        ledger.post(payment.amount() - fee);
        return signer.sign(payment.id());
    }

    public void refund(Payment payment) {
        ledger.post(-payment.amount() + FeeCalculator.refundFee(payment.amount()));
    }
}
