# My RAG Framework

> 基于 RAG 的企业知识库问答系统

## Project Overview

本项目是一个**面向企业知识库问答场景的 RAG（Retrieval-Augmented Generation）实践项目**，旨在构建一个完整的端到端 RAG 问答系统，涵盖文档解析、文本分块、向量检索、生成回答等核心环节。

项目重点关注以下工程实践点：

- 多格式文档（PDF/Word/Markdown/HTML）的解析与处理
- 多种分块策略的实践与对比
- 向量检索与混合检索的工程实现
- Prompt 工程与生成质量的优化
- RAG 流程各环节的效果评估

## Tech Stack

- **语言模型**: DeepSeek-V4-Pro
- **向量数据库**: Chroma
- **Embedding**: Qwen
- **框架**: LangChain
- **评估**: RAGAS

## Research Scope

| 环节 | 内容 |
|------|------|
| **Document Processing** | PDF / Word / HTML / Markdown 多格式解析、文档结构恢复 |
| **Text Chunking** | 固定窗口、递归字符分割、语义分段、基于文档结构的分块 |
| **Embedding** | 向量模型选型、中英文 Embedding 对比、向量化优化 |
| **Vector Store** | FAISS / Chroma / Milvus / pgvector 的使用与特性对比 |
| **Retrieval** | 语义检索、混合检索（BM25 + 向量）、重排序（Reranking） |
| **Generation** | Prompt 工程、上下文管理、引用标注 |
| **Evaluation** | 检索质量评估、生成质量评估、RAG 评测框架实践 |

## Target Use Cases

- 企业内部知识库问答（员工手册、政策文件等）
- 技术文档智能问答
- 合同条款检索
- 多语言文档问答

## Key Research Questions

1. 分块策略对检索召回的影响：chunk size / overlap 如何选择？
2. Embedding 模型选型：不同模型在中文场景下的效果差异
3. 检索数量与质量：top_k 如何设定，context 噪声如何控制
4. 混合检索的有效性：BM25 + 向量检索是否优于单一方案
5. Reranking 的价值：粗召回后引入重排序能否提升准确率
6. Prompt 设计：模板优化、少样本示例对生成效果的影响
7. 幻觉问题的缓解：如何通过检索结果约束生成过程
