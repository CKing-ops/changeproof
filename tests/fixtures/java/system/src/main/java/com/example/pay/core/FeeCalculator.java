package com.example.pay.core;

/** Synthetic: card fee for a payment. */
public final class FeeCalculator {
    static final long RATE_BASIS_POINTS = 150;
    static final long MINIMUM_FEE = 25;

    private FeeCalculator() {
    }

    public static long fee(long amount) {
        long fee = amount * RATE_BASIS_POINTS / 10000;
        return Math.max(fee, MINIMUM_FEE);
    }

    public static long refundFee(long amount) {
        return MINIMUM_FEE;
    }
}
