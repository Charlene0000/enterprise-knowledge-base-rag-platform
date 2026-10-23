# Contributing

1. 从 `main` 创建功能分支，保持提交聚焦且不包含 `.env`、模型、运行数据或真实文档。
2. 修改检索、切分、Prompt 或排序逻辑时，同时增加测试或更新固定评测集。
3. 提交前运行：

```bash
python -m ruff check app scripts tests
python -m pytest --cov=app --cov-fail-under=75
python scripts/check_secrets.py
python scripts/evaluate.py --top-k 5
docker compose -f docker-compose.yml config --quiet
```

4. PR 中说明行为变化、验证命令、评测差异和安全影响。不要为了提高指标只修改期望答案；数据和实现变更应分别解释。
