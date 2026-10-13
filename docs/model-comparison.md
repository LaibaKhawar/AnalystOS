# Model comparison

Best value per row in bold; ranges are min to max across repeated runs.

Same 67 cases, same code, four models. Three are free models served locally by Ollama (16K context) on the laptop;
Ministral 8B (`Ministral-8B-Instruct-2410`) is served by vLLM on a Modal A10G GPU (16K context), with cost estimated
from GPU-seconds of model time at the A10G rate. Qwen3 4B is the
`qwen3:4b-instruct-2507` build: the default `qwen3:4b` tag is now a thinking-only model that cannot return plain
JSON, so that run was stopped and replaced. The Qwen3 4B and Ministral 8B runs were made after the NaN fix described above; the Qwen3 8B and
Llama runs were not.

| Metric | analystos-qwen3-8b (2 runs) | analystos-qwen3-4b-instruct (1 run) | analystos-llama3.1-8b (1 run) | ministral-8b (1 run) |
|---|---|---|---|---|
| Overall pass rate | **93.3% (92.5% to 94.0%)** | 88.1% | 67.2% | 64.2% |
| Numerical accuracy | **93.9%** | 81.8% | 63.6% | 60.6% |
| Entity accuracy | **92.6%** | **92.6%** | 66.7% | 59.3% |
| Computation accuracy | **92.4% (91.5% to 93.2%)** | 84.8% | 67.8% | 61.0% |
| Unsupported numbers in drafts | **2.4% (1.8% to 2.9%)** | 8.6% | 12.8% | 17.0% |
| Unsupported numbers in final answers | **0.0%** | **0.0%** | **0.0%** | **0.0%** |
| First-pass step success | **87.6% (85.0% to 90.3%)** | 83.4% | 72.4% | 67.6% |
| Retry recovery | **91.7% (83.3% to 100.0%)** | 55.9% | 66.7% | 52.2% |
| Safety cases passed | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| Latency p50 | 78.1s (75.4s to 80.9s) | 26.9s | 30.7s | **16.5s** |
| Latency p95 | 285.6s (235.7s to 335.4s) | 75.6s | 95.0s | **40.9s** |
| LLM calls per task | **2.73 (2.52 to 2.93)** | 3.37 | 3.52 | 4.10 |
| Cost per task | **$0.0000** | **$0.0000** | **$0.0000** | $0.0064 |

What it shows: **model quality moves pass rate, not trustworthiness.** The weaker the model, the more unsupported
numbers it drafts (2.4% for Qwen3 8B up to 17.0% for Ministral 8B) and the fewer cases it passes, yet across all four
models 0% of the numbers in final answers lacked evidence, and none executed unsafe SQL. A weaker model makes
AnalystOS answer less, not answer wrongly. Speed is the other axis: on a hosted A10G the agent answers in 16 s at the
median instead of 78 s on the laptop, for about $0.006 per question. Qwen3 8B stays the default model; serving it on
the same GPU (`deploy/modal/llm_server.py`) should combine both, but has not been measured yet.