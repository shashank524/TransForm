package com.multimodal.mcp.config;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.fasterxml.jackson.databind.ObjectMapper;

import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.json.jackson2.JacksonMcpJsonMapper;
import io.modelcontextprotocol.server.McpServer;
import io.modelcontextprotocol.server.McpSyncServer;
import io.modelcontextprotocol.server.transport.HttpServletStreamableServerTransportProvider;
import io.modelcontextprotocol.spec.McpSchema.ServerCapabilities;

import com.multimodal.mcp.mcp.McpResourceRegistry;
import com.multimodal.mcp.mcp.McpToolRegistry;

/**
 * MCP sync server wiring at {@code /mcp} using Streamable HTTP servlet transport.
 * Mirrors Python {@code mcp.streamable_http_app(stateless_http=True)} mounting.
 */
@Configuration
public class McpServerConfiguration {

    @Bean
    public McpJsonMapper mcpJsonMapper(ObjectMapper objectMapper) {
        return new JacksonMcpJsonMapper(objectMapper);
    }

    @Bean
    public HttpServletStreamableServerTransportProvider mcpTransportProvider(McpJsonMapper mcpJsonMapper) {
        return HttpServletStreamableServerTransportProvider.builder()
                .jsonMapper(mcpJsonMapper)
                .mcpEndpoint("/mcp")
                .build();
    }

    @Bean
    public ServletRegistrationBean<HttpServletStreamableServerTransportProvider> mcpServletRegistration(
            HttpServletStreamableServerTransportProvider transportProvider) {
        ServletRegistrationBean<HttpServletStreamableServerTransportProvider> registration =
                new ServletRegistrationBean<>(transportProvider);
        registration.addUrlMappings("/mcp", "/mcp/*");
        registration.setName("mcpStreamableServlet");
        registration.setLoadOnStartup(1);
        return registration;
    }

    @Bean
    public McpSyncServer mcpSyncServer(
            HttpServletStreamableServerTransportProvider transportProvider,
            McpJsonMapper mcpJsonMapper,
            McpToolRegistry toolRegistry,
            McpResourceRegistry resourceRegistry) {
        var builder = McpServer.sync(transportProvider)
                .serverInfo("LargeOutputBenchmark", "1.0.0")
                .jsonMapper(mcpJsonMapper)
                .capabilities(ServerCapabilities.builder()
                        .resources(false, true)
                        .tools(true)
                        .build());

        for (var toolSpec : toolRegistry.buildToolSpecifications()) {
            builder.tools(toolSpec);
        }
        for (var resourceTemplate : resourceRegistry.buildResourceTemplateSpecifications()) {
            builder.resourceTemplates(resourceTemplate);
        }

        return builder.build();
    }
}
