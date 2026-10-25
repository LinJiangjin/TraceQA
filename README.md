# TraceQA

带溯源、带权限、可被评测证明的企业知识问答系统。**这是我面向 FDE（前沿部署工程师）岗位的主打作品集项目。**

一句话：把散落的制度文档变成能溯源、能过安全评审、能用指标证明价值的问答系统，并且部署到真实客户环境里交付。

详细设计见 [`项目设计.md`](./项目设计.md)。

---

## 快速开始

前置：**Docker Desktop**（只用它的 Postgres/pgvector 和模型服务，代码仍在本机跑）和 Python 3.11+。

```powershell
winget install Docker.DockerDesktop      # 装完按提示重启，首次启动要等它初始化完
```

装 venv（Windows 用 pyenv 的 python 建，别用别的版本的 pip 装，否则会装进 cp3xx 轮子导致
`pydantic_core` / `psycopg` 全崩 —— 见下方【常见坑】）：

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # 含 pytest

./.venv/Scripts/python.exe -c "import app.main; print('ok')"   # 冒烟：能否导入
./.venv/Scripts/python.exe -m pytest -q tests/                 # 4 个单元测试
```

### 方式 A：一键全量（最省事）

```bash
cp .env.example .env
docker compose up -d          # Postgres(pgvector) + embedder(bge-m3) + reranker + API
curl http://localhost:8000/healthz
```

首次要拉 3GB+ 权重（bge-m3 ~1.2GB、bge-reranker-v2-m3 ~2.2GB），
`docker compose logs -f reranker` 看到 ready 后精排才真正生效（没 ready 时会自动降级，不影响启动）。

### 方式 B：本机跑代码（推荐，改代码热重载）

只把依赖放容器里，API 用本机 venv 跑：

```bash
docker compose up -d db embedder reranker
```

然后**必须覆盖两个服务名**（`.env` 里写的是 compose 服务名，本机连不上）：

```powershell
$env:DATABASE_URL="postgresql+psycopg://tracingqa:tracingqa@localhost:5432/tracingqa"
$env:EMBEDDING_ENDPOINT="http://localhost:9997"
$env:RERANK_ENDPOINT="http://localhost:9998"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Git Bash 用 `export KEY=value` 三行替代上面三行。

### 方式 C：只起数据库（网络差时先跑通链路）

```bash
docker compose up -d db
```

向量会自动回退到本地哈希向量，rerank 自动降级到融合检索分，**问答链路依然能跑通**，只是检索质量差。等网络好了再补起 embedder/reranker。

### 起不来时的自检顺序

```bash
curl http://localhost:8000/healthz                                   # 1. 服务在不在
curl -H "X-User-Id: u-alice" http://localhost:8000/api/v1/me         # 2. demo 用户在不在
curl http://localhost:9997/health                                    # 3. embedder 就绪没
curl http://localhost:9998/health                                    # 4. reranker 就绪没
```

第 2 步依赖启动时的自动 seed（`app/seed.py`）：`u-alice`(employee) / `u-hr`(employee,hr) / `u-bob`(另一租户)。
只想手动灌就跑 `./.venv/Scripts/python.exe -m app.seed`。

灌入文档（本地直跑时同样要带上 DATABASE_URL 覆盖）：

```bash
# 仓库自带 sample_docs：employee/ 是普通文档，hr/ 是薪酬机密（专门用来验越权）
./.venv/Scripts/python.exe -m app.ingest.pipeline --input ./sample_docs/employee --tenant acme --acl employee
./.venv/Scripts/python.exe -m app.ingest.pipeline --input ./sample_docs/hr       --tenant acme --acl hr
```

> `--acl` 指的是「哪些角色能看到」，不是「哪些角色被限制」。
> 写成 `--acl employee,hr` 等于给所有员工开权限，越权测试就失去意义了。

查询：

```bash
curl -s http://localhost:8000/api/v1/qa \
  -H "Content-Type: application/json" \
  -H "X-User-Id: u-alice" \
  -d '{"question":"年假需要提前几天申请？"}'
```

跑评测：

```bash
./.venv/Scripts/python.exe -m evals.harness --dataset evals/dataset.yaml --variant v1-baseline
```

> `.env` 里 `LLM_API_KEY` 是空的，灌文档和检索都能跑，只有最后一步生成答案会失败。
> 填一个 DeepSeek / OpenAI 的 key 再重启即可。

### 本地模型（大陆网络必看）

TEI 启动时才去 HuggingFace 拉权重，而它的下载器要求响应带 `Content-Range`，
hf-mirror 的重定向会丢掉这个头，结果是 `Error: Could not download model artifacts` 直接退出。

