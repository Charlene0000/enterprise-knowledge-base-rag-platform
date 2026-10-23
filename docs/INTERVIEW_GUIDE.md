# 简历与面试讲法

## 30 秒项目介绍

“我做了一个面向设备说明书和售后知识的企业 RAG 平台。文档经过 MinerU、图片理解和标题感知切分后，用 BGE-M3 生成稠密与稀疏向量并存入 Milvus；查询侧并行执行普通混合检索、HyDE 和联网检索，本地两路先通过 RRF 融合，再与联网结果一起进入 Qwen3 Rerank，最终生成带 `[n]` 引用的回答。工程上我统一了 FastAPI 接口，补了 JWT/RBAC、SSE、MongoDB 会话、MinIO、Docker、CI 和可复现评测，同时提供无需 Key 的 standalone 独立运行模式，让招聘方可以直接体验。”

## 建议简历表述

> 企业设备知识库与可评测 RAG 平台｜FastAPI、LangGraph、BGE-M3、Milvus、MongoDB、MinIO、Docker

- 设计文档导入与问答两条 LangGraph 工作流，完成 PDF/Markdown 解析、图片理解、标题感知切分、设备实体识别及 BGE-M3 稠密/稀疏向量入库。
- 实现普通混合检索与 HyDE 双路本地召回，使用 RRF 融合后合并联网结果，再通过 Qwen3 Rerank 动态截断，返回带 `[n]` 引用的结构化来源。
- 统一 FastAPI 文档/查询/SSE/会话接口，通过 `asyncio.to_thread()` 隔离同步重型工作流，并补充 JWT/RBAC、上传校验、健康检查和结构化日志。
- 构建 8 条合成问题的离线回归集，记录 Recall@5、MRR、关键词覆盖、引用覆盖和 P50/P95 延迟；用 pytest、Ruff、Docker Compose 与 GitHub Actions 固化质量门槛。

注意：当前 1.0 指标只属于 8 条合成回归数据，不要说成“线上准确率 100%”；完整外部服务集成没有在公开 CI 中运行，不要说成“所有生产依赖测试通过”。

## 高频追问

### 为什么同时使用稠密和稀疏检索？

稠密向量擅长语义近似，例如“温度太高怎么办”；稀疏向量更容易命中型号、错误码和专有词，例如 `HAK-180`、`E07`。BGE-M3 同时产生两类表示，Milvus 使用混合检索和加权排序，能兼顾语义与精确词匹配。

### RRF 与 Reranker 有什么区别？

RRF 只看不同召回列表中的名次，优点是无需校准各路分数；Reranker 会把用户问题和候选文档重新配对阅读，判断细粒度相关性。项目先用 RRF 降低候选集合偏差，再用 Reranker 做二阶段精排。

### HyDE 为什么可能有效，也为什么有风险？

HyDE 先生成一个假设性答案，再用它做检索，能补足用户短问题中的语义信息；但假设答案可能包含错误事实，因此它只能用于召回，不能直接作为最终证据。项目把 HyDE 结果与普通检索通过 RRF 融合，最终仍要求真实文档和引用。

### 为什么不是所有三路都进 RRF？

当前代码中，普通与 HyDE 都返回结构相同的本地切片，适合按 `chunk_id` 去重融合；联网结果是 URL、标题和摘要，先单独保留，再与本地 RRF 结果进入统一 Reranker。面试时要按真实代码讲，不能说“三路都做 RRF”。

### `await asyncio.to_thread()` 到底发生了什么？

`workflow.run` 是同步阻塞函数。`to_thread` 把它交给线程池，当前请求协程在 `await` 处暂停，事件循环可以继续处理其他协程；线程完成后，协程恢复并取得最终 State。它不等于新进程，也不会让 CPU 密集 Python 代码自动并行。

### 为什么用 Milvus、MongoDB、MinIO 三个存储？

Milvus负责向量和切片召回，MongoDB负责按会话和时间组织消息，MinIO负责 PDF 和图片大对象。它们服务不同访问模式，通过业务 ID 关联，不是随意堆数据库。

### 如何证明项目质量？

可演示证据包括统一 Swagger 和 `/app` 页面；代码证据包括 API、鉴权、两条工作流和安全配置；测试证据包括 10 个轻量测试、79% app 覆盖率和 CI；效果证据包括固定 JSONL 数据集与可重跑报告。最重要的是说明数据规模和指标边界。

## 面试演示顺序（3 分钟）

1. 打开 `/app`，提问一个型号+参数问题，指出回答中的 `[1]` 与右侧来源。
2. 提问一个错误码，说明稀疏词匹配和 Reranker 的价值。
3. 打开 `/docs`，展示 query、stream、documents、history、evaluation、health。
4. 打开 `reports/evaluation-standalone.json` 和 CI，强调“可重复证据”而不是口头指标。
5. 最后展示架构图，准确说出联网检索在 RRF 之后合并。

## 诚实边界

- standalone 使用确定性哈希稠密向量、BM25 和抽取式答案；BGE-M3/LLM 能力属于 full 模式。
- 统一 SSE 会立即返回 accepted 事件，但答案 delta 在同步工作流结束后输出；原始 full 查询服务保留模型逐 Token 推送。
- FastAPI `BackgroundTasks` 是进程内任务，不保证进程重启后的可靠执行。
- 线上规模、真实用户量、成本下降和性能提升没有证据时不要写进简历。
