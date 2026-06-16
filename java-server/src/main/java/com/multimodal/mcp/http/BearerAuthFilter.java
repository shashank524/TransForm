package com.multimodal.mcp.http;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.multimodal.mcp.util.Env;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * Validates Bearer token against {@code MCP_API_KEY}. Port of Python {@code BearerAuthMiddleware}.
 */
public class BearerAuthFilter extends OncePerRequestFilter {

    private final String expectedKey;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public BearerAuthFilter() {
        String raw = Env.get("MCP_API_KEY");
        this.expectedKey = raw.isEmpty() ? null : raw;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        if (expectedKey == null) {
            filterChain.doFilter(request, response);
            return;
        }

        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.regionMatches(true, 0, "Bearer ", 0, 7)) {
            sendUnauthorized(response, "Missing or invalid Authorization header");
            return;
        }

        String token = authHeader.substring(7).trim();
        if (!expectedKey.equals(token)) {
            sendUnauthorized(response, "Invalid API key");
            return;
        }

        filterChain.doFilter(request, response);
    }

    private void sendUnauthorized(HttpServletResponse response, String detail) throws IOException {
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("WWW-Authenticate", "Bearer realm=\"MCP\", error=\"invalid_token\"");
        objectMapper.writeValue(
                response.getOutputStream(),
                java.util.Map.of("error", "unauthorized", "detail", detail));
    }
}