所以大陆网络的正确姿势是：**宿主机先把模型下下来，再挂进容器**（compose 已经把 `./.models` 挂到 `/models`）：

```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1   # 不关 xet 会走 cas-server 报 401
./.venv/Scripts/hf.exe download BAAI/bge-m3 \
  config.json config_sentence_transformers.json modules.json sentence_bert_config.json \
  sentencepiece.bpe.model special_tokens_map.json tokenizer.json tokenizer_config.json pytorch_model.bin \
  1_Pooling/config.json --local-dir .models/bge-m3

./.venv/Scripts/hf.exe download BAAI/bge-reranker-v2-m3 \
  config.json model.safetensors sentencepiece.bpe.model special_tokens_map.json \
  tokenizer.json tokenizer_config.json --local-dir .models/bge-reranker-v2-m3
```

`.env` 里对应写 `EMBEDDING_MODEL=/models/bge-m3`、`RERANK_MODEL=/models/bge-reranker-v2-m3`。
能直连 HuggingFace 的环境把它们改回模型名（`BAAI/bge-m3`）即可，让 TEI 自己下。

`.models/` 约 4.5GB，已在 `.gitignore` 里。

---

## 前端控制台（web/）

Vite + React 19 + TypeScript 单页，**不是完整后台**，只做三件能把后端卖点讲清楚的事：

```bash
cd web
npm install
npm run dev          # http://127.0.0.1:5173
```

前提：后端 API 已在 8000 端口跑着。前端走 `/api` 同源请求，由 vite dev server 代理过去
（见 `web/vite.config.ts`），所以前端代码里没有任何硬编码端口，部署时换成 nginx 反代即可。

| 模块 | 作用 |
|---|---|
| 身份切换器 | `u-alice` / `u-hr` / `u-bob` 一键切换，同一句话立刻看到「拒答 vs 准确回答」 |
| 答案区 | `[1]` `[2]` 渲染成可点击上标，点击后对应段落高亮并滚动到可视区 |
| 来源卡片 | 标题、文件路径、rerank 分数、原文片段 |
| 审计日志 | 拉 `/api/v1/admin/qa-logs`，谁问了什么、答了什么、耗时多少 |

```
web/
  src/
    api.ts                      # fetch 封装，X-User-Id 头在这里
    types.ts                    # 与后端返回结构一一对应
    App.tsx                     # 状态编排
    components/
      IdentitySwitcher.tsx
      QuestionForm.tsx
      AnswerView.tsx            # 引用 [n] 的解析与点击
      SourceList.tsx            # 高亮 + scrollIntoView
      AuditLog.tsx
```

> `vite.config.ts` 里显式写了 `host: '127.0.0.1'`：默认的 `'localhost'` 在这台机器上
> 解析成 `[::1]`，只监听 IPv6，浏览器敲 `127.0.0.1:5173` 会打不开。

---

## 常见坑（都踩过）

| 症状 | 原因 | 处理 |
|---|---|---|
| `ImportError: cannot import name 'ArgsKwargs' from 'pydantic_core._pydantic_core'`、`psycopg: no pq wrapper available` | venv 用 3.11 建、却被别的 Python 版本的 pip 装成了 cp313 轮子 | 删掉 `.venv` 重建。D 盘 `rm` 会被安全策略拦，用 PowerShell：`Remove-Item -LiteralPath 'D:\code\TraceQA\.venv' -Recurse -Force` |
| 启动时报 `type "vector" does not exist` | pgvector 镜像里扩展已安装但未启用 | 已修：`init_db()` 第一步就 `CREATE EXTENSION IF NOT EXISTS vector` |
| `/api/v1/me` 401 或 `用户不存在` | users 表是空的，项目原本没有 seed | 已修：启动时自动灌 `u-alice` / `u-hr` / `u-bob`（生产环境不灌） |
| 所有问题都返回"未找到相关信息" | reranker 没起来时分数恒为 0，被充分性闸门全拦掉 | 已修：reranker 不可用时降级到融合检索分并放行（`RERANK_FAIL_OPEN`），阈值改成 `RERANK_MIN_SCORE` 可配 |
| rerank 一直报错 | 一个 TEI 实例只能加载一个模型，之前 reranker 指向了 embedder 那个实例 | 已修：compose 里新增独立 `reranker` 服务（宿主机 9998），协议改用 TEI 的 `POST /rerank` |
| 灌文档报 `syntax error at or near ":"` | `text()` 里的 `:metadata::jsonb` 被 SQLAlchemy 解析成"参数 + 字面量 :jsonb" | 已修：改成 `CAST(:metadata AS jsonb)` |
| 灌文档/检索报 `malformed vector literal` | `text()` 的参数不走 `Vector` 类型的 bind_processor，list 被 psycopg 转成 PG 数组 `{...}` | 已修：统一用 `app.utils.vec_literal()` 转成 `[0.1,0.2]` 再 `CAST(... AS vector)` |
| 检索报 `operator does not exist: character varying[] && text[]` | `acl` 列是 `varchar(64)[]`，和 `text[]` 没有重叠操作符 | 已修：`CAST(:roles AS varchar[])`（换成 text[] 也会让 `idx_documents_acl` 这个 GIN 索引失效） |
| 检索报 `column reference "id" is ambiguous` | `sem_raw` 里又 JOIN 了一次 `chunks`，而 `visible` 已含 chunks 的列 | 已修：把 `embedding` 提进 `visible`，`sem_raw` 不再重复 join |
| embedder/reranker 反复重启，日志 `Could not download model artifacts` | TEI 下载器要求 `Content-Range`，hf-mirror 重定向丢掉该头 | 已修：宿主机 `hf download` 到 `.models/` 再挂载（见上文）。手动下时报 `cas-server.xethub.hf.co 401` 则加 `HF_HUB_DISABLE_XET=1` |
| `docker compose up` 报 `dial tcp [2a03:...]` / `no HTTPS proxy` | `docker.io`、`ghcr.io` 在国内 DNS 被污染，直连不通 | 已修：`.env` 里 `DB_IMAGE` / `TEI_IMAGE` 指向 daocloud 镜像站，后台 `daemon.json` 配了 `registry-mirrors` |
| `pytest` 报 `WinError 5 拒绝访问` | D 盘写 `.pytest_cache` 被拦 | 加 `-p no:cacheprovider` |

