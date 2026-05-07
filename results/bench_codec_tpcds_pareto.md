# TPC-DS Parquet codec/encoding Pareto summary

Objective: minimize **bytes** and **total_time_s = encode_s + decode_s**.

## Slice 10000x6 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| zstd | data_driven | 50,085 | 0.002039 | 0.000456 | 0.002495 |
| none | default | 82,842 | 0.001146 | 0.000648 | 0.001794 |

## Slice 10000x20 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| zstd | data_driven | 194,620 | 0.006311 | 0.000923 | 0.007234 |
| zstd | default | 211,641 | 0.004495 | 0.001154 | 0.005649 |
| none | default | 340,334 | 0.003747 | 0.001155 | 0.004902 |

## Slice 10000x34 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| zstd | data_driven | 575,839 | 0.011804 | 0.001520 | 0.013324 |
| snappy | data_driven | 751,439 | 0.011443 | 0.001820 | 0.013263 |
| zstd | default | 792,545 | 0.011070 | 0.001659 | 0.012729 |
| none | data_driven | 859,334 | 0.010047 | 0.001588 | 0.011635 |
| none | default | 1,034,384 | 0.009040 | 0.001759 | 0.010799 |

## Slice 100000x6 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| gzip | default | 474,764 | 0.188277 | 0.002452 | 0.190729 |
| zstd | default | 482,787 | 0.009451 | 0.001346 | 0.010797 |
| snappy | default | 622,590 | 0.008235 | 0.001268 | 0.009503 |
| none | default | 776,079 | 0.008025 | 0.001194 | 0.009219 |

## Slice 100000x20 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| gzip | default | 1,821,870 | 0.581223 | 0.004770 | 0.585993 |
| zstd | default | 1,844,266 | 0.030368 | 0.003171 | 0.033539 |
| snappy | default | 2,253,761 | 0.028481 | 0.003296 | 0.031777 |
| none | default | 2,691,011 | 0.025915 | 0.003150 | 0.029065 |

## Slice 100000x34 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| zstd | data_driven | 5,592,836 | 0.108069 | 0.005253 | 0.113322 |
| zstd | default | 7,086,016 | 0.091922 | 0.008021 | 0.099943 |
| snappy | default | 8,343,944 | 0.087389 | 0.007997 | 0.095386 |
| none | default | 8,840,936 | 0.082541 | 0.006881 | 0.089422 |

## Slice 500000x6 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| gzip | default | 2,326,449 | 0.778120 | 0.010280 | 0.788400 |
| zstd | default | 2,366,370 | 0.048442 | 0.003986 | 0.052428 |
| snappy | default | 2,957,558 | 0.041023 | 0.003623 | 0.044646 |

## Slice 500000x20 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| gzip | data_driven | 8,881,189 | 2.466763 | 0.018116 | 2.484879 |
| zstd | default | 9,021,164 | 0.145504 | 0.013431 | 0.158935 |
| none | default | 12,662,163 | 0.124445 | 0.012764 | 0.137209 |

## Slice 500000x34 (Pareto front)

| codec | strategy | bytes | encode_s | decode_s | total_time_s |
|---|---|---:|---:|---:|---:|
| zstd | data_driven | 27,412,093 | 0.554542 | 0.023410 | 0.577952 |
| zstd | default | 31,297,600 | 0.449272 | 0.032835 | 0.482107 |
| snappy | default | 35,802,052 | 0.423851 | 0.032667 | 0.456518 |
| none | default | 38,145,391 | 0.397846 | 0.029528 | 0.427374 |
