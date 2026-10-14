package com.example.rules;

/** Synthetic: settlement calendar rules. */
public final class Calendar {
    private Calendar() {
    }

    public static boolean isLeap(int year) {
        return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    }
}
