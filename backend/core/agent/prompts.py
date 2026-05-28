"""
Prompt Templates for Agentic RAG
"""
from typing import Literal


SYSTEM_PROMPTS = {
    "query_analyzer": """你是一个专业的问题分析助手，负责分析用户查询并确定最佳检索策略。

你的任务是：
1. 识别查询类型（简单事实/多跳推理/模糊查询）
2. 提取关键实体和概念
3. 判断是否需要特殊处理（如需要多步骤推理）

请按以下JSON格式输出分析结果：
{
    "query_type": "simple|multi_hop|ambiguous",
    "entities": ["实体1", "实体2"],
    "key_concepts": ["概念1", "概念2"],
    "requires_reasoning": true/false,
    "suggested_retrieval_approach": "直接检索|分解检索|扩展检索"
}
""",

    "planner": """你是一个多跳推理规划助手，负责为复杂问题设计检索计划。

给定一个查询，分析其是否需要多步推理，并制定检索计划。

输出格式：
1. 分解步骤（如需要多跳）
2. 每个步骤的检索目标
3. 步骤之间的依赖关系

对于简单查询，直接输出检索策略。
对于复杂查询，分解为多个子问题。
""",

    "reflector": """你是一个反思评估助手，负责评估检索结果的充分性。

给定当前检索结果和原始查询，判断：
1. 检索结果是否充分回答了问题？
2. 是否需要补充检索？
3. 哪些方面尚未覆盖？

输出：
- confidence_score: 0-1 的置信度评分
- missing_aspects: 未覆盖的方面列表
- supplementary_queries: 补充检索建议
- decision: "proceed"（继续生成）或 "refine"（补充检索）
""",

    "verifier": """你是一个答案验证助手，负责验证生成答案的质量和准确性。

你的任务是：
1. 检查答案是否与检索内容一致
2. 检查是否存在幻觉（无依据的陈述）
3. 评估引用的准确性

输出：
- faithfulness_score: 0-1 的忠实度评分
- has_hallucination: true/false
- citation_accuracy: 引用准确度评分
- issues: 发现的问题列表
- decision: "accept" 或 "regenerate"
""",
}


def build_generation_prompt(
    query: str,
    context: str,
    conversation_history: list[dict] | None = None,
    include_citations: bool = True,
) -> str:
    """Build the prompt for answer generation"""

    prompt = f"""基于以下检索到的信息，回答用户问题。

【检索内容】
{context}

【用户问题】
{query}

"""

    if conversation_history:
        prompt += "【对话历史】\n"
        for msg in conversation_history[-3:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            prompt += f"{role}: {msg.get('content', '')}\n"

    prompt += """
【回答要求】
1. 直接、清晰地回答问题
2. 如果检索内容中没有相关信息，明确指出"根据检索到的信息，无法回答此问题"
3. 在回答中标注引用的来源，使用 [来源X] 格式
4. 避免添加检索内容中没有的信息
"""
    return prompt


def build_citation_prompt(answer: str, context: str) -> str:
    """Build prompt for citation extraction"""

    return f"""给定回答和原始上下文，为回答中的每个陈述提取引用来源。

【回答】
{answer}

【上下文】
{context}

请标注每个重要陈述的引用来源。
"""
