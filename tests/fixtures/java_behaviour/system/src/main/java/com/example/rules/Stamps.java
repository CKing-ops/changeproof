package com.example.rules;

import java.util.UUID;

/** Synthetic: values that differ on every run, so the probe must not call them different. */
public final class Stamps {
    private Stamps() {
    }

    public static long stamp() {
        return System.nanoTime();
    }

    public static String token() {
        return UUID.randomUUID().toString();
    }
}
