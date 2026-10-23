# 安全说明

## 已实现

- `.env` 和运行数据已加入 `.gitignore`/`.dockerignore`，仓库只保留空值示例。
- CI 密钥检查不读取 `.env`，且只输出文件、行号和规则名，不打印疑似密钥值。
- JWT 使用 HS256、过期时间、issuer 校验和常量时间签名比较。
- admin/viewer RBAC 覆盖文档删除、上传、历史清理和评测等操作。
- 生产环境启用鉴权时，默认 JWT 密钥和默认管理员密码会直接使应用启动失败。
- CORS 使用明确来源列表，不允许“通配来源 + credentials”。
- 上传使用安全文件名、扩展名白名单和大小限制。
- MongoDB/MinIO 懒连接；MinIO bucket 默认不设置公共读策略。
- 日志不输出 Prompt、Token、密码或图片 URL，只记录必要的请求元数据。

## 本地完整栈的特殊设置

`docker-compose.full.yml` 为了让浏览器直接显示 MinIO 图片，显式设置了 `MINIO_PUBLIC_READ=true`，并只用于本地演示。生产环境应保持 `MINIO_PUBLIC_READ=false`，通过受鉴权的文件代理、CDN 签名或短期授权访问对象。

## 上线前清单

1. 使用密钥管理服务注入 API Key、JWT Secret 和数据库凭据，不把 `.env` 烘焙进镜像。
2. 开启 HTTPS，限制 CORS 域名，轮换管理员凭据。
3. 为 MongoDB、Milvus、MinIO 开启认证和最小权限网络策略。
4. 对上传文件做病毒扫描、PDF 解析沙箱、MIME/魔数校验和租户隔离。
5. 把内存任务状态与 FastAPI `BackgroundTasks` 替换为持久队列和 worker。
6. 增加限流、审计日志、备份恢复、依赖漏洞和镜像扫描。
7. 对联网检索内容做 Prompt Injection 防护和域名/内容可信度策略。

## 报告问题

不要在公开 Issue 中粘贴密钥、真实文档或内部地址。请先撤销泄露凭据，再通过仓库维护者提供的私密渠道报告。
