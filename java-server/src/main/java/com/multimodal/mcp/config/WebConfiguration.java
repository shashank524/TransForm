package com.multimodal.mcp.config;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import com.multimodal.mcp.http.BearerAuthFilter;

@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Bean
    public FilterRegistrationBean<BearerAuthFilter> bearerAuthFilterRegistration() {
        FilterRegistrationBean<BearerAuthFilter> registration = new FilterRegistrationBean<>();
        registration.setFilter(new BearerAuthFilter());
        registration.addUrlPatterns(
                "/mcp",
                "/mcp/*",
                "/blobs/*",
                "/streams/*",
                "/ipc-blobs/*",
                "/ipc-streams/*",
                "/raw/*",
                "/raw-gzip/*",
                "/materialized",
                "/materialized-raw");
        registration.setOrder(1);
        return registration;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .exposedHeaders(
                        "X-Benchmark-Rows",
                        "X-Benchmark-Cols",
                        "X-Benchmark-Bytes",
                        "X-Benchmark-Compression",
                        "X-Benchmark-Encoding-Strategy",
                        "X-Benchmark-Rows-Per-Chunk",
                        "X-Benchmark-IPC-Compression",
                        "Content-Encoding");
    }
}
