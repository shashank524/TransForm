package com.multimodal.mcp.security;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;

import javax.crypto.SecretKey;

import org.springframework.stereotype.Service;

import com.multimodal.mcp.core.RuntimeState;
import com.multimodal.mcp.util.Env;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

/**
 * JWT session tokens for MCP auth tools. Port of Python auth section in {@code server_app.py}.
 */
@Service
public class AuthService {

    public static final String JWT_SECRET_ENV = "MCP_JWT_SECRET";
    public static final int SESSION_TTL_SECONDS = 3600;

    private final RuntimeState runtimeState;

    public AuthService(RuntimeState runtimeState) {
        this.runtimeState = runtimeState;
    }

    public boolean validateCredentials(String username, String credentials) {
        String envUser = Env.get("MCP_DEMO_USERNAME", "demo");
        String envPass = Env.get("MCP_DEMO_PASSWORD", "password");
        return envUser.equals(username) && envPass.equals(credentials);
    }

    public String createSessionToken(String username) {
        SecretKey key = getJwtSecretKey();
        Instant now = Instant.now();
        Instant exp = now.plusSeconds(SESSION_TTL_SECONDS);
        String token = Jwts.builder()
                .subject(username)
                .claim("username", username)
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .signWith(key)
                .compact();
        runtimeState.getActiveSessions().put(token, username);
        return token;
    }

    public boolean verifySessionToken(String token) {
        if (token == null || token.isBlank()) {
            return false;
        }
        if (!runtimeState.getActiveSessions().containsKey(token)) {
            return false;
        }
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(getJwtSecretKey())
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            Date exp = claims.getExpiration();
            return exp == null || exp.after(new Date());
        } catch (Exception e) {
            return false;
        }
    }

    public String getUsernameFromToken(String token) {
        return runtimeState.getActiveSessions().get(token);
    }

    public boolean checkResourcePermission(String username, String resource, String operation) {
        if (username == null) {
            return false;
        }
        if (username.equals(Env.get("MCP_DEMO_USERNAME", "demo"))) {
            return true;
        }
        return resource.startsWith("/public/") && "read".equals(operation);
    }

    public Map<String, Object> authenticate(String username, String credentials) {
        if (!validateCredentials(username, credentials)) {
            return Map.of("authenticated", false);
        }
        String token = createSessionToken(username);
        return Map.of("authenticated", true, "session_token", token);
    }

    public Map<String, Object> accessProtectedResource(String sessionToken, String resourcePath, String operation) {
        if (!verifySessionToken(sessionToken)) {
            return Map.of("authorized", false);
        }
        String username = getUsernameFromToken(sessionToken);
        if (username == null) {
            username = "<unknown>";
        }
        if (!checkResourcePermission(username, resourcePath, operation)) {
            return Map.of("authorized", false, "username", username);
        }
        return Map.of("authorized", true, "username", username);
    }

    private SecretKey getJwtSecretKey() {
        String secret = Env.get(JWT_SECRET_ENV);
        if (secret.isEmpty()) {
            throw new IllegalStateException(
                    JWT_SECRET_ENV + " is not set; configure a secret key to use auth tools.");
        }
        byte[] keyBytes = secret.getBytes(StandardCharsets.UTF_8);
        if (keyBytes.length < 32) {
            byte[] padded = new byte[32];
            System.arraycopy(keyBytes, 0, padded, 0, Math.min(keyBytes.length, 32));
            keyBytes = padded;
        }
        return Keys.hmacShaKeyFor(keyBytes);
    }
}
