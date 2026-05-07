## Research Project Goal (Final, Clean Version)

### High-level goal

**To evaluate how large, structured tool outputs should be represented and delivered in MCP-based systems, and to determine whether Parquet-based streaming can outperform JSON while enabling early consumption and better efficiency—without modifying the MCP protocol.**

* * *

## Motivation

Model Context Protocol (MCP) standardizes how AI agents invoke tools using JSON-RPC. While JSON is effective for control messages and small responses, modern tools increasingly return **large structured data** such as tables, logs, metrics, and analytical results. Encoding these outputs entirely in JSON leads to:

*   high payload sizes
    
*   expensive serialization/deserialization
    
*   lack of early consumption
    
*   poor scalability for large results
    

The MCP specification does not define how large tool outputs should be handled, leaving an important design gap.

* * *

## Core research question

> **Is JSON the right representation for large MCP tool outputs, and if not, how do alternative encodings—specifically Parquet—change performance, streaming behavior, and system capabilities?**

* * *

## Key idea

Treat MCP as a **control plane** and introduce a **data plane** for large results:

*   **Control plane (unchanged):** MCP / JSON-RPC for tool invocation, schemas, and lifecycle
    
*   **Data plane:** Parquet-encoded outputs delivered via HTTP, either as:
    
    *   a single Parquet blob, or
        
    *   a stream of Parquet chunks enabling early consumption
        

This approach is fully backward-compatible with MCP and uses existing SDK capabilities.

* * *

## What the project implements

The project implements the _same logical tool_ in three output modes:

1.  **JSON output (baseline)**
    
    *   Entire result encoded as JSON
        
2.  **Parquet blob**
    
    *   Tool returns a URI to a Parquet file
        
3.  **Parquet chunk streaming**
    
    *   Tool returns a stream descriptor
        
    *   Server streams independent Parquet chunks
        
    *   Client decodes and consumes chunks incrementally
        

All three are invoked via MCP tools; only the data representation changes.