---

## 这个项目的三个核心看点

### 1. 权限在检索层前置过滤

`app/retrieval/hybrid.py` 里，`tenant_id` 和 ACL 直接下推到 SQL 的 `WHERE`：

```sql
WHERE d.tenant_id = :tenant_id
  AND d.acl && :roles      -- 数组交集，GIN 索引
```

**为什么不在应用层过滤？** 先把 top-k 捞出来再筛，无权限的高相似段落会占满名额，过滤后剩下的是垃圾，答案质量直接崩塌；更糟的是这些内容可能已经被塞进 LLM 上下文，造成事实上的泄漏。

面试必问题，务必能把这段讲清楚（包括 bigram 处理中文的取舍：`to_search_text()` 必须在入库侧和查询侧保持一致）。

### 2. Evals 里包含「越权测试集」

`evals/dataset.yaml` 有四类题：常规、拒答、**越权**、Prompt 注入。

越权题是构造"普通员工问 HR 机密政策"的场景，要求**泄漏率必须为 0%**，并且 `--max-leakage 0.0` 作为 CI 硬门禁。绝大多数 RAG 作品集根本没做权限，更别说专门评测。

### 3. 评测的就是线上跑的

`app/api/qa.py` 的 `run_qa()` 同时被 HTTP 接口和 `evals/harness.py` 调用，不存在"评测逻辑和线上逻辑分叉"的问题。

---

## 目录

| 路径 | 说明 |
|---|---|
| `app/retrieval/hybrid.py` | ⭐ 混合检索 + ACL 前置过滤 + 中文 bigram 处理 |
| `app/retrieval/rerank.py` | cross-encoder 精排 + 上下文充分性闸门（拒答） |
| `app/generation/answer.py` | 带引用结构化输出 + 幻觉引用剔除 |
| `app/models.py` | 数据模型（注意 `QALog` 是审计表） |
| `evals/harness.py` | ⭐ 评测主程序 + CI 门禁 |
| `evals/dataset.yaml` | 100 题黄金集模板 |
| `app/ingest/pipeline.py` | ingestion 管线 |
| `项目设计.md` | 完整设计书（含里程碑、面试话术） |

---

## 待替换的占位实现

骨架里这几处是刻意留的最小实现，按阶段替换：

| 位置 | 现状 | 换成什么 |
|---|---|---|
| `app/embeddings.py` | 哈希向量兜底 | 本地 bge-m3（Xinference / TEI）或 OpenAI embedding |
| `app/security.py` | 本地 HMAC JWT + 演示用户头 | 真 OIDC（Keycloak / Okta / Entra ID） |
| `evals/harness.py` 的 `_dummy_embed` | 抛 NotImplementedError | 接入 `embed_texts` |
| 前端 | 无 | React/Vue 控制台 + 可嵌入 widget |
| `app/api/mcp_server.py` | 未实现 | MCP server（Anthropic JD 直接要求的交付物） |

---

## 里程碑

见 `项目设计.md` §5。M0（找客户写 spec）不要跳过 —— 那是 FDE 的一半，也是 case study 能不能讲出业务 ROI 的关键。
