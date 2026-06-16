package com.multimodal.mcp.mcp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.multimodal.mcp.core.RuntimeState;

import io.modelcontextprotocol.server.McpServerFeatures;
import io.modelcontextprotocol.spec.McpSchema;

/**
 * Registers the {@code validated://{validation_id}} MCP resource template.
 */
@Component
public class McpResourceRegistry {

    private final RuntimeState runtimeState;

    public McpResourceRegistry(RuntimeState runtimeState) {
        this.runtimeState = runtimeState;
    }

    public List<McpServerFeatures.SyncResourceTemplateSpecification> buildResourceTemplateSpecifications() {
        return List.of(new McpServerFeatures.SyncResourceTemplateSpecification(
                McpSchema.ResourceTemplate.builder()
                        .uriTemplate("validated://{validation_id}")
                        .name("validated-file")
                        .description("Files that passed validate_file")
                        .mimeType("application/octet-stream")
                        .build(),
                (exchange, request) -> {
                    try {
                        return readValidatedFile(request.uri());
                    } catch (IOException e) {
                        throw new RuntimeException("Failed to read validated file", e);
                    }
                }));
    }

    private McpSchema.ReadResourceResult readValidatedFile(String uri) throws IOException {
        if (uri == null || !uri.startsWith("validated://")) {
            throw new IllegalArgumentException("Access denied: invalid validated URI");
        }
        String validationId = uri.substring("validated://".length());
        Map<String, Object> meta = runtimeState.getValidatedFiles().get(validationId);
        if (meta == null) {
            throw new IllegalArgumentException("Access denied: file not validated or unknown validation id");
        }

        Object filePathObj = meta.get("file_path");
        if (filePathObj == null) {
            throw new IllegalArgumentException("Access denied: missing file path metadata");
        }

        Path path = Path.of(String.valueOf(filePathObj));
        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException("Access denied: validated file no longer exists");
        }

        byte[] bytes = Files.readAllBytes(path);
        String mime = meta.get("mime") != null ? String.valueOf(meta.get("mime")) : "application/octet-stream";
        String blob = Base64.getEncoder().encodeToString(bytes);
        return new McpSchema.ReadResourceResult(List.of(new McpSchema.BlobResourceContents(uri, mime, blob)));
    }
}
