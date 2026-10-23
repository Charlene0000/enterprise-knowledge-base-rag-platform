# 当前简历与项目真实性对齐

本文件不直接修改 Word 简历，只记录最终项目证据和必须纠正的口径，供后续简历更新使用。

## 已有真实证据

- FastAPI 统一 API、SSE、JWT/RBAC、上传校验、健康检查和结构化日志。
- 两条 LangGraph：文档导入与问题查询。
- BGE-M3 稠密/稀疏向量、Milvus 混合检索、普通 + HyDE、本地 RRF、联网结果合并、Qwen3 Rerank。
- MinerU PDF 解析、图片理解、MinIO 对象存储、MongoDB 会话历史。
- Dockerfile、standalone/full Compose、GitHub Actions、Ruff、pytest、79% app 覆盖率。
- 8 条合成回归数据的 Recall@5、MRR、关键词覆盖、引用覆盖与启发式 groundedness 报告。

## 简历必须改正

- full 模式稀疏检索是 BGE-M3 sparse vector，不是 BM25；BM25 只属于无依赖 standalone。
- 当前真实数据栈是 Milvus + MongoDB + MinIO，不是 MySQL + Redis。
- 当前真实 Reranker 是 DashScope Qwen3 Rerank；本地 BGE Reranker 工具不是查询主链路。
- 联网结果不参加本地 RRF，而是在 RRF 后合并并进入 Reranker。
- 当前启发式 groundedness 不等于 RAGAS Faithfulness；尚不能把 Faithfulness/Answer Relevance 写成已实现。

## 仍需标记为待验证

- full Compose 的配置已通过解析，但本机 Docker Desktop 引擎未启动，镜像实构建需复验。
- 公开 CI 只运行无外部依赖测试；Milvus、MongoDB、MinIO、MinerU 和真实模型 API 的端到端集成需在 full 环境验收。
- 没有真实业务用户量、线上 QPS、SLA、成本或性能提升数据。
