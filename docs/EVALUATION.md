# RAG 评测说明

## 目标

评测不是为了制造一个“100% 准确率”宣传数字，而是把检索和答案质量变成可重复的回归门槛。固定数据位于 `examples/eval_dataset.jsonl`，报告位于 `reports/evaluation-standalone.json`。

## 数据格式

每行一条 JSON：

```json
{"question":"...","expected_source":"HAK-180","expected_keywords":["110℃"]}
```

当前 8 条问题覆盖型号区分、温度、预热时间、错误代码、默认地址和恢复设置。所有手册均为合成数据，不对应真实厂商。

## 指标

| 指标 | 计算口径 | 回答什么问题 |
|---|---|---|
| Recall@k | 期望来源是否出现在前 k 条 | 检索有没有找回来 |
| MRR | 第一个正确来源排名的倒数均值 | 正确来源是否靠前 |
| Answer keyword coverage | 期望关键词在答案中的覆盖率 | 核心事实有没有回答 |
| Citation coverage | 答案是否包含合法 `[n]` | 回答有没有可追溯引用 |
| Heuristic groundedness | 答案词元被来源支持的比例 | 是否大量出现来源外文本 |
| P50/P95 latency | 单次查询耗时分位数 | 确定性链路是否发生明显退化 |

`heuristic_groundedness` 只是无需模型的词元代理，不等价于 RAGAS Faithfulness、Answer Relevance 或 LLM-as-a-Judge。

## 复现

```bash
python scripts/evaluate.py --top-k 5 --output reports/evaluation-standalone.json
```

当前回归结果为 Recall@5、MRR、答案关键词覆盖、引用覆盖和启发式 groundedness 均为 1.0。这个结果只适用于当前 8 条合成数据，不能外推到真实设备文档、用户分布或 full 模式模型调用。

## 如何扩展为生产评测

1. 从真实文档构建至少 100 条人工标注问题，隔离训练/调参集与最终测试集。
2. 增加“无答案、型号冲突、多轮指代、表格、图片、跨章节”样本。
3. 同时评估 Recall@k、nDCG、MRR、Faithfulness、Answer Relevance 和拒答准确率。
4. 记录 embedding、rerank、LLM 各阶段耗时、Token 与费用。
5. 每次修改切分、Prompt、TopK 或模型时生成对比报告，并保存 Git 提交号。
