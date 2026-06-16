package com.multimodal.mcp.security;

import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.multimodal.mcp.core.RuntimeState;

/**
 * Blog-style file validation. Port of {@code _validate_file_locally} from {@code server/core/runtime.py}.
 */
@Service
public class FileValidationService {

    private final RuntimeState runtimeState;

    public FileValidationService(RuntimeState runtimeState) {
        this.runtimeState = runtimeState;
    }

    public Map<String, Object> validateFile(String filePath, String expectedType) {
        return runtimeState.validateFileLocally(filePath, expectedType, FileValidationService::detectMimeType);
    }

    public Map<String, Object> validateAndRegister(String filePath, String expectedType) {
        Map<String, Object> result = validateFile(filePath, expectedType);
        if (!Boolean.TRUE.equals(result.get("valid"))) {
            return result;
        }

        String validationId = UUID.randomUUID().toString();
        runtimeState.getValidatedFiles().put(validationId, result);

        return Map.of(
                "valid", true,
                "validation_id", validationId,
                "validated_uri", "validated://" + validationId,
                "details", result.get("details"),
                "mime", result.get("mime"),
                "size", result.get("size"),
                "hash_prefix", String.valueOf(result.get("hash")).substring(0, 16));
    }

    private static String detectMimeType(Path path, byte[] header) {
        if (header.length >= 3
                && (header[0] & 0xFF) == 0xFF
                && (header[1] & 0xFF) == 0xD8
                && (header[2] & 0xFF) == 0xFF) {
            return "image/jpeg";
        }
        if (header.length >= 8
                && header[0] == (byte) 0x89
                && header[1] == 'P'
                && header[2] == 'N'
                && header[3] == 'G') {
            return "image/png";
        }
        if (header.length >= 6
                && header[0] == 'G'
                && header[1] == 'I'
                && header[2] == 'F'
                && header[3] == '8') {
            return "image/gif";
        }
        if (header.length >= 12
                && header[0] == 'R'
                && header[1] == 'I'
                && header[2] == 'F'
                && header[3] == 'F'
                && header[8] == 'W'
                && header[9] == 'E'
                && header[10] == 'B'
                && header[11] == 'P') {
            return "image/webp";
        }
        if (header.length >= 4 && header[0] == 'R' && header[1] == 'I' && header[2] == 'F' && header[3] == 'F') {
            return "audio/wav";
        }
        if (header.length >= 3
                && header[0] == (byte) 0xFF
                && (header[1] & 0xE0) == 0xE0) {
            return "audio/mp3";
        }
        if (header.length >= 8
                && header[4] == 'f'
                && header[5] == 't'
                && header[6] == 'y'
                && header[7] == 'p') {
            return "video/mp4";
        }
        if (header.length >= 4 && header[0] == '%' && header[1] == 'P' && header[2] == 'D' && header[3] == 'F') {
            return "application/pdf";
        }
        return RuntimeState.detectMimeTypeFallback(path, header);
    }
}
