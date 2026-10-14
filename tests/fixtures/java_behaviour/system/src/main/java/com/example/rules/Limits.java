package com.example.rules;

/** Synthetic: payment limits. */
public final class Limits {
    private Limits() {
    }

    public static int clamp(int value, int low, int high) {
        if (value < low) {
            return low;
        }
        if (value > high) {
            return high;
        }
        return value;
    }

    public static boolean overLimit(long amount) {
        return amount > 50000;
    }
}
