# 系统架构

## 1. 目标与边界

Zhiku 解决的是“长设备文档难检索、型号容易混淆、回答缺少证据”的问题。系统把导入和查询拆成两条 LangGraph 工作流，用统一 FastAPI 暴露文档、问答、SSE、会话、鉴权、健康检查和评测能力。

项目有两个运行模式：

- `standalone`：无外部依赖的确定性实现，用于独立运行、接口测试和离线回归。
- `full`：真实模型与数据基础设施实现，用于 PDF、多模态理解和语义 RAG。

两者共享 `app/contracts.py` 中的服务契约，API 层不依赖具体实现。

## 2. 文档导入链路

```text
FastAPI upload
  → 文件名、类型、大小校验
  → MinIO 保存原始文件
  → LangGraph 入口判断 PDF / Markdown
  → PDF 通过 MinerU 转 Markdown
  → 图片上下文理解并写入 MinIO
  → 标题感知切分与重叠窗口
  → 识别设备/商品名称
  → BGE-M3 生成 dense_vec + sparse_vec
  → Milvus 保存切片、标量元数据和两类向量
```

为什么按章节再切片：章节提供 Small-to-Big 的父上下文，子切片提高召回粒度；最终将更完整的父章节交给生成模型，避免只返回一句残缺说明。

## 3. 查询链路

```text
用户问题与 session_id
  → 型号识别/歧义确认
  → 结合会话历史改写问题
  ├─ 普通 BGE-M3 稠密/稀疏混合检索
  ├─ HyDE 假设答案的混合检索
  └─ 联网检索
  → RRF 只融合两路本地名单
  → 合并联网结果
  → Qwen3 Rerank 统一阅读问题与候选文档
  → 分数断崖动态截断
  → LLM 基于编号上下文回答并给出 [n] 引用
  → JSON/SSE 返回来源，MongoDB 保存历史
```

这里必须讲准确：联网结果没有进入 RRF。RRF 处理普通本地检索与 HyDE 本地检索，随后再将联网结果与本地 RRF 结果合并，交给 Reranker。

## 4. RRF 与 Reranker 的职责

RRF 只使用“名次”，不直接比较不同检索器不可比的原始分数：

```text
score(d) = Σ weight_i / (k + rank_i(d))
```

同一切片在多路名单中排名越靠前，融合分越高。Reranker 则把“用户问题 + 每个候选文档”重新配对打分，解决纯名次融合无法判断语义细节的问题。

## 5. 数据组件分工

| 组件 | 保存内容 | 为什么不用同一个数据库 |
|---|---|---|
| Milvus | 文档切片、dense/sparse 向量、检索元数据 | 面向 ANN 和混合向量检索 |
| MongoDB | 会话消息、改写问题、来源 ID、图片 URL | 消息结构灵活，适合按 session + 时间查询 |
| MinIO | PDF/Markdown 原文件和解析图片 | 大对象存储比数据库二进制字段更合适 |

这不是“数据库混乱”，而是按访问模式选择存储。统一 API 和 `document_id/session_id/source_id` 负责跨组件关联。

## 6. 异步边界

FastAPI 路由是协程；原 LangGraph、PyMongo、Milvus/MinIO SDK 和模型调用大多是同步阻塞代码。非流式完整工作流使用：

```python
final_state = await asyncio.to_thread(workflow.run, init_state, False)
```

含义是：同步 `workflow.run` 在线程池线程执行，当前请求协程暂停并把事件循环控制权交回；进程仍可调度其他协程。它没有把同步函数“自动改造成异步算法”，也不适合无限量 CPU 密集任务，生产中仍需并发上限和独立任务队列。

## 7. 可靠性与可观测性

- liveness 只证明 API 进程可响应；readiness 还检查 full 模式依赖。
- 每个请求生成或透传 `X-Request-ID`，结构化日志记录路径、状态和耗时。
- MongoDB 与 MinIO 均为懒连接，单个依赖未启动不会阻止 standalone API 导入。
- 文档上传限制扩展名、大小和安全文件名。
- GitHub Actions 重跑 Lint、密钥扫描、测试、覆盖率、评测和 Compose 校验。

## 8. 图源

可编辑 draw.io 文件：[`assets/zhiku-architecture.drawio`](assets/zhiku-architecture.drawio)。README 中同时保留 Mermaid，保证 GitHub 可直接显示。
