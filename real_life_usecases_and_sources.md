# Real-Life Use Cases & Supporting Sources for Parquet-Based MCP Tool Outputs

This document summarizes **real-world scenarios** where large structured tool outputs matter, **papers and industry sources** that support the problem, and how this project’s approach (MCP control plane + Parquet data plane) fits.

---

## 1. Real-Life Use Cases (What to Say in the Meeting)

### A. **Text-to-SQL / NL2SQL agents**

- **Scenario**: An LLM agent turns natural language into SQL and the database returns **large result sets** (e.g. 100k+ rows for analytics).
- **Problem today**: If the tool “returns query results” as JSON over MCP, the payload and parse cost explode; context limits and latency make full-table results impractical.
- **Your approach**: MCP tool returns a **descriptor** (e.g. “results at `/blobs/{id}.parquet`” or “stream at `/streams/{id}`”). The agent (or a downstream consumer) fetches Parquet over HTTP—smaller payload, faster decode, and with streaming, **time-to-first-rows** in milliseconds so the agent can start reasoning or paginate without waiting for the full result.
- **Supporting angle**: Text-to-SQL and “agentic speculation” (many exploratory queries) require **sub-second iteration**; large JSON tool outputs are a bottleneck (Firebolt whitepaper, Berkeley-style agentic workloads).

### B. **Data lakes & table discovery (LLM-driven analytics)**

- **Scenario**: LLMs are used to **discover and query tables** in data lakes (e.g. LEDD, Pneuma, OTQA). Queries can return large tables or samples.
- **Problem**: Delivering full table contents or large samples as JSON through the tool-calling channel is inefficient and hits context limits.
- **Your approach**: Tool returns a URL to Parquet (blob or stream). The client (agent runtime or analytics layer) fetches columnar data, optionally with **projection pushdown** (read only needed columns), matching how data lakes already store data (Parquet/ORC).
- **Supporting angle**: “Efficient Data Formats for Generative AI” (Parquet/ORC/columnar) and data-lake + LLM papers (LEDD, table QA over data lakes).

### C. **Observability / logs & metrics (agents that analyze telemetry)**

- **Scenario**: An AI agent has a “query logs” or “get metrics” tool. Results are large (time-series, many rows/columns).
- **Problem**: Returning full result sets as JSON in the tool response blows up payload size and latency.
- **Your approach**: Tool returns a descriptor; actual log/metric tables are served as Parquet (blob or stream). Streaming gives **early rows** so the agent can decide to refine the query or stop early (e.g. “first 8k rows enough”).
- **Supporting angle**: Observability platforms (SigNoz, Langfuse, etc.) already deal with large traces/logs; agent tools that return “big tables” benefit from the same pattern you benchmark.

### D. **Agentic speculation / high-throughput exploratory querying**

- **Scenario**: Berkeley-style “agentic speculation”—agents fire **many exploratory queries** (metadata, samples, partial results) to converge on an answer. Success depends on **low latency per result** (sub-second).
- **Problem**: If each tool result is a huge JSON blob, serialization, network, and parse time dominate; iteration speed drops and agent effectiveness degrades.
- **Your approach**: Keep MCP for **control** (which tool, which params); deliver **large results** as Parquet over HTTP. You showed ~3× smaller payloads and ~20–30× faster end-to-end for large tables, and with streaming, **time-to-first-rows** in the single-digit milliseconds—directly supporting fast iteration.
- **Supporting angle**: Firebolt whitepaper “Data Systems in the Age of AI Agents” and the Berkeley research it cites (e.g. arxiv 2509.00997): iteration speed and efficient result delivery are first-order requirements.

### E. **Dashboard / BI-style “run report” tools**

- **Scenario**: Agent tool “run_report(dataset, filters)” returns a large table for charting or further analysis.
- **Problem**: Embedding the full table in the tool response as JSON is heavy and slow.
- **Your approach**: Tool returns a descriptor; the actual report table is fetched as Parquet (or streamed). Downstream (BI tool or another agent) can stream and render incrementally (early rows) or only fetch needed columns (projection).

### F. **Spreadsheet automation agents (Excel / Google Sheets)**

- **Scenario**: An LLM agent automates spreadsheets via **atomic actions** (read ranges, pivot, filter, chart)—each step can touch **large rectangular regions** (many rows × columns).
- **Problem**: Returning full sheet snapshots or intermediate grids as JSON in every tool turn inflates payloads and slows the observe–plan–act loop.
- **Your approach**: Tools that return “the current grid / result of this operation” expose a **Parquet descriptor** for bulk data; the agent keeps **small structured metadata** (range, sheet id) in MCP while fetching columnar data over HTTP.
- **Supporting angle**: **SheetCopilot** (NeurIPS 2023) formalizes spreadsheet control as an agent with state-machine planning; success depends on **many tool interactions** over tabular state—exactly where efficient bulk serialization helps.

### G. **Enterprise warehouse / cloud SQL workflows (beyond single-shot Text-to-SQL)**

