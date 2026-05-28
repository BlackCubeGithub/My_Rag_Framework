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

    <el-dialog v-model="showTraceDialog" title="Trace 详情" width="900px">
      <div v-if="currentTrace" class="trace-detail">
        <el-descriptions :column="2" border>
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
            {{ currentTrace.total_latency_ms }}ms
          </el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top: 20px">状态历史</h4>
        <el-timeline>
          <el-timeline-item
            v-for="(state, idx) in currentTrace.state_history"
            :key="idx"
            :timestamp="formatTimestamp(state.timestamp)"
            placement="top"
          >
            {{ state.from }} -> {{ state.to }}
          </el-timeline-item>
        </el-timeline>

        <h4 style="margin-top: 20px">用户查询</h4>
        <div class="query-box">{{ currentTrace.query }}</div>

        <h4 style="margin-top: 20px">生成答案</h4>
        <div class="answer-box">{{ currentTrace.answer || 'N/A' }}</div>
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
    .query-box, .answer-box {
      background: #f5f7fa;
      padding: 16px;
      border-radius: 8px;
      white-space: pre-wrap;
      line-height: 1.6;
    }
  }
}
</style>
