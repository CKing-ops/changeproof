package com.example.rules;

/** Synthetic: running count and sum of accepted amounts. */
public class Tally {
    private int count;
    private long sum;

    public void add(long amount) {
        if (amount > 0) {
            count++;
            sum += amount;
        }
    }

    public int count() {
        return count;
    }

    public long sum() {
        return sum;
    }
}