- **Scenario**: Agents operate in **real enterprise** settings: Snowflake/BigQuery-style warehouses, **very wide schemas** (1000+ columns), documentation and dbt code in-repo, **multi-step SQL** (tens to hundreds of lines), and **large intermediate result sets**.
- **Problem**: Baselines that assume “one SELECT, small result” underestimate **payload and latency** when tools return big tables or samples after each sub-query.
- **Your approach**: Same control/data-plane split as Text-to-SQL (§A), but the narrative emphasizes **workflow length** and **warehouse scale**—Parquet blob/stream keeps each execution leg cheap to transfer and decode.
- **Supporting angle**: **Spider 2.0** (ICLR 2025) benchmarks **real-world enterprise text-to-SQL workflows** (632 tasks, cloud/local engines); it highlights long contexts and complex pipelines—use it when you argue that **delivery format** matters for each execution step, not only final answer quality.

### H. **Code-interpreter / notebook-style data-science agents**

- **Scenario**: The agent runs **Python in a sandbox** (pandas, sklearn, PyTorch): `read_csv`, `df.describe()`, joins, train/eval loops. Tool outputs are often **DataFrames**, **arrays**, or **logs**—tabular or easy to cast to tables.
- **Problem**: Serializing large frames to JSON for every `execute_cell` or tool return duplicates row-oriented overhead; multi-turn notebooks amplify cost.
- **Your approach**: Represent “large execution result” as **Parquet** on the data plane; keep stderr/short stdout as text. Aligns with **columnar** consumption if downstream steps only need subsets of columns.
- **Supporting angle**: **CIBench** evaluates LLMs on **interactive code-interpreter** sessions for data science (analysis, ML, viz); **Data Interpreter** (LLM agent for end-to-end data science, MetaGPT line of work) stresses **dynamic planning and tool integration**—both assume **repeated execution** with non-trivial outputs.

### I. **Open-domain QA over tables + text (retrieval agents)**

- **Scenario**: The agent **retrieves** evidence from a corpus where answers may live in **Wikipedia tables**, **HTML tables**, or **linked passages**—multi-hop over **heterogeneous** stores.
- **Problem**: Once a relevant table is identified, **materializing** it for the reader model can mean **large structured payloads** per hop; mixing with text snippets increases total bytes moved per turn.
- **Your approach**: Retrieved tables flow through the same **descriptor + Parquet** path; text chunks stay in MCP or a separate RAG channel. Lets you **separate** “bulk structured evidence” from “unstructured passages.”
- **Supporting angle**: **OTT-QA** (ICLR 2021) is a **peer-reviewed** open-domain benchmark requiring **joint reasoning over tables and text**; newer tool agents (e.g. **OpenTable-R1**, arXiv) emphasize **tool use** for open-domain table QA—good citations for **mixed modalities** in the retrieval loop.

### J. **AutoML / experiment-tracking agents**

- **Scenario**: Multi-agent systems run **preprocessing, model search, training**; tools return **metrics tables** (per-epoch loss, validation scores), **hyperparameter grids**, and **leaderboards**—often wide and long.
- **Problem**: Logging every trial as JSON tool output to the LLM context is **token- and bandwidth-heavy**; parallel agents multiply traffic.
- **Your approach**: **Experiment results** as Parquet on the data plane; the agent receives a **small summary dict** (best trial id, metric name) over MCP.
- **Supporting angle**: **AutoML-Agent** (multi-agent full-pipeline AutoML, arXiv) and related **AutoML-GPT** line use LLMs to orchestrate pipelines—**tabular metrics** are central artifacts between tools and planners.

### K. **Regulatory / risk reporting and ESG pipelines (industry)**

- **Scenario**: Agents assemble **submission tables** (many rows, many indicators) from internal systems for **disclosure** or **stress tests**; outputs are **strictly structured** with audit trails.
- **Problem**: Large submissions as inline JSON are hard to **version, sign, and stream** to reviewers.
- **Your approach**: Immutable **Parquet blobs** with checksums; MCP carries **references and lineage** (which query produced which blob)—complements governance narratives (pair with **client auth** / signed URLs in production).

---

## 1.5 Citations, peer-reviewed datasets, and benchmarking multiple workflows

### Can you benchmark against multiple workflows?

**Yes.** The same metrics you already use (**payload bytes, end-to-end latency, time-to-first-rows, optional cost proxies**) apply across workflows. What changes is the **story** and the **data profile**:

- Keep the **MCP control plane + Parquet/JSON data plane** fixed.
- For each workflow, define a **scenario adapter**: e.g. (1) *shape* of the synthetic table (`n_rows`, `n_cols`, string vs numeric columns), (2) optional **replay** of a small subset of a paper benchmark (executed SQL results, retrieved table slices, spreadsheet regions), (3) optional **second tool** for unstructured text (explanation / summary) when the workflow is mixed-output.
- Report results **per workflow family** (or per adapter), not only one global grid—reviewers can then map your numbers to Text-to-SQL vs spreadsheet vs code-interpreter settings.

Below: **primary citations** and **datasets/corpora** that appear in peer-reviewed (or clearly documented benchmark) work for each workflow in §1.A–K. Where no standard agent benchmark exists, we flag **industry / preprint / internal** honestly.

### Master table: workflow → citations → datasets

