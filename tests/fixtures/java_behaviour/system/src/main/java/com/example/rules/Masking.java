package com.example.rules;

/** Synthetic: card number masking for statements. */
public final class Masking {
    private Masking() {
    }

    public static String mask(String card) {
        if (card == null || card.length() < 4) {
            return card;
        }
        return "*".repeat(card.length() - 4) + card.substring(card.length() - 4);
    }
}
