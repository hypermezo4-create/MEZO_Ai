# Third-party licenses

MEZO AI source is Apache-2.0. Model weights and generated binaries are not committed.

| Component | Pinned version or revision | License |
|---|---|---|
| llama.cpp | b10079 | MIT |
| Qwen3-Coder-Next | a7fbcb5c0e12d62a448eaa0e260346bf5dcc0feb | Apache-2.0 |
| GLM-4.5-Air | a24ceef6ce4f3536971efe9b778bdaa1bab18daa | MIT |
| DeepSeek-R1-Distill-Qwen-32B | 711ad2ea6aa40cfca18895e8aca02ab92df1a746 | MIT |
| Qwen3-VL-32B-Instruct | 0cfaf48183f594c314753d30a4c4974bc75f3ccb | Apache-2.0 |
| Qwen3-8B | b968826d9c46dd6066d109eabc6255188de91218 | Apache-2.0 |
| Qwen3-Embedding-8B | 1d8ad4ca9b3dd8059ad90a75d4983776a23d44af | Apache-2.0 |
| Qwen3-Reranker-8B | 77d193c791ed757ca307ee72715aa132723da912 | Apache-2.0 |
| Valkey | 8.1.3 | BSD-3-Clause |
| FastAPI | 0.116.1 | MIT |
| React | 18.2 | MIT |
| Tauri | 2.x | Apache-2.0 / MIT |
| PostgreSQL | 17 | PostgreSQL License |
| bubblewrap | distribution package | LGPL-2.0-or-later |

The deployment manifests also pin checksummed GGUF conversions. Each conversion declares the official model above as its base. See `mezo-model-server/manifests/` for exact revisions and SHA-256 values.
