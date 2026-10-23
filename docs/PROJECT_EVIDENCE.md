# 项目证据矩阵

这份文件用于约束简历和面试表述：每一句项目能力都应能指向代码、测试、评测或演示证据。

| 能力表述 | 代码证据 | 验证证据 | 面试讲法 |
|---|---|---|---|
| 统一 FastAPI RAG API | `app/main.py`、`app/models.py` | `tests/test_api.py`、`/docs` | 文档、查询、SSE、历史、评测、健康统一入口 |
| standalone/full 双模式 | `app/standalone_rag.py`、`app/full_rag.py` | API 测试、Docker 两套 Compose | 可复现运行与真实重型链路解耦 |
| LangGraph 导入 | `processor/import_processor/main_graph.py` | full 条件测试/本地服务 | PDF/MD 路由、图片、切分、实体、向量、Milvus |
| LangGraph 查询 | `processor/query_processor/main_graph.py` | `tests/test_query_service.py`（full 条件） | 型号确认、改写、多路召回、融合、精排、回答 |
| BGE-M3 混合检索 | embedding 与 Milvus 节点 | full 环境 | 稠密负责语义、稀疏负责型号/错误码 |
| RRF + Rerank | `node_rrf.py`、`node_rerank.py` | standalone 回归、full 环境 | 本地两路 RRF，联网结果随后合并精排 |
| 引用与来源 | `node_answer_output.py`、`app/contracts.py` | API 测试、citation coverage | Prompt 编号约束 + 结构化 sources |
| 异步隔离 | `app/full_rag.py`、`web/api/query_service.py` | `tests/test_query_service.py` | 同步工作流在线程池，事件循环继续处理请求 |
| 会话历史 | Mongo 工具、统一 API | API 历史测试 | session + 时间索引，回答保存 source IDs |
| JWT/RBAC | `app/security.py` | `test_authentication_and_rbac` | viewer/admin 权限边界与生产默认密码拒绝 |
| 上传安全 | `app/main.py`、旧导入 API 加固 | `test_upload_size_limit` | 文件名、扩展名、大小三层校验 |
| 离线评测 | `app/evaluation.py`、`scripts/evaluate.py` | `reports/evaluation-standalone.json` | Recall@k、MRR、答案/引用/延迟，说明样本边界 |
| 工程质量 | Dockerfile、Compose、CI、密钥扫描 | 9 passed、79% coverage、Ruff pass | 克隆可跑、变更可回归、配置不泄密 |

## 当前可直接写入简历

- 上表已有代码与验证证据的内容。
- 8 条合成评测集上的具体指标，必须同时注明数据规模和“回归集”。

## 不应写成已完成

- 真实公司用户量、线上 QPS、生产 SLA、成本降低或业务转化。
- 大规模真实文档上的准确率。
- Kubernetes、云部署、RAGAS/LLM Judge、Celery/Kafka worker，除非后续产生代码和运行证据。
