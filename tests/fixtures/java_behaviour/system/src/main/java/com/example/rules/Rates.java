package com.example.rules;

/** Synthetic: fee bands and simple interest. */
public final class Rates {
    private Rates() {
    }

    public static int bandFor(long amount) {
        if (amount <= 1000) {
            return 1;
        }
        if (amount <= 10000) {
            return 2;
        }
        return 3;
    }

    public static long interest(long principal, int days) {
        return principal * 5 * days / 36500;
    }
}
