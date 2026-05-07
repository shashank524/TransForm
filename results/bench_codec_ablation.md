# Codec & Encoding-Strategy Ablation

Compression codecs: snappy, gzip, zstd, none.  
Encoding strategies: default (PyArrow defaults), data_driven (CodecDB-inspired per-column selection).  
JSON baseline included for reference.

| n_rows | n_cols | codec | encoding_strategy | bytes | encode_s | decode_s |
|--------|--------|-------|-------------------|-------|----------|----------|
| 10,000 | 6 | json | n/a | 1,111,675 | 0.0043 | 0.0047 |
| 10,000 | 6 | snappy | default | 407,792 | 0.0025 | 0.0154 |
| 10,000 | 6 | snappy | data_driven | 4,396 | 0.0015 | 0.0006 |
| 10,000 | 6 | gzip | default | 225,013 | 0.3577 | 0.0007 |
| 10,000 | 6 | gzip | data_driven | 4,446 | 0.0015 | 0.0004 |
| 10,000 | 6 | zstd | default | 195,391 | 0.0046 | 0.0008 |
| 10,000 | 6 | zstd | data_driven | 4,411 | 0.0013 | 0.0003 |
| 10,000 | 6 | none | default | 687,138 | 0.0016 | 0.0004 |
| 10,000 | 6 | none | data_driven | 5,673 | 0.0014 | 0.0004 |
| 10,000 | 20 | json | n/a | 3,472,073 | 0.0124 | 0.0144 |
| 10,000 | 20 | snappy | default | 1,226,861 | 0.0065 | 0.0011 |
| 10,000 | 20 | snappy | data_driven | 11,915 | 0.0041 | 0.0006 |
| 10,000 | 20 | gzip | default | 673,536 | 0.8687 | 0.0018 |
| 10,000 | 20 | gzip | data_driven | 12,063 | 0.0039 | 0.0006 |
| 10,000 | 20 | zstd | default | 588,707 | 0.0071 | 0.0010 |
| 10,000 | 20 | zstd | data_driven | 11,958 | 0.0039 | 0.0007 |
| 10,000 | 20 | none | default | 2,060,156 | 0.0046 | 0.0007 |
| 10,000 | 20 | none | data_driven | 15,740 | 0.0037 | 0.0006 |
| 100,000 | 6 | json | n/a | 11,816,676 | 0.0471 | 0.0485 |
| 100,000 | 6 | snappy | default | 4,230,402 | 0.0154 | 0.0024 |
| 100,000 | 6 | snappy | data_driven | 7,571 | 0.0137 | 0.0007 |
| 100,000 | 6 | gzip | default | 2,327,309 | 3.1498 | 0.0033 |
| 100,000 | 6 | gzip | data_driven | 7,574 | 0.0137 | 0.0007 |
| 100,000 | 6 | zstd | default | 2,075,280 | 0.0188 | 0.0018 |
| 100,000 | 6 | zstd | data_driven | 7,366 | 0.0139 | 0.0006 |
| 100,000 | 6 | none | default | 7,025,595 | 0.0122 | 0.0013 |
| 100,000 | 6 | none | data_driven | 20,462 | 0.0140 | 0.0006 |
| 100,000 | 20 | json | n/a | 36,820,410 | 0.1239 | 0.1437 |
| 100,000 | 20 | snappy | default | 12,738,833 | 0.0482 | 0.0041 |
| 100,000 | 20 | snappy | data_driven | 21,463 | 0.0441 | 0.0010 |
| 100,000 | 20 | gzip | default | 6,974,082 | 7.6051 | 0.0073 |
| 100,000 | 20 | gzip | data_driven | 21,470 | 0.0444 | 0.0012 |
| 100,000 | 20 | zstd | default | 6,276,591 | 0.0600 | 0.0039 |
| 100,000 | 20 | zstd | data_driven | 20,837 | 0.0441 | 0.0010 |
| 100,000 | 20 | none | default | 21,075,506 | 0.0375 | 0.0034 |
| 100,000 | 20 | none | data_driven | 60,121 | 0.0437 | 0.0010 |

## Interpretation

- Average JSON size is 6.2x larger than average Parquet size across all codec/strategy combinations.
- data_driven encoding is on average 99.7% smaller than default encoding (across all codecs).
- See CodecDB (Jiang et al., SIGMOD '21) and AdaEdge (Liu et al., ICDE '24) for data-driven and workload-aware compression selection.