| § | Workflow | Primary citations (examples) | Datasets / corpora in the literature | Peer-reviewed data? |
|---|----------|------------------------------|----------------------------------------|---------------------|
| **A** | Text-to-SQL / NL2SQL | **BIRD** (Li et al., NeurIPS 2023); **Gao et al.** (PVLDB 2024); **Spider 1.0** (Yu et al., EMNLP 2018); **SQLStorm** (Schmidt et al., PVLDB 2025) | **BIRD**: 95 databases, **12,751** question–SQL pairs, **33.4 GB** total; **Spider 1.0**: **200** DBs, **10,181** questions (cross-domain); **WikiSQL** (Zhong et al., 2017): **80,654** pairs over **24,241** tables—often used for semantic parsing / execution; **SQLStorm**: LLM-generated workloads on **1 GB–220 GB**-class real datasets | **Yes** (BIRD, Spider, WikiSQL, SQLStorm via PVLDB; Gao uses multiple benchmarks including academic sets) |
| **B** | Data lakes & table discovery | **OTT-QA** (Chen et al., ICLR 2021); **HybridQA** (Chen et al., EMNLP 2020); **Liu et al.** (VLDB Journal 2025) for columnar/Parquet trade-offs in analytics | **HybridQA**: **70,000** questions, **~13,000** Wikipedia tables, **~293,000** passages ([project](https://hybridqa.github.io/)); **OTT-QA**: **~45,000** questions, **400K+** tables, **millions** of linked passages ([GitHub](https://github.com/wenhuchen/OTT-QA)) | **Yes** (ICLR / EMNLP) |
| **C** | Observability / logs & metrics | Industry (SigNoz, Langfuse, Datadog, etc.); **AgentTrace** (arXiv:2602.10133)—structured logging for agents | **No single peer-reviewed “agent over logs” benchmark** is standard. Practitioners use **internal traces**, **OpenTelemetry** exports, or public log collections (e.g. **LogHub**-style corpora—check latest biblio for the collection you cite). For papers, prefer **explicit dataset names** from each observability/ML-on-logs paper you cite. | **Mixed** (public log corpora exist; agent+telemetry benchmarks are fragmented) |
| **D** | Agentic speculation | **Liu et al.** (arXiv:2509.00997, UC Berkeley); **Firebolt whitepaper** “Data Systems in the Age of AI Agents” | Berkeley work characterizes **agentic analytical workloads** (high fan-out, exploratory queries); datasets are often **synthetic or warehouse traces**—see paper for exact traces. Firebolt: industry positioning, not a dataset. | **Preprint / industry** for the headline citation; read Berkeley paper for any **named traces** |
| **E** | Dashboard / BI “run report” | Same as **§A** and **§G** (report = executed query / cube result); **TPC-DS / TPC-H** as industry analytics standards | **TPC-DS**, **TPC-H** (official benchmark databases—not paper-specific but standard for **large analytic result sets**); academic studies often reuse **Spider/BIRD** execution results or warehouse samples | **TPC** = standard benchmark spec; **Spider/BIRD** = peer-reviewed benchmarks for the SQL side |
| **F** | Spreadsheet automation | **SheetCopilot** (Li et al., NeurIPS 2023; arXiv:2305.19308) | **SheetCopilot benchmark**: **221** spreadsheet control tasks across **28** workbooks; **44** operation types in the public materials | **Yes** (NeurIPS) |
| **G** | Enterprise warehouse SQL workflows | **Spider 2.0** (Lei et al., ICLR 2025; arXiv:2411.07763) | **632** real-world workflow problems; subsets **Spider 2.0-Snow** (Snowflake), **Spider 2.0-Lite** (BigQuery / Snowflake / SQLite), **Spider 2.0-DBT** (**68** dbt/DuckDB-style code-agent tasks); DBs often **1000+ columns** | **Yes** (ICLR) |
| **H** | Code-interpreter / data science | **CIBench** (Zhang et al., arXiv:2407.10499; OpenReview—confirm ACL if accepted); **Data Interpreter** (Hong et al., arXiv:2402.18679); **InfiAgent-DABench** (Hu et al., **ICML 2024**) | **CIBench**: **234** tasks, **1900+** sub-questions, consecutive **IPython** sessions; covers **pandas, matplotlib, PyTorch**, etc.; **InfiAgent-DABench** / **DAEval**: **603** data-analysis questions built from **124** CSV files ([PMLR](https://proceedings.mlr.press/v235/hu24s.html), [OpenReview](https://openreview.net/forum?id=d5LURMSfTx)) | **InfiAgent-DABench: Yes** (ICML); **CIBench**: arXiv + confirm conference listing |
| **I** | Open-domain table + text QA | **OTT-QA** (ICLR 2021); **OpenTable-R1** (Qiu, arXiv:2507.03018) | **OTT-QA** corpus (tables + passages as above); **OpenTable-R1** evaluates on **Open WikiTable** (paper’s name for the open-domain WikiTable QA setting; tables indexed for **BM25+** and loaded into **SQLite** for SQL tool)—see paper §3–4 and [code](https://github.com/TabibitoQZP/OpenTableR1) for exact splits | **OTT-QA: Yes**; **OpenTable-R1: preprint** (builds on established table-QA corpora) |
| **J** | AutoML / experiment tracking | **AutoML-Agent** (Trirat et al., arXiv:2410.02958) | Paper reports experiments on **seven downstream task types** with **fourteen datasets** total (mix of **tabular, CV, NLP**—see paper tables for names, e.g. classic UCI/OpenML-style and vision/text sets); no single “agent metrics table” standard | **Datasets peer-reviewed or standard ML benchmarks**; **framework** paper is arXiv |
| **K** | Regulatory / ESG reporting | **Standards** (e.g. **XBRL** taxonomies, jurisdiction-specific disclosure templates); optional **risk** literature (BCBS stress-testing narratives) | Typically **proprietary bank/issuer submissions**; **no** widely shared peer-reviewed “agent ESG benchmark” | **Industry / regulatory** (use for motivation, not for reproducible bench without your own released subset) |

### How this maps to *your* repo today

- **Already aligned**: **TPC-DS `catalog_sales`** (optional) and **synthetic** `(n_rows, n_cols)` grids mirror **§A / §E / §G** (analytic tables) and can **stand in** for fragments of **BIRD/Spider**-shaped results if you document column semantics.
- **To add later for paper-faithful benches**: small **replays**—e.g. export result shapes from **BIRD dev** or **Spider 2.0-Lite** after execution; **SheetCopilot**-style workloads need spreadsheet traces; **CIBench** needs IPython session replay (heavier).
- **§B / §I**: Use **HybridQA** or **OTT-QA** when you add a **text + table** adapter (two channels: Parquet for table evidence, text for passages).

**§B note:** §1.B names **LEDD / Pneuma / OTQA** as examples of data-lake discovery; for **peer-reviewed** benchmarks with explicit table–text corpora, cite **HybridQA** and **OTT-QA** (rows above) and add LEDD/Pneuma only after you have a stable DOI for each.

### Spider 1.0 (for §A) — full cite

- **Yu, T., et al. (2018).** “Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task.” **EMNLP 2018.** — [ACL Anthology](https://aclanthology.org/D18-1426/) · [Spider site](https://yale-lily.github.io/spider)

---

## 2. Papers & Industry Sources to Cite

### MCP and tool-use ecosystems

- **Guo et al., “A Measurement Study of Model Context Protocol Ecosystem”** (arXiv:2509.25292)  
  - First large-scale measurement of MCP (8,060 servers, 341 clients). Notes **response format diversity** and **scalability** as ecosystem concerns. Supports the need for **standardized, efficient handling of large tool outputs** rather than ad-hoc JSON blobs.
- **MCP-Atlas / tool-use benchmarks**  
  - Benchmarks for tool-use with real MCP servers; tool **result** size and format affect task success. Your work directly addresses “how to represent large results” in such setups.

### Agentic workloads and data systems

- **Firebolt whitepaper: “Data Systems in the Age of AI Agents: Requirements and Architecture”**  
  - Builds on Berkeley-style “agentic speculation”: high-throughput, heterogeneous, redundant exploratory queries. Emphasizes **sub-second analytical performance**, **mixed workloads**, and **standards-based integration**.  
  - **Relevance**: Delivering large query/analytics results efficiently (e.g. Parquet over HTTP instead of JSON in the control channel) is exactly the kind of “data system” requirement they describe.
- **Berkeley-style agentic speculation** (referenced in Firebolt; e.g. arxiv 2509.00997)  
  - Agents issue many queries; **latency per result** and **iteration speed** drive success. Your benchmarks show that moving large results off MCP and into Parquet reduces latency and payload—directly supporting faster iteration.

### Table reasoning and LLM + structured data

- **TableMind, JT-DA, TableZoomer** (arXiv and related)  
  - LLM agents for **table reasoning** and tool-augmented analytics; they deal with **large tables** and context limits. Your work provides a **protocol-level** option: same tools, but large table *content* delivered as Parquet (blob/stream) instead of in-context JSON.
- **LEDD (LLM-Empowered Data Discovery in Data Lakes)**  
  - Semantic search and discovery over data lakes; downstream consumption of **tables** (for training, text-to-SQL, etc.). Your pattern (descriptor in MCP, data via Parquet URL) fits “return large table references/results” in such pipelines.

### Data formats and columnar storage

- **“Efficient Data Formats for Generative AI: Why Parquet, ORC, and Columnar Storage Matter”** (Medium / data-eng articles)  
  - Parquet/columnar reduces I/O and improves analytics and ML pipelines. Your project **applies the same idea** to the *tool-output* channel: large structured results as Parquet instead of JSON.
- **SochDB / “AI-Native Database for Agent Memory & Context”**  
  - Discusses **token-optimized output** and **columnar storage** for agent-facing data; argues that **row-based JSON** is inefficient for LLM/agent consumption. Your work is a **concrete protocol design** (MCP + Parquet URLs) that avoids putting large JSON in the tool response.

### Context length and long-context LLMs

- **“Can Long-Context LLMs Subsume Retrieval, RAG, SQL, and More?”** (e.g. 2406.13121)  
  - Long context helps, but **how** information is presented and how much is **transferred** still matter. Your approach reduces **how much** is sent over the tool channel (descriptor only) and **how** the bulk is encoded (Parquet), which complements long-context use cases.
- **“Beyond the Limits: A Survey of Techniques to Extend Context Length”**  
  - Extending context has a cost; **not putting** large tables in context (instead, streaming Parquet by reference) is an orthogonal, efficient strategy your project demonstrates.

---

## 3. One-Sentence Pitch for the Professor

**“Real-life use cases include text-to-SQL agents receiving large query results, LLM-driven data-lake discovery and table QA, observability agents analyzing logs/metrics tables, and Berkeley-style agentic speculation where many exploratory queries return large result sets—all of which are poorly served by stuffing full results into JSON over MCP; our approach (MCP as control plane, Parquet over HTTP as data plane) is supported by MCP ecosystem studies, agentic workload whitepapers, and table-reasoning/columnar-format literature, and our benchmarks show large payload and latency gains plus millisecond time-to-first-rows when streaming.”**

**Optional add-on (broader workflows):** The same pattern applies to **spreadsheet agents**, **enterprise warehouse workflows (Spider 2.0-style)**, **code-interpreter data-science agents**, **open-domain table+text retrieval**, and **AutoML-style metric tables**—any agent loop where tools repeatedly return **large tabular artifacts**.

---

## 4. Peer-Reviewed Papers (Venues & Citations)

Use these for “Related Work” or “Motivation” when you need **journal or conference** citations.

### Text-to-SQL and large result sets

- **Gao, D., Wang, H., Liu, J., Sun, Y., Qiu, Y., Du, Z. (2024).** “Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation.” **Proceedings of the VLDB Endowment (PVLDB), Vol. 17.**  
  - Systematic benchmark of prompt-engineering and LLM-based text-to-SQL; discusses token efficiency and execution over real DBs. **VLDB 2024.**  
  - [dblp](https://dblp.org/rec/journals/pvldb/GaoWLSQDZ24) · PDF: `vldb.org/pvldb/vol17/p1132-gao.pdf`
- **Li, J., Hui, B., Qu, G., Yang, J., Li, B., Li, B., Wang, B., Li, B., Wang, Y., Ma, G., Yang, Y., Zhang, W., Li, Y. (2023).** “Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs.” **NeurIPS 2023 (Spotlight).**  
  - **BIRD benchmark**: 12,751 question-SQL pairs, 95 databases, 33.4 GB, 37 domains; emphasizes dirty data, external knowledge, and **SQL execution efficiency on large databases**.  
  - [OpenReview](https://openreview.net/forum?id=dI4wzAE6uV) · [BIRD-bench](https://bird-bench.github.io/)
- **Schmidt, C. et al. (2025).** “SQLStorm: Taking Database Benchmarking into the LLM Era.” **PVLDB Vol. 18, 2025.**  
  - LLM-generated benchmarks on real-world datasets (1GB–220GB); relevant for scale of query results in evaluation.  
  - [VLDB](https://www.vldb.org/pvldb/vol18/p4144-schmidt.pdf)
- **Lei, F., et al. (2025).** “Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows.” **ICLR 2025.**  
  - **632** enterprise-style tasks, real-world DBs (e.g. Snowflake/BigQuery/SQLite variants), **very large schemas** and **long, multi-step SQL workflows**; stresses that naive text-to-SQL benchmarks understate production difficulty.  
  - **Relevance**: Each workflow step that **executes SQL and returns rows** is a candidate for **efficient tabular tool delivery** (your JSON vs Parquet story at warehouse scale).  
  - [OpenReview](https://openreview.net/forum?id=XmProj9cPs) · [arXiv:2411.07763](https://arxiv.org/abs/2411.07763) · [Project](https://spider2-sql.github.io/)

### Spreadsheets, code interpreters, hybrid table–text retrieval, AutoML agents

- **Li, H., Su, J., Chen, Y., Li, Q., Zhang, Z. (2023).** “SheetCopilot: Bringing Software Productivity to the Next Level through Large Language Models.” **NeurIPS 2023.**  
  - LLM agent for **spreadsheet** automation (221 tasks); **state-machine** planning (observe–propose–revise–act) over **tabular** operations.  
  - **Relevance**: Frequent tool returns over **large grids**; same serialization bottleneck as SQL result sets.  
  - [NeurIPS proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/0ff30c4bf31db0119a6219e0d250e037-Abstract-Conference.html) · [arXiv:2305.19308](https://arxiv.org/abs/2305.19308)
- **Chen, W., et al. (2021).** “Open Question Answering over Tables and Text.” **ICLR 2021.**  
  - **OTT-QA**: open-domain QA requiring retrieval and reasoning over **tables and text** (Wikipedia-scale); **peer-reviewed** benchmark for **mixed** structured/unstructured evidence.  
  - **Relevance**: When an agent **materializes** retrieved tables for downstream reasoning, **columnar bulk transfer** reduces cost vs JSON.  
  - [OpenReview](https://openreview.net/forum?id=MmCRswl1UYl) · [Project](https://ott-qa.github.io/)
- **Qiu, Z. (2025).** “OpenTable-R1: A Reinforcement Learning Augmented Tool Agent for Open-Domain Table Question Answering.” **arXiv:2507.03018.**  
  - End-to-end **agentic** table QA with **multi-turn tool calls** (BM25+ search API + **SQLite SQL executor**); RL fine-tuning (Async GRPO).  
  - **Relevance**: Each **SQL execution** returns a structured result—natural fit for **efficient tabular serialization** between tool and model.  
  - [arXiv](https://arxiv.org/abs/2507.03018) · [Code](https://github.com/TabibitoQZP/OpenTableR1)
- **Zhang, C., et al. (2024).** “CIBench: Evaluating Your LLMs with a Code Interpreter Plugin.” **arXiv:2407.10499** (also **OpenReview**; check ACL Anthology for final venue if accepted).  
  - **Interactive** IPython-style sessions for **data science** (analysis, ML, visualization); evaluates **multi-turn** tool use.  
  - **Relevance**: **DataFrame-sized** outputs recur every turn—strong motivation for **non-JSON bulk** channels.  
  - [arXiv](https://arxiv.org/abs/2407.10499) · [OpenReview](https://openreview.net/forum?id=oGzKSR7Myc)
- **Hong, S., et al. (2024).** “Data Interpreter: An LLM Agent For Data Science.” **arXiv:2402.18679** (see also **OpenReview** for venue updates).  
  - End-to-end **data science** agent (planning + code/tools); strong results on **agentic data** benchmarks.  
  - **Relevance**: **Pipeline** of executions → **large intermediate tables** and logs.  
  - [arXiv](https://arxiv.org/abs/2402.18679) · [OpenReview](https://openreview.net/forum?id=aYwHiDkAdI)
- **Hu, J., et al. (2024).** “InfiAgent-DABench: Evaluating Agents on Data Analysis Tasks.” **Proceedings of ICML 2024** (PMLR Vol. 235).  
  - **DAEval**: **603** data-analysis questions over **124** CSV files; evaluates LLM agents on **realistic data analysis** workflows.  
  - **Relevance**: Repeated tool execution with **tabular** inputs/outputs—fits §1.H and the §1.5 dataset table.  
  - [PMLR](https://proceedings.mlr.press/v235/hu24s.html) · [OpenReview](https://openreview.net/forum?id=d5LURMSfTx) · [Project](https://infiagent.github.io/)
- **Trirat, P., Jeong, W., Hwang, S. J. (2024).** “AutoML-Agent: A Multi-Agent LLM Framework for Full-Pipeline AutoML.” **arXiv:2410.02958.**  
  - Multi-agent **full-pipeline** AutoML (data retrieval through deployment); **retrieval-augmented planning**, parallel specialized agents, multi-stage verification.  
  - **Relevance**: **Repeated execution** and **tabular** artifacts (metrics, configs) exchanged between agents/tools—serialization and bandwidth matter.  
  - [arXiv](https://arxiv.org/abs/2410.02958)

### Data formats (Parquet, columnar, analytical)

- **Liu, C., Pavlenko, A., Interlandi, M., Haynes, B. (2025).** “Data formats in analytical DBMSs: performance trade-offs and future directions.” **The VLDB Journal, Springer.**  
  - **Peer-reviewed journal.** Evaluates Apache Arrow, Parquet, and ORC for analytical DBMSs; trade-offs and future directions; notes that for some ML tasks no format is optimal.  
  - DOI: [10.1007/s00778-025-00911-1](https://link.springer.com/article/10.1007/s00778-025-00911-1) (VLDB Journal, 2025; extended from VLDB 2023).
- **Zeng, X., Hui, Y., Shen, J., Pavlo, A., McKinney, W., Zhang, H. (2023).** “An Empirical Evaluation of Columnar Storage Formats.” **arXiv:2304.05028 (cs.DB).**  
  - Empirical evaluation of Parquet and ORC; recommendations for encoding, decoding speed vs compression, ML/GPU workloads. Widely cited; check for subsequent conference publication (e.g. SIGMOD/ICDE).
- **ParquetDB (NIST).** “ParquetDB: A Lightweight Database System Leveraging Apache Parquet for Efficient Data Storage and Retrieval.” **npj Computational Materials (Nature Partner Journal), 2025.**  
  - NIST publication on Parquet for complex nested records; shows Parquet’s use in structured data systems.  
  - [NIST](https://www.nist.gov/publications/parquetdb-lightweight-database-system-leveraging-apache-parquet-efficient-data-storage)

### LLM agents and tool use (efficiency, scalability)

- **ACL 2025 Findings.** “A Joint Optimization Framework for Enhancing Efficiency of Tool Utilization in LLM Agents.” **Findings of ACL 2025.**  
  - Joint optimization of tool selection and parameter generation; **efficiency of tool utilization** is central.  
  - [ACL Anthology](https://aclanthology.org/2025.findings-acl.1149/)
- **EMNLP 2024 Findings.** “Enhancing Tool Retrieval with Iterative Feedback from Large Language Models.” **Findings of EMNLP 2024.**  
  - Improves tool selection with iterative LLM feedback; tool retrieval and result handling are part of the pipeline.  
  - [ACL Anthology](https://aclanthology.org/2024.findings-emnlp.561/)
- **EMNLP 2024 Findings.** “Learning to Use Tools via Cooperative and Interactive Agents” (ConAgents). **Findings of EMNLP 2024.**  
  - Multi-agent tool selection, execution, and calibration; success rates depend on tool outputs and coordination.  
  - [ACL Anthology](https://aclanthology.org/2024.findings-emnlp.624/)
- **NeurIPS 2024.** “AvaTaR: Optimizing LLM Agents for Tool Usage via Contrastive Reasoning.” **NeurIPS 2024.**  
  - Improves tool usage in LLM agents; tool interfaces and result consumption matter for performance.  
  - [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/2db8ce969b000fe0b3fb172490c33ce8-Abstract-Conference.html)

### Agentic workloads and data systems (preprint → under review)

- **Liu, Z., Ponnapalli, S., Shankar, S., et al. (2025).** “Supporting our AI Overlords: Redesigning Data Systems for Agentic Workloads.” **arXiv:2509.00997.**  
  - UC Berkeley; introduces **agentic speculation** (high-throughput exploratory querying). Referenced by Firebolt whitepaper. Check OpenReview/venue for peer-reviewed version.  
  - [arXiv](https://arxiv.org/abs/2509.00997)

### MCP ecosystem (preprint)

- **Guo, H., Hao, Y., Zhang, Y., Xu, M., Lv, P., Chen, J., Cheng, X. (2025).** “A Measurement Study of Model Context Protocol Ecosystem.” **arXiv:2509.25292.**  
  - Large-scale MCP measurement; **response format diversity** and scalability. Check for conference submission (e.g. WWW, IMC).  
  - [arXiv](https://arxiv.org/abs/2509.25292)

---

## 5. Quick Reference: Source List


| Topic                         | Source                                              | Peer-reviewed?        | Use in narrative                                                                                                                        |
| ----------------------------- | --------------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Text-to-SQL, large DBs        | Gao et al. PVLDB’24; BIRD NeurIPS’23                | Yes                   | Token efficiency, execution over large DBs; result-set scale                                                                            |
| Enterprise SQL workflows      | Spider 2.0 ICLR’25                                  | Yes                   | Multi-step warehouse tasks; wide schemas; result scale per step                                                                         |
| Spreadsheets                  | SheetCopilot NeurIPS’23                             | Yes                   | Tabular tool loops; grid-sized outputs                                                                                                  |
| Table + text retrieval        | OTT-QA ICLR’21; OpenTable-R1 arXiv’25               | Yes / preprint        | Mixed evidence; SQL tool returns structured rows                                                                                        |
| Code interpreter / DS         | CIBench arXiv’24; Data Interpreter arXiv’24         | arXiv (+ venue check) | DataFrame-like outputs each turn                                                                                                        |
| AutoML agents                 | AutoML-Agent arXiv’24                               | Preprint              | Metrics tables, parallel agents                                                                                                         |
| Data analysis agents          | InfiAgent-DABench ICML’24                           | Yes                   | DAEval 603 Qs / 124 CSVs; code-interpreter workflow §1.H                                                                                |
| Data formats (Parquet, etc.)  | Liu et al. VLDB J.’25; Zeng et al. arXiv:2304.05028 | Yes (VLDB J.); arXiv  | Trade-offs for analytics/ML; columnar vs row-based                                                                                      |
| MCP ecosystem                 | Guo et al., arXiv:2509.25292                        | Preprint              | Response format diversity, scalability                                                                                                  |
| Agentic workloads             | Firebolt whitepaper; Berkeley arXiv:2509.00997      | Industry; preprint    | Sub-second result delivery, iteration speed                                                                                             |
| Tool use efficiency           | ACL’25 Findings; EMNLP’24; NeurIPS’24               | Yes                   | Tool utilization, retrieval; your work = result format                                                                                  |
| Table reasoning / data lakes  | TableMind, JT-DA, LEDD, OTQA                        | arXiv / venues vary   | LLMs + large tables; Parquet fits table delivery                                                                                        |
| Context / long context        | 2406.13121, “Beyond the Limits”                     | Yes (arXiv/venues)    | Reducing tool-channel payload complements long context                                                                                  |
| **Papers that do what we do** | Section 6 below                                     | Mixed                 | ATON/TOON/ZON (in-context format); NeMo #748 (truncate+store); Perplexity/Brave (reference+fetch); MemTool/Acon/dCache (context/memory) |


**For a “Related Work” paragraph:** Prefer **Gao et al. (PVLDB’24)**, **BIRD (NeurIPS’23)**, **Liu et al. (VLDB Journal’25)**, and **ACL/EMNLP/NeurIPS** tool-use papers as peer-reviewed citations; add Berkeley/MCP preprints with a note (“under review” or “preprint”) if your venue allows.

---

## 6. Papers and Systems That Do What We Do (Efficient Delivery of Large Tool Outputs)

This section lists work that **directly** addresses: (1) efficient representation of large structured tool results for LLM/agents, (2) alternatives to inline JSON (token-optimized text, truncation+storage, reference/URL), or (3) control-plane vs data-plane separation for large payloads. Use these to position your contribution: you provide **protocol-level** design (MCP + Parquet over HTTP) and **benchmarks** (bytes, latency, time-to-first-rows), whereas most prior work is either **in-context format** (token-optimized text) or **truncation + external storage** without a standard data plane.

### 6.1 Token-optimized text formats (same goal: smaller payload, still in-context)


| Source                                      | What they do                                                                                                                                               | Relevance to you                                                                                                                                                                                                                                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **ATON (Adaptive Token-Oriented Notation)** | Whitepaper + lib: text serialization for LLMs; **56% token reduction vs JSON**; "Structured Tool Outputs" for agent tools; RAG, multi-agent, streaming.    | Same problem (JSON bloat). They keep data **in the prompt** in a compact text format; you move **bulk data off-channel** (Parquet over HTTP). Complementary: ATON for small/medium in-context; your approach for large tables.                                                             |
| **TOON (Token-Optimated Output Notation)**  | Formal byte-efficiency analysis vs JSON; **tabular arrays** are the best case (declare columns once, stream rows). Used by SochDB for agent-facing output. | [TOON vs JSON](https://toonformat.dev/reference/efficiency-formalization.html), [ResearchGate](https://www.researchgate.net/publication/397903673_TOON_vs_JSON_A_Mathematical_Evaluation_of_Byte_Efficiency_in_Structured_Data). Same "avoid JSON verbosity" goal; text-based, in-context. |
| **SochDB + TOON**                           | AI-native DB with **columnar storage** and **TOON** output; token budgeting, projection pushdown; MCP server.                                              | Already in Section 2. They optimize **what goes in context** (columnar + TOON); you optimize **how large results are delivered** (descriptor + Parquet URL).                                                                                                                               |
| **ZON**                                     | LLM-oriented format; benchmarks report **7.7–19.3% token savings** vs JSON.                                                                                | [ZON benchmarks](https://zonformat.org/docs/benchmarks). Another in-context format; your work is orthogonal (out-of-band data plane).                                                                                                                                                      |


### 6.2 Truncation + storage / reference instead of inline


| Source                                                        | What they do                                                                                                                                                                                                         | Relevance to you                                                                                                                                                                                                    |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **NVIDIA NeMo Agent Toolkit (Issue #748)**                    | **Large Tool Context Management**: opt-in truncation (`max_tool_response_chars`); truncated summary in context, **full output in object store**; built-in retrieval so the agent can fetch full content when needed. | Closest to your "don't put full result in the tool channel." They use **truncate + store + retrieve**; you use **descriptor + Parquet URL**. You provide a **standard data plane** (HTTP + Parquet) and benchmarks. |
| **Perplexity Agent API**                                      | Two-stage: `web_search` returns **references/URLs**; `fetch_url` retrieves full content **only when needed**.                                                                                                        | Same idea: return references first, fetch bulk on demand. You generalize to **any** large tabular result (Parquet blob/stream).                                                                                     |
| **Brave LLM Context API**                                     | Pre-extracted web content with **token budget** params (`maximum_number_of_tokens`, `maximum_number_of_tokens_per_url`).                                                                                             | Control size at delivery; you control size by **not** putting data in the control channel and by format (Parquet + streaming).                                                                                      |
| **Gantz.ai: "How to Handle Tools That Return Too Much Data"** | Pagination, hard limits at source, LIMIT clauses, head+tail truncation.                                                                                                                                              | Industry best practices; your approach (descriptor + fetch) is a **protocol-level** solution that avoids truncation loss.                                                                                           |


### 6.3 Context / memory management (reduce what goes in context)


| Source                                            | What they do                                                                                                                                         | Relevance to you                                                                                                                        |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **MemTool** (arXiv 2507.21428)                    | Short-term memory for **tool context** (which tools to keep/remove) in multi-turn MCP conversations; tool-removal ratio to avoid context saturation. | Addresses **tool definitions** and **which tools stay in context**, not **result size/format**. Your work addresses **result payload**. |
| **Acon** (arXiv 2510.00615)                       | Context **compression** for long-horizon agents (observations + history); 26–54% token reduction.                                                    | Reduces *amount* of context; you reduce *how* large results are **delivered** (out-of-band Parquet).                                    |
| **LLM-dCache** (arXiv 2406.06799)                 | Cache as callable API; LLM manages what to cache for tool-augmented agents; data access optimization.                                                | Caching to avoid re-fetching; you optimize **first-time** delivery format and channel (Parquet over HTTP).                              |
| **Efficient On-Device Agents** (arXiv 2511.03728) | Minimal tool **schemas**, just-in-time loading; 6–10× context reduction.                                                                             | Again about **tool definitions**, not **tool result** representation.                                                                   |


### 6.4 MCP and ecosystem (indirect)


| Source                                                                                       | What they do                                                                                                                        | Relevance to you                                                                                                                                                                     |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Guo et al., "A Measurement Study of Model Context Protocol Ecosystem"** (arXiv 2509.25292) | First large-scale MCP measurement (servers, clients, markets); **response format diversity** and scalability as ecosystem concerns. | Does **not** propose Parquet or a data plane; it observes that formats and scale are issues. Supports the **motivation** for standardized, efficient handling of large tool outputs. |


### 6.5 One-line summary for "Related Work"

**"Prior work on large tool outputs either keeps data in-context with token-optimized text formats (ATON, TOON, SochDB), truncates and stores full results elsewhere (NeMo #748), or returns references and fetches on demand (Perplexity, Brave); none propose a standard, protocol-level data plane for large structured results. We evaluate MCP as control plane plus Parquet over HTTP as data plane, with benchmarks on payload size, latency, and time-to-first-rows for JSON vs Parquet blob vs Parquet stream."**