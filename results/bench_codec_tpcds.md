# Codec & Encoding-Strategy Ablation (TPC-DS catalog_sales SF=1)

Compression codecs: snappy, gzip, zstd, none.  
Encoding strategies: default (PyArrow defaults), data_driven (CodecDB-inspired per-column selection).  
JSON baseline included for reference.

| dataset | n_rows | n_cols | codec | encoding_strategy | bytes | encode_s | decode_s |
|---------|--------|--------|-------|-------------------|-------|----------|----------|
| tpcds_catalog_sales | 10,000 | 6 | json | n/a | 1,799,688 | 0.0149 | 0.0085 |
| tpcds_catalog_sales | 10,000 | 6 | snappy | default | 62,198 | 0.0017 | 0.0010 |
| tpcds_catalog_sales | 10,000 | 6 | snappy | data_driven | 62,198 | 0.0024 | 0.0008 |
| tpcds_catalog_sales | 10,000 | 6 | gzip | default | 50,911 | 0.0158 | 0.0008 |
| tpcds_catalog_sales | 10,000 | 6 | gzip | data_driven | 50,911 | 0.0158 | 0.0007 |
| tpcds_catalog_sales | 10,000 | 6 | zstd | default | 50,085 | 0.0024 | 0.0009 |
| tpcds_catalog_sales | 10,000 | 6 | zstd | data_driven | 50,085 | 0.0020 | 0.0005 |
| tpcds_catalog_sales | 10,000 | 6 | none | default | 82,842 | 0.0011 | 0.0006 |
| tpcds_catalog_sales | 10,000 | 6 | none | data_driven | 82,842 | 0.0018 | 0.0006 |
| tpcds_catalog_sales | 10,000 | 20 | json | n/a | 5,428,824 | 0.0424 | 0.0267 |
| tpcds_catalog_sales | 10,000 | 20 | snappy | default | 262,137 | 0.0046 | 0.0015 |
| tpcds_catalog_sales | 10,000 | 20 | snappy | data_driven | 247,815 | 0.0060 | 0.0011 |
| tpcds_catalog_sales | 10,000 | 20 | gzip | default | 216,902 | 0.0813 | 0.0015 |
| tpcds_catalog_sales | 10,000 | 20 | gzip | data_driven | 197,729 | 0.0893 | 0.0014 |
| tpcds_catalog_sales | 10,000 | 20 | zstd | default | 211,641 | 0.0045 | 0.0012 |
| tpcds_catalog_sales | 10,000 | 20 | zstd | data_driven | 194,620 | 0.0063 | 0.0009 |
| tpcds_catalog_sales | 10,000 | 20 | none | default | 340,334 | 0.0037 | 0.0012 |
| tpcds_catalog_sales | 10,000 | 20 | none | data_driven | 350,266 | 0.0052 | 0.0010 |
| tpcds_catalog_sales | 10,000 | 34 | json | n/a | 9,369,270 | 0.1102 | 0.0453 |
| tpcds_catalog_sales | 10,000 | 34 | snappy | default | 952,378 | 0.0103 | 0.0021 |
| tpcds_catalog_sales | 10,000 | 34 | snappy | data_driven | 751,439 | 0.0114 | 0.0018 |
| tpcds_catalog_sales | 10,000 | 34 | gzip | default | 805,376 | 0.1075 | 0.0024 |
| tpcds_catalog_sales | 10,000 | 34 | gzip | data_driven | 590,273 | 0.1135 | 0.0018 |
| tpcds_catalog_sales | 10,000 | 34 | zstd | default | 792,545 | 0.0111 | 0.0017 |
| tpcds_catalog_sales | 10,000 | 34 | zstd | data_driven | 575,839 | 0.0118 | 0.0015 |
| tpcds_catalog_sales | 10,000 | 34 | none | default | 1,034,384 | 0.0090 | 0.0018 |
| tpcds_catalog_sales | 10,000 | 34 | none | data_driven | 859,334 | 0.0100 | 0.0016 |
| tpcds_catalog_sales | 100,000 | 6 | json | n/a | 17,995,975 | 0.1149 | 0.0676 |
| tpcds_catalog_sales | 100,000 | 6 | snappy | default | 622,590 | 0.0082 | 0.0013 |
| tpcds_catalog_sales | 100,000 | 6 | snappy | data_driven | 622,590 | 0.0120 | 0.0011 |
| tpcds_catalog_sales | 100,000 | 6 | gzip | default | 474,764 | 0.1883 | 0.0025 |
| tpcds_catalog_sales | 100,000 | 6 | gzip | data_driven | 474,764 | 0.2002 | 0.0019 |
| tpcds_catalog_sales | 100,000 | 6 | zstd | default | 482,787 | 0.0095 | 0.0013 |
| tpcds_catalog_sales | 100,000 | 6 | zstd | data_driven | 482,787 | 0.0143 | 0.0014 |
| tpcds_catalog_sales | 100,000 | 6 | none | default | 776,079 | 0.0080 | 0.0012 |
| tpcds_catalog_sales | 100,000 | 6 | none | data_driven | 776,079 | 0.0125 | 0.0011 |
| tpcds_catalog_sales | 100,000 | 20 | json | n/a | 54,426,911 | 0.3883 | 0.2230 |
| tpcds_catalog_sales | 100,000 | 20 | snappy | default | 2,253,761 | 0.0285 | 0.0033 |
| tpcds_catalog_sales | 100,000 | 20 | snappy | data_driven | 2,253,761 | 0.0392 | 0.0033 |
| tpcds_catalog_sales | 100,000 | 20 | gzip | default | 1,821,870 | 0.5812 | 0.0048 |
| tpcds_catalog_sales | 100,000 | 20 | gzip | data_driven | 1,821,870 | 0.6087 | 0.0044 |
| tpcds_catalog_sales | 100,000 | 20 | zstd | default | 1,844,266 | 0.0304 | 0.0032 |
| tpcds_catalog_sales | 100,000 | 20 | zstd | data_driven | 1,844,266 | 0.0434 | 0.0032 |
| tpcds_catalog_sales | 100,000 | 20 | none | default | 2,691,011 | 0.0259 | 0.0032 |
| tpcds_catalog_sales | 100,000 | 20 | none | data_driven | 2,691,011 | 0.0377 | 0.0029 |
| tpcds_catalog_sales | 100,000 | 34 | json | n/a | 93,829,384 | 1.0205 | 0.4079 |
| tpcds_catalog_sales | 100,000 | 34 | snappy | default | 8,343,944 | 0.0874 | 0.0080 |
| tpcds_catalog_sales | 100,000 | 34 | snappy | data_driven | 7,105,593 | 0.1027 | 0.0054 |
| tpcds_catalog_sales | 100,000 | 34 | gzip | default | 7,072,231 | 1.0396 | 0.0145 |
| tpcds_catalog_sales | 100,000 | 34 | gzip | data_driven | 5,677,504 | 1.0330 | 0.0105 |
| tpcds_catalog_sales | 100,000 | 34 | zstd | default | 7,086,016 | 0.0919 | 0.0080 |
| tpcds_catalog_sales | 100,000 | 34 | zstd | data_driven | 5,592,836 | 0.1081 | 0.0053 |
| tpcds_catalog_sales | 100,000 | 34 | none | default | 8,840,936 | 0.0825 | 0.0069 |
| tpcds_catalog_sales | 100,000 | 34 | none | data_driven | 7,620,067 | 0.0956 | 0.0050 |
| tpcds_catalog_sales | 500,000 | 6 | json | n/a | 89,981,589 | 0.5896 | 0.3524 |
| tpcds_catalog_sales | 500,000 | 6 | snappy | default | 2,957,558 | 0.0410 | 0.0036 |
| tpcds_catalog_sales | 500,000 | 6 | snappy | data_driven | 2,957,558 | 0.0624 | 0.0031 |
| tpcds_catalog_sales | 500,000 | 6 | gzip | default | 2,326,449 | 0.7781 | 0.0103 |
| tpcds_catalog_sales | 500,000 | 6 | gzip | data_driven | 2,326,449 | 0.8781 | 0.0070 |
| tpcds_catalog_sales | 500,000 | 6 | zstd | default | 2,366,370 | 0.0484 | 0.0040 |
| tpcds_catalog_sales | 500,000 | 6 | zstd | data_driven | 2,366,370 | 0.0741 | 0.0041 |
| tpcds_catalog_sales | 500,000 | 6 | none | default | 3,711,340 | 0.0444 | 0.0036 |
| tpcds_catalog_sales | 500,000 | 6 | none | data_driven | 3,711,340 | 0.0670 | 0.0033 |
| tpcds_catalog_sales | 500,000 | 20 | json | n/a | 273,002,975 | 1.9738 | 1.2176 |
| tpcds_catalog_sales | 500,000 | 20 | snappy | default | 10,687,215 | 0.1433 | 0.0158 |
| tpcds_catalog_sales | 500,000 | 20 | snappy | data_driven | 10,687,215 | 0.2134 | 0.0146 |
| tpcds_catalog_sales | 500,000 | 20 | gzip | default | 8,881,189 | 2.5028 | 0.0260 |
| tpcds_catalog_sales | 500,000 | 20 | gzip | data_driven | 8,881,189 | 2.4668 | 0.0181 |
| tpcds_catalog_sales | 500,000 | 20 | zstd | default | 9,021,164 | 0.1455 | 0.0134 |
| tpcds_catalog_sales | 500,000 | 20 | zstd | data_driven | 9,021,164 | 0.2087 | 0.0126 |
| tpcds_catalog_sales | 500,000 | 20 | none | default | 12,662,163 | 0.1244 | 0.0128 |
| tpcds_catalog_sales | 500,000 | 20 | none | data_driven | 12,662,163 | 0.1862 | 0.0123 |
| tpcds_catalog_sales | 500,000 | 34 | json | n/a | 469,994,346 | 4.7679 | 2.0002 |
| tpcds_catalog_sales | 500,000 | 34 | snappy | default | 35,802,052 | 0.4239 | 0.0327 |
| tpcds_catalog_sales | 500,000 | 34 | snappy | data_driven | 34,174,362 | 0.5240 | 0.0208 |
| tpcds_catalog_sales | 500,000 | 34 | gzip | default | 31,153,690 | 3.6211 | 0.0547 |
| tpcds_catalog_sales | 500,000 | 34 | gzip | data_driven | 27,751,872 | 4.0765 | 0.0347 |
| tpcds_catalog_sales | 500,000 | 34 | zstd | default | 31,297,600 | 0.4493 | 0.0328 |
| tpcds_catalog_sales | 500,000 | 34 | zstd | data_driven | 27,412,093 | 0.5545 | 0.0234 |
| tpcds_catalog_sales | 500,000 | 34 | none | default | 38,145,391 | 0.3978 | 0.0295 |
| tpcds_catalog_sales | 500,000 | 34 | none | data_driven | 36,518,665 | 0.4894 | 0.0217 |

## Interpretation

- Average JSON size is 17.8x larger than average Parquet size across all codec/strategy combinations.
- data_driven encoding is on average 7.1% smaller than default encoding (across all codecs).
- See CodecDB (Jiang et al., SIGMOD '21) and AdaEdge (Liu et al., ICDE '24) for data-driven and workload-aware compression selection.
