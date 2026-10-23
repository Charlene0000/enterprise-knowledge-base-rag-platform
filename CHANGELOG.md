# Changelog

## 1.0.0 - 2026-08-19

- 增加统一 FastAPI 入口与 standalone/full 双运行模式。
- 完成文档、问答、SSE、历史、JWT/RBAC、健康检查和评测 API。
- 增加无密钥独立运行模式、3 份合成手册和 8 条固定评测集。
- 修复非流式 LangGraph State 处理、同步工作流阻塞事件循环和 Reranker 分数映射问题。
- 为 full 链路补充结构化来源、`[n]` 引用约束与 MongoDB 来源持久化。
- 将 MongoDB、MinIO 改为懒连接，增加上传、CORS、对象存储和密钥安全基线。
- 增加 Docker/Compose、GitHub Actions、Ruff、pytest 覆盖率门槛和项目文档。
