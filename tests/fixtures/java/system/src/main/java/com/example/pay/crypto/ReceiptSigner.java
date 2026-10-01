package com.example.pay.crypto;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

/** Synthetic: signs payment receipts. */
public class ReceiptSigner {
    private final KeyPair keys;

    public ReceiptSigner() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("ML-DSA");
        keys = generator.generateKeyPair();
    }

    public byte[] sign(String receipt) throws Exception {
        Signature signature = Signature.getInstance("ML-DSA");
        signature.initSign(keys.getPrivate());
        signature.update(receipt.getBytes(StandardCharsets.UTF_8));
        return signature.sign();
    }
}
