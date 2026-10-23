# 部署与排障

## 1. standalone 独立运行模式

适合 GitHub 展示、面试演示、API 联调和 CI。无需 GPU、模型 Key、Milvus、MongoDB 或 MinIO。

```bash
docker compose up --build
```

确认：

```bash
curl http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/documents
```

停止服务：

```bash
docker compose down
```

默认 Compose 不挂载持久卷，standalone 文档和会话随容器重启重置，这是为了保证每次运行结果一致。

## 2. 本地 Python 模式

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

测试：

```powershell
python -m ruff check app scripts tests
python -m pytest --cov=app --cov-fail-under=75
python scripts/evaluate.py --top-k 5 --output reports/evaluation-standalone.json
```

## 3. full 模式

先复制配置：

```powershell
Copy-Item .env.example .env
```

至少填写模型 API Key、MinerU Token，并修改 MinIO、JWT 和管理员默认凭据。随后：

```bash
docker compose -f docker-compose.full.yml config
docker compose -f docker-compose.full.yml up --build
```

完整栈包含 API、MongoDB、etcd、MinIO 和 Milvus。首次构建会安装 PyTorch、FlagEmbedding、Transformers 等重依赖，首次运行还可能下载 BGE-M3 模型，因此耗时和磁盘占用远大于 standalone。

## 4. 健康检查语义

- `/health/live`：API 进程能够响应。
- `/health/ready`：standalone 返回内存索引状态；full 额外检查 Milvus、MongoDB、MinIO。

`ready=degraded` 时不要把实例加入负载均衡，但可以保留进程用于排障。

## 5. 常见问题

### 端口冲突

默认使用 8000、9000、9001、19530、9091。修改 Compose 左侧宿主机端口，不要随意修改容器内服务端口和依赖地址。

### full 模式一直启动

检查镜像构建、模型下载、内存和磁盘；BGE-M3 CPU 推理可运行但速度较慢。先用 standalone 验证 API，再逐个检查 `/health/ready` 中的依赖。

### 上传 PDF 失败

确认 `APP_MODE=full`、MinerU 配置有效、文件不超过 `MAX_UPLOAD_MB`，并查看带 `X-Request-ID` 的结构化日志。

### 图片无法显示

本地 Compose 要求浏览器能访问 `MINIO_PUBLIC_ENDPOINT=localhost:9000`。生产环境不要开放整个 bucket，应使用受控文件访问层。

### Docker 警告找不到 `.env`

完整 Compose 将 `.env` 标记为可选，因此 `config` 可以在 CI 中验证；真正运行 full 前仍必须创建并填写本地 `.env`。

## 6. 生产化取舍

仓库已覆盖可展示的一体化部署，但高并发生产环境应把导入任务移到 Celery/RQ/Kafka worker，将会话和任务状态做持久化，增加网关限流、租户隔离、监控告警和备份恢复。
