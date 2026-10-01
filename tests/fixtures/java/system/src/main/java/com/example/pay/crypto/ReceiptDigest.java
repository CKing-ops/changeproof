package com.example.pay.crypto;

import java.security.MessageDigest;

/** Synthetic: fingerprint of a receipt for the audit trail. */
public final class ReceiptDigest {
    private ReceiptDigest() {
    }

    public static byte[] of(byte[] receipt) throws Exception {
        return MessageDigest.getInstance("SHA-384").digest(receipt);
    }
}
