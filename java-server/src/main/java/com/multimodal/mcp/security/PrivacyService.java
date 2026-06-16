package com.multimodal.mcp.security;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Service;

import com.multimodal.mcp.util.Env;

/**
 * PII scanning and AES-GCM encryption (Fernet-like symmetric encryption for Java).
 * Port of Python privacy tools in {@code server_app.py}.
 */
@Service
public class PrivacyService {

    public static final String ENCRYPTION_KEY_ENV = "MCP_ENCRYPTION_KEY";
    private static final int GCM_TAG_LENGTH_BITS = 128;
    private static final int GCM_IV_LENGTH_BYTES = 12;

    private static final Map<String, Pattern> PII_PATTERNS = Map.of(
            "ssn", Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b"),
            "email",
                    Pattern.compile(
                            "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
                            Pattern.CASE_INSENSITIVE),
            "phone", Pattern.compile("\\b\\d{3}-\\d{3}-\\d{4}\\b"),
            "credit_card", Pattern.compile("\\b\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}\\b"));

    private final SecureRandom secureRandom = new SecureRandom();

    public Map<String, Object> scanForPii(String textContent) {
        Map<String, Integer> findings = new LinkedHashMap<>();
        for (Map.Entry<String, Pattern> entry : PII_PATTERNS.entrySet()) {
            Matcher matcher = entry.getValue().matcher(textContent);
            int count = 0;
            while (matcher.find()) {
                count++;
            }
            if (count > 0) {
                findings.put(entry.getKey(), count);
            }
        }

        if (findings.isEmpty()) {
            return Map.of("pii_found", false, "findings", Map.of());
        }

        String sanitized = textContent;
        for (Map.Entry<String, Pattern> entry : PII_PATTERNS.entrySet()) {
            if (findings.containsKey(entry.getKey())) {
                sanitized = entry.getValue().matcher(sanitized).replaceAll("[REDACTED_" + entry.getKey().toUpperCase() + "]");
            }
        }

        Map<String, Object> result = new HashMap<>();
        result.put("pii_found", true);
        result.put("findings", findings);
        result.put("sanitized_text", sanitized);
        return result;
    }

    public Map<String, Object> encryptSensitiveData(String dataContent) {
        try {
            byte[] key = resolveEncryptionKey();
            byte[] iv = new byte[GCM_IV_LENGTH_BYTES];
            secureRandom.nextBytes(iv);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv));
            byte[] ciphertext = cipher.doFinal(dataContent.getBytes(StandardCharsets.UTF_8));

            byte[] combined = new byte[iv.length + ciphertext.length];
            System.arraycopy(iv, 0, combined, 0, iv.length);
            System.arraycopy(ciphertext, 0, combined, iv.length, ciphertext.length);

            String encryptedB64 = Base64.getUrlEncoder().withoutPadding().encodeToString(combined);
            return Map.of("encrypted", encryptedB64, "length", combined.length);
        } catch (Exception e) {
            throw new IllegalStateException("Encryption failed: " + e.getMessage(), e);
        }
    }

    private byte[] resolveEncryptionKey() {
        String key = Env.get(ENCRYPTION_KEY_ENV);
        if (key.isEmpty()) {
            byte[] generated = new byte[32];
            secureRandom.nextBytes(generated);
            return generated;
        }
        byte[] decoded;
        try {
            decoded = Base64.getDecoder().decode(key);
        } catch (IllegalArgumentException e) {
            decoded = key.getBytes(StandardCharsets.UTF_8);
        }
        if (decoded.length == 32) {
            return decoded;
        }
        byte[] normalized = new byte[32];
        System.arraycopy(decoded, 0, normalized, 0, Math.min(decoded.length, 32));
        return normalized;
    }
}
