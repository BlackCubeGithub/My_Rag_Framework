<template>
  <div class="trace-debug">
    <el-row :gutter="20">
      <el-col :span="18">
        <div class="card">
          <div class="section-header">
            <h3>链路追踪</h3>
            <el-button @click="refreshTraces">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>

          <el-table :data="traces" v-loading="loading" stripe>
            <el-table-column prop="trace_id" label="Trace ID" width="120">
              <template #default="{ row }">
                <code>{{ row.trace_id }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="query" label="查询" min-width="200" show-overflow-tooltip />
            <el-table-column prop="query_type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag :type="getTypeColor(row.query_type)" size="small">
                  {{ row.query_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reflection_rounds" label="反思轮次" width="100" />
            <el-table-column prop="total_latency_ms" label="延迟(ms)" width="100" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="viewTrace(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="pagination.page"
            :page-size="pagination.limit"
            :total="pagination.total"
            layout="total, prev, pager, next"
            @current-change="fetchTraces"
            style="margin-top: 16px; justify-content: flex-end"
          />
        </div>
      </el-col>

      <el-col :span="6">
        <div class="card">
          <h4>查询类型分布</h4>
          <div class="type-stats">
            <div class="type-item" v-for="(count, type) in queryTypeStats" :key="type">
              <span class="type-label">{{ type }}</span>
              <el-progress :percentage="getPercentage(count)" :color="getTypeColor(type)" />
              <span class="type-count">{{ count }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- Trace Detail Dialog -->
    <el-dialog v-model="showTraceDialog" title="Trace 详情" width="1000px" destroy-on-close>
      <div v-if="currentTrace" class="trace-detail">

        <!-- Basic Info -->
        <el-descriptions :column="2" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="Trace ID">
            <code>{{ currentTrace.trace_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="查询类型">
            <el-tag :type="getTypeColor(currentTrace.query_type)" size="small">
              {{ currentTrace.query_type }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="时间">
            {{ formatDate(currentTrace.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="总延迟">
            {{ currentTrace.total_latency_ms?.toFixed(1) || '-' }} ms
          </el-descriptions-item>
        </el-descriptions>

        <!-- State History Timeline -->
        <div class="detail-section">
          <h5>状态历史</h5>
          <el-timeline v-if="currentTrace.state_history?.length">
            <el-timeline-item
              v-for="(s, idx) in currentTrace.state_history"
              :key="idx"
              :timestamp="formatTimestamp(s.timestamp)"
              placement="top"
              size="small"
            >
              <strong>{{ s.from }}</strong> → <strong>{{ s.to }}</strong>
            </el-timeline-item>
          </el-timeline>
          <div v-else class="empty-hint">无状态历史</div>
        </div>

        <!-- Stage Latencies -->
        <div class="detail-section" v-if="currentTrace.stage_latencies && Object.keys(currentTrace.stage_latencies).length">
          <h5>各阶段延迟</h5>
          <el-row :gutter="12">
            <el-col :span="8" v-for="(ms, stage) in currentTrace.stage_latencies" :key="stage">
              <div class="latency-chip">
                <span class="stage-name">{{ stageLabel(stage) }}</span>
                <span class="stage-ms">{{ typeof ms === 'number' ? ms.toFixed(1) : ms }} ms</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- Query Analysis -->
        <div class="detail-section" v-if="currentTrace.query_analysis && Object.keys(currentTrace.query_analysis).length">
          <h5>Query Analysis</h5>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="类型">
              <el-tag size="small">{{ currentTrace.query_analysis.query_type }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="需要推理">
              <el-tag size="small" :type="currentTrace.query_analysis.requires_reasoning ? 'warning' : 'success'">
                {{ currentTrace.query_analysis.requires_reasoning ? '是' : '否' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="建议策略" :span="2">
              {{ currentTrace.query_analysis.suggested_approach || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="实体" v-if="currentTrace.query_analysis.entities?.length">
              <el-tag v-for="e in currentTrace.query_analysis.entities" :key="e" size="small" style="margin-right: 4px">{{ e }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="关键概念" v-if="currentTrace.query_analysis.key_concepts?.length">
              <el-tag v-for="c in currentTrace.query_analysis.key_concepts" :key="c" size="small" type="info" style="margin-right: 4px">{{ c }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- Planning -->
        <div class="detail-section" v-if="currentTrace.planning && Object.keys(currentTrace.planning).length">
          <h5>检索规划</h5>
          <div class="info-row">
            <span class="label">Plan Type:</span>
            <el-tag size="small">{{ currentTrace.planning.plan_type }}</el-tag>
            <span class="label" style="margin-left: 16px">Strategy:</span>
            <span>{{ currentTrace.planning.final_strategy || '-' }}</span>
          </div>
          <div v-if="currentTrace.planning.reasoning" class="info-row" style="margin-top: 8px">
            <span class="label">Reasoning:</span>
            <span>{{ currentTrace.planning.reasoning }}</span>
          </div>
          <div v-if="currentTrace.planning.steps?.length" style="margin-top: 8px">
            <el-table :data="currentTrace.planning.steps" size="small" border>
              <el-table-column prop="step_id" label="Step" width="60" />
              <el-table-column prop="action" label="Action" width="120" />
              <el-table-column prop="sub_query" label="Sub Query" min-width="200" show-overflow-tooltip />
              <el-table-column prop="dependencies" label="Dependencies" width="100">
                <template #default="{ row }">
                  {{ row.dependencies?.join(', ') || '-' }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- Rewritten Queries -->
        <div class="detail-section" v-if="currentTrace.rewritten_queries?.length">
          <h5>查询改写</h5>
          <el-tag v-for="(q, i) in currentTrace.rewritten_queries" :key="i" style="margin: 2px">
            {{ i + 1 }}. {{ q }}
          </el-tag>
        </div>

        <!-- Retrieval Rounds -->
        <div class="detail-section" v-if="currentTrace.retrieval_rounds?.length">
          <h5>检索详情 ({{ currentTrace.retrieval_rounds.length }} 轮)</h5>
          <el-collapse v-if="currentTrace.retrieval_rounds.length > 1">
            <el-collapse-item
              v-for="(round, idx) in currentTrace.retrieval_rounds"
              :key="idx"
              :title="`Round ${round.round_id}: ${round.sub_query?.slice(0, 60) || 'sub_query'}...`"
              :name="idx"
            >
              <div class="round-detail">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="Sub Query">{{ round.sub_query || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="Fusion">{{ round.fusion_method || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="Alpha">{{ round.alpha ?? '-' }}</el-descriptions-item>
                  <el-descriptions-item label="Latency">{{ round.latency_ms?.toFixed(1) || '-' }} ms</el-descriptions-item>
                  <el-descriptions-item label="Vector Count">{{ round.vector_count ?? '-' }}</el-descriptions-item>
                  <el-descriptions-item label="BM25 Count">{{ round.bm25_count ?? '-' }}</el-descriptions-item>
                </el-descriptions>
                <div v-if="round.reranked_chunks?.length" style="margin-top: 8px">
                  <div class="sub-label">Reranked Chunks:</div>
                  <el-table :data="round.reranked_chunks" size="small" border max-height="200">
                    <el-table-column prop="chunk_id" label="Chunk ID" width="120" show-overflow-tooltip />
                    <el-table-column prop="rerank_score" label="Rerank Score" width="120">
                      <template #default="{ row }">{{ row.rerank_score?.toFixed(4) || '-' }}</template>
                    </el-table-column>
                    <el-table-column prop="rank" label="Rank" width="60" />
                  </el-table>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
          <div v-else>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="Sub Query">{{ currentTrace.retrieval_rounds[0].sub_query || '-' }}</el-descriptions-item>
              <el-descriptions-item label="Fusion">{{ currentTrace.retrieval_rounds[0].fusion_method || '-' }}</el-descriptions-item>
              <el-descriptions-item label="Vector Count">{{ currentTrace.retrieval_rounds[0].vector_count ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="BM25 Count">{{ currentTrace.retrieval_rounds[0].bm25_count ?? '-' }}</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <!-- All Chunks -->
        <div class="detail-section" v-if="currentTrace.all_chunks?.length">
          <h5>检索 Chunks ({{ currentTrace.all_chunks.length }} 个)</h5>
          <el-table :data="currentTrace.all_chunks" size="small" border max-height="300">
            <el-table-column prop="rank" label="#" width="50" />
            <el-table-column prop="chunk_id" label="Chunk ID" width="120" show-overflow-tooltip />
            <el-table-column prop="source" label="Source" width="150" show-overflow-tooltip />
            <el-table-column prop="vector_score" label="Vector" width="80">
              <template #default="{ row }">{{ row.vector_score?.toFixed(4) || '-' }}</template>
            </el-table-column>
            <el-table-column prop="bm25_score" label="BM25" width="80">
              <template #default="{ row }">{{ row.bm25_score?.toFixed(4) || '-' }}</template>
            </el-table-column>
            <el-table-column prop="rerank_score" label="Rerank" width="80">
              <template #default="{ row }">{{ row.rerank_score?.toFixed(4) || '-' }}</template>
            </el-table-column>
            <el-table-column prop="text" label="Text" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <!-- Reflection Rounds -->
        <div class="detail-section" v-if="currentTrace.reflection_rounds_detail?.length">
          <h5>反思详情 ({{ currentTrace.reflection_rounds }} 轮)</h5>
          <el-collapse>
            <el-collapse-item
              v-for="(r, idx) in currentTrace.reflection_rounds_detail"
              :key="idx"
              :title="`Round ${idx}: ${r.decision} (confidence: ${r.confidence_score?.toFixed(2) || '-'})`"
              :name="idx"
            >
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="Decision">
                  <el-tag size="small" :type="decisionColor(r.decision)">{{ r.decision }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Confidence">{{ r.confidence_score?.toFixed(4) || '-' }}</el-descriptions-item>
                <el-descriptions-item label="Missing Aspects" :span="2" v-if="r.missing_aspects?.length">
                  <el-tag v-for="m in r.missing_aspects" :key="m" size="small" type="warning" style="margin: 2px">{{ m }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Supplementary Queries" :span="2" v-if="r.supplementary_queries?.length">
                  <div v-for="(sq, i) in r.supplementary_queries" :key="i" style="margin: 2px 0">
                    {{ i + 1 }}. {{ sq }}
                  </div>
                </el-descriptions-item>
              </el-descriptions>
              <div v-if="r.reasoning" style="margin-top: 8px; color: #666; font-size: 12px">
                {{ r.reasoning }}
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- Generation -->
        <div class="detail-section" v-if="currentTrace.generation && Object.keys(currentTrace.generation).length">
          <h5>Generation</h5>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="Model">{{ currentTrace.generation.model || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Prompt Tokens">{{ currentTrace.generation.prompt_tokens ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="Completion Tokens">{{ currentTrace.generation.completion_tokens ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="Total Tokens">{{ currentTrace.generation.total_tokens ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="Latency">{{ currentTrace.generation.latency_ms?.toFixed(1) || '-' }} ms</el-descriptions-item>
          </el-descriptions>
          <div v-if="currentTrace.generation.prompt" style="margin-top: 8px">
            <div class="sub-label">Prompt:</div>
            <div class="code-box">{{ currentTrace.generation.prompt }}</div>
          </div>
          <div v-if="currentTrace.generation.raw_response" style="margin-top: 8px">
            <div class="sub-label">Raw Response:</div>
            <div class="code-box">{{ currentTrace.generation.raw_response }}</div>
          </div>
        </div>

        <!-- Verification -->
        <div class="detail-section" v-if="currentTrace.verification && Object.keys(currentTrace.verification).length">
          <h5>Verification</h5>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="Decision">
              <el-tag size="small" :type="decisionColor(currentTrace.verification.decision)">
                {{ currentTrace.verification.decision }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Faithfulness">
              {{ currentTrace.verification.faithfulness_score?.toFixed(4) || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="Hallucination">
              <el-tag size="small" :type="currentTrace.verification.has_hallucination ? 'danger' : 'success'">
                {{ currentTrace.verification.has_hallucination ? '是' : '否' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Citation Accuracy">
              {{ currentTrace.verification.citation_accuracy?.toFixed(4) || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="Issues" :span="2" v-if="currentTrace.verification.issues?.length">
              <el-tag v-for="issue in currentTrace.verification.issues" :key="issue" size="small" type="danger" style="margin: 2px">{{ issue }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="currentTrace.verification.revised_answer" style="margin-top: 8px">
            <div class="sub-label">Revised Answer:</div>
            <div class="code-box">{{ currentTrace.verification.revised_answer }}</div>
          </div>
        </div>

        <!-- User Query -->
        <div class="detail-section">
          <h5>用户查询</h5>
          <div class="query-box">{{ currentTrace.query }}</div>
        </div>

        <!-- Final Answer -->
        <div class="detail-section">
          <h5>生成答案</h5>
          <div class="answer-box">{{ currentTrace.answer || 'N/A' }}</div>
        </div>

        <!-- Error -->
        <div class="detail-section" v-if="currentTrace.error">
          <h5>Error</h5>
          <div class="error-box">{{ currentTrace.error }}</div>
        </div>

      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { observabilityApi } from '@/services/api'

const traces = ref([])
const loading = ref(false)
const showTraceDialog = ref(false)
const currentTrace = ref(null)

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
})

const queryTypeStats = computed(() => {
  const stats = {}
  traces.value.forEach(t => {
    const type = t.query_type || 'simple'
    stats[type] = (stats[type] || 0) + 1
  })
  return stats
})

const totalCount = computed(() => traces.value.length)

function getPercentage(count) {
  if (!totalCount.value) return 0
  return Math.round((count / totalCount.value) * 100)
}

function getTypeColor(type) {
  const colors = {
    simple: 'success',
    multi_hop: 'warning',
    ambiguous: 'danger',
  }
  return colors[type] || 'info'
}

function decisionColor(decision) {
  const map = {
    proceed: 'success',
    refine: 'warning',
    insufficient: 'danger',
    accept: 'success',
    regenerate: 'danger',
    revise: 'warning',
  }
  return map[decision] || 'info'
}

function stageLabel(stage) {
  const labels = {
    analyzing_ms: '分析',
    planning_ms: '规划',
    retrieval_ms: '检索',
    reflecting_ms: '反思',
    generating_ms: '生成',
    verifying_ms: '验证',
  }
  return labels[stage] || stage
}

async function fetchTraces() {
  loading.value = true
  try {
    const response = await observabilityApi.traces({
      skip: (pagination.value.page - 1) * pagination.value.limit,
      limit: pagination.value.limit,
    })
    traces.value = response.traces || []
    pagination.value.total = response.total || 0
  } catch (error) {
    ElMessage.error('获取追踪记录失败')
  } finally {
    loading.value = false
  }
}

async function viewTrace(row) {
  try {
    const trace = await observabilityApi.trace(row.trace_id)
    currentTrace.value = trace
    showTraceDialog.value = true
  } catch (error) {
    ElMessage.error('获取详情失败')
  }
}

function refreshTraces() {
  fetchTraces()
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatTimestamp(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

onMounted(() => {
  fetchTraces()
})
</script>

<style lang="scss" scoped>
.trace-debug {
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    h3 { margin: 0; }
  }
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    h4 { margin: 0 0 16px 0; }
  }
  .type-stats {
    .type-item {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      .type-label { width: 80px; font-size: 13px; }
      .el-progress { flex: 1; }
      .type-count { width: 40px; text-align: right; color: #666; }
    }
  }
  .trace-detail {
    max-height: 70vh;
    overflow-y: auto;
    padding-right: 4px;
    &::-webkit-scrollbar { width: 6px; }
    &::-webkit-scrollbar-thumb { background: #dcdfe6; border-radius: 3px; }
  }
  .detail-section {
    margin-bottom: 20px;
    h5 {
      margin: 0 0 10px 0;
      padding-bottom: 6px;
      border-bottom: 1px solid #ebeef5;
      font-size: 14px;
      color: #409eff;
    }
  }
  .query-box, .answer-box {
    background: #f5f7fa;
    padding: 16px;
    border-radius: 8px;
    white-space: pre-wrap;
    line-height: 1.6;
    font-size: 13px;
  }
  .code-box {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px;
    border-radius: 6px;
    white-space: pre-wrap;
    line-height: 1.5;
    font-size: 12px;
    font-family: 'Courier New', monospace;
    max-height: 200px;
    overflow-y: auto;
  }
  .error-box {
    background: #fff1f0;
    color: #cf1322;
    padding: 12px;
    border-radius: 6px;
    border: 1px solid #ffa39e;
    font-size: 13px;
    white-space: pre-wrap;
  }
  .sub-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 4px;
  }
  .info-row {
    font-size: 13px;
    .label { color: #909399; margin-right: 4px; }
  }
  .latency-chip {
    background: #f0f9eb;
    border: 1px solid #c2e7b0;
    border-radius: 6px;
    padding: 6px 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    .stage-name { font-size: 12px; color: #606266; }
    .stage-ms { font-size: 13px; font-weight: 600; color: #67c23a; }
  }
  .empty-hint {
    color: #c0c4cc;
    font-size: 13px;
    padding: 8px 0;
  }
}
</style>
