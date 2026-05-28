# My RAG Framework

> 基于 Agentic RAG + 多模态 + 全链路可观测性的企业知识库问答系统

## 项目简介

这是一个面向面试的 RAG 工程展示项目，展示了以下核心技术能力：

- **Agentic RAG**：问题分析 + 多跳推理 + 反思机制 + 答案验证
- **多模态 RAG**：文本 + 图片 + PDF 表格/版面分析
- **高级检索**：混合检索 (BM25 + Vector) + Cross-Encoder 重排序 + Query 改写
- **全链路可观测性**：内置调试工具 + 独立 Trace/Metrics 平台

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 后端                            │
├─────────────────────────────────────────────────────────────┤
│  Agentic RAG 核心  │  多模态处理  │  高级检索  │  可观测性  │
│  - Query Analyzer  │  - Document   │  - Hybrid │  - Trace   │
│  - Planner         │    Parser     │    Search │  - Metrics │
│  - Reflector       │  - Text       │  - BM25   │  - Debug   │
│  - Verifier        │    Chunker   │  - Rerank │            │
│  - Orchestrator    │  - Image Proc│  - Query  │            │
│                    │  - Table Ext │    Rewrite│            │
└─────────────────────────────────────────────────────────────┘
```

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI |
| LLM | DeepSeek / GPT-4 |
| Embedding | BGE-large-zh |
| 向量数据库 | Chroma / Qdrant |
| 前端 | Vue 3 + Element Plus + ECharts |
| 可观测性 | OpenTelemetry |

## 项目结构

```
My_RAG_Framework/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py           # 配置管理
│   ├── api/v1/             # API 路由
│   │   ├── rag.py          # RAG 对话接口
│   │   ├── ingest.py       # 文档上传接口
│   │   └── observability.py # 可观测性接口
│   ├── core/
│   │   ├── agent/         # Agentic RAG 核心
│   │   │   ├── orchestrator.py  # 状态机编排
│   │   │   ├── planner.py      # 多跳规划器
│   │   │   ├── reflector.py     # 反思机制
│   │   │   └── verifier.py      # 答案验证器
│   │   ├── retrieval/      # 高级检索
│   │   │   ├── hybrid_retriever.py
│   │   │   ├── reranker.py
│   │   │   └── query_rewriter.py
│   │   ├── multimodal/     # 多模态处理
│   │   │   ├── document_parser.py
│   │   │   ├── image_processor.py
│   │   │   └── table_extractor.py
│   │   └── generation/     # 生成模块
│   ├── observability/      # 可观测性
│   │   ├── rag_trace.py
│   │   ├── evaluator.py
│   │   └── debug_panel.py
│   └── core/storage/       # 存储模块
│
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── views/          # 页面视图
│       │   ├── RAGChat.vue
│       │   ├── DocManage.vue
│       │   ├── TraceDebug.vue
│       │   ├── MetricsPanel.vue
│       │   └── DebugTool.vue
│       └── services/       # API 服务
│
├── scripts/
│   ├── download_models.py  # 模型下载脚本
│   └── setup_env.py        # 环境安装脚本
│
└── configs/               # 配置文件
```

## 快速开始

### 1. 安装依赖

```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install
```

### 2. 配置环境变量

```bash
# 创建 .env 文件
cp .env.example .env

# 编辑配置
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4-turbo
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

### 3. 下载 AI 模型

首次运行前需要下载模型。默认从 HuggingFace 镜像（`hf-mirror.com`，国内速度快）下载，之后会缓存到本地：

```bash
# 下载所有模型（Embedding + Reranker）
python scripts/download_models.py

# 或一键安装环境 + 下载模型
python scripts/setup_env.py
```

> 注意：首次下载模型需要网络连接，Embedding + Reranker 模型总大小约 1.5GB。下载后会自动缓存在 `./models/` 目录。

### 4. 启动服务

```bash
# 启动后端（从项目根目录运行，不要 cd backend）
uvicorn backend.main:app --reload --port 8000

# 启动前端 (新终端)
cd frontend && npm run dev
```

### 5. 访问应用

- 前端界面: http://localhost:3000
- API 文档: http://localhost:8000/docs

## 核心功能演示

### Agentic RAG Pipeline

```
用户问题
    │
    ▼
┌──────────────┐
│ Query Analyzer │ ──► 问题分类（简单/多跳/模糊）
└──────────────┘
    │
    ▼
┌──────────────┐
│   Planner    │ ──► 多跳推理规划
└──────────────┘
    │
    ▼
┌──────────────┐
│   Retrieval  │ ──► 混合检索 + 重排序
└──────────────┘
    │
    ▼
┌──────────────┐
│  Reflector   │ ◄──► 反思机制（置信度评估）
└──────────────┘
    │
    ▼
┌──────────────┐
│  Generator   │ ──► LLM 生成答案
└──────────────┘
    │
    ▼
┌──────────────┐
│   Verifier   │ ──► 答案验证
└──────────────┘
    │
    ▼
  最终答案 + 引用来源
```

### 高级检索策略

1. **Query 改写**: 扩展、同义词、分解
2. **混合检索**: BM25 + 向量检索 + RRFS 融合
3. **重排序**: Cross-Encoder 二次精排

## API 接口

### RAG 对话

```bash
POST /api/v1/rag/query
{
  "query": "RAG 是什么？",
  "enable_reflection": true,
  "enable_verification": true,
  "top_k": 10
}
```

### 文档上传

```bash
POST /api/v1/ingest/upload
Content-Type: multipart/form-data
file: <file>
chunk_size: 512
chunk_overlap: 128
```

### 可观测性

```bash
# 获取追踪详情
GET /api/v1/observability/traces/{trace_id}

# 获取仪表盘
GET /api/v1/observability/dashboard

# 获取指标
GET /api/v1/observability/metrics
```

## 面试亮点

1. **自研状态机编排**: 不依赖 LangChain，体现架构设计能力
2. **Agentic RAG**: 反思机制 + 多跳推理，对标前沿方向
3. **多模态处理**: PDF 表格提取 + 图片理解
4. **全链路可观测性**: 完整的 Trace + Metrics + Debug 体系
5. **工程完备**: FastAPI + Vue + Docker 一键部署

## License

MIT
