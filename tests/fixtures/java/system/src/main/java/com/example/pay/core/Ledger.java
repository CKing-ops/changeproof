package com.example.pay.core;

import java.util.ArrayList;
import java.util.List;

/** Synthetic: in-memory ledger of posted amounts. */
public class Ledger {
    private final List<Long> entries = new ArrayList<>();

    public void post(long amount) {
        entries.add(amount);
    }

    public long total() {
        long sum = 0;
        for (long entry : entries) {
            sum += entry;
        }
        return sum;
    }
}
