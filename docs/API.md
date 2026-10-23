# API 使用说明

基础地址：`http://localhost:8000`。Swagger 位于 `/docs`。

## 健康检查

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

## 获取 JWT

默认 standalone 模式关闭鉴权，不需要 Token。启用 `AUTH_ENABLED=True` 后：

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"your-admin","password":"your-password"}'
```

后续请求增加：`Authorization: Bearer <access_token>`。不要把 Token 写入代码、文档、截图或 Git。

## 文档导入

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@examples/hak180_manual.md;type=text/markdown"
```

standalone 支持 UTF-8 Markdown/TXT；full 支持 PDF/Markdown。默认最大 20 MB，可通过 `MAX_UPLOAD_MB` 调整。

## 文档列表与删除

```bash
curl http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <access_token>"

curl -X DELETE http://localhost:8000/api/v1/documents/<document_id> \
  -H "Authorization: Bearer <access_token>"
```

## 非流式问答

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"query":"HAK-180最高工作温度是多少？","session_id":"case-001","top_k":5}'
```

核心返回字段：

```json
{
  "session_id": "case-001",
  "query": "HAK-180最高工作温度是多少？",
  "rewritten_query": "HAK-180最高工作温度是多少？",
  "answer": "设备温度可调范围为50℃至180℃。[1]",
  "sources": [
    {
      "source_id": "...",
      "title": "HAK-180桌面烫金机示例操作手册",
      "section": "产品与安全",
      "snippet": "...",
      "score": 0.71,
      "source_type": "local"
    }
  ],
  "retrieval_strategy": "...",
  "latency_ms": 2.1
}
```

## SSE 问答

```bash
curl -N -X POST http://localhost:8000/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"query":"E07如何处理？","top_k":5}'
```

事件顺序为 `accepted → metadata → delta... → sources → final`；失败时发送 `error`。统一接口会先发送已受理事件，full 模式的同步工作流在线程池执行，最终答案再按 delta 事件输出。原始 full 查询服务仍保留模型逐 Token 推送实现。

## 会话历史

```bash
curl http://localhost:8000/api/v1/sessions/case-001/history \
  -H "Authorization: Bearer <access_token>"

curl -X DELETE http://localhost:8000/api/v1/sessions/case-001/history \
  -H "Authorization: Bearer <access_token>"
```

## 运行基准评测

```bash
curl -X POST http://localhost:8000/api/v1/evaluations/benchmark \
  -H "Authorization: Bearer <access_token>"
```

该端点只允许 `APP_MODE=standalone`，避免把合成数据指标误当成 full 模式线上质量。
