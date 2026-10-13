# Model comparison

Best value per row in bold; ranges are min to max across repeated runs.

Same 67 cases, same code, three free models served locally by Ollama (16K context). Qwen3 4B is the
`qwen3:4b-instruct-2507` build: the default `qwen3:4b` tag is now a thinking-only model that cannot return plain
JSON, so that run was stopped and replaced. The Qwen3 4B run was made after the NaN fix described above; the other
runs were not.

| Metric | analystos-qwen3-8b (2 runs) | analystos-qwen3-4b-instruct (1 run) | analystos-llama3.1-8b (1 run) |
|---|---|---|---|
| Overall pass rate | **93.3% (92.5% to 94.0%)** | 88.1% | 67.2% |
| Numerical accuracy | **93.9%** | 81.8% | 63.6% |
| Entity accuracy | **92.6%** | **92.6%** | 66.7% |
| Computation accuracy | **92.4% (91.5% to 93.2%)** | 84.8% | 67.8% |
| Unsupported numbers in drafts | **2.4% (1.8% to 2.9%)** | 8.6% | 12.8% |
| Unsupported numbers in final answers | **0.0%** | **0.0%** | **0.0%** |
| First-pass step success | **87.6% (85.0% to 90.3%)** | 83.4% | 72.4% |
| Retry recovery | **91.7% (83.3% to 100.0%)** | 55.9% | 66.7% |
| Safety cases passed | **100.0%** | **100.0%** | **100.0%** |
| Latency p50 | 78.1s (75.4s to 80.9s) | **26.9s** | 30.7s |
| Latency p95 | 285.6s (235.7s to 335.4s) | **75.6s** | 95.0s |
| LLM calls per task | **2.73 (2.52 to 2.93)** | 3.37 | 3.52 |
| Cost per task | **$0.0000** | **$0.0000** | **$0.0000** |

What it shows: **model quality moves pass rate, not trustworthiness.** Llama 3.1 8B drafted five times more
unsupported numbers than Qwen3 8B (12.8% vs 2.4%) and passed far fewer cases, yet 0% of the numbers in its final
answers lacked evidence, and it executed no unsafe SQL. A weaker model makes AnalystOS answer less, not answer
wrongly. The small Qwen3 4B is three times faster than the 8B and loses about five points of pass rate, mostly on
numeric and multi-table questions.
