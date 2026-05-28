<template>
  <div class="metrics-panel">
    <el-row :gutter="20">
      <el-col :span="6">
        <div class="metric-card">
          <div class="metric-icon" style="background: #409eff">
            <el-icon :size="32"><ChatDotRound /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ dashboard.total_queries }}</div>
            <div class="metric-label">总查询数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <div class="metric-icon" style="background: #67c23a">
            <el-icon :size="32"><CircleCheck /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ (dashboard.success_rate * 100).toFixed(1) }}%</div>
            <div class="metric-label">成功率</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <div class="metric-icon" style="background: #e6a23c">
            <el-icon :size="32"><Timer /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ Math.round(dashboard.avg_response_time_ms) }}ms</div>
            <div class="metric-label">平均响应时间</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="metric-card">
          <div class="metric-icon" style="background: #f56c6c">
            <el-icon :size="32"><Refresh /></el-icon>
          </div>
          <div class="metric-content">
            <div class="metric-value">{{ dashboard.avg_reflection_rounds?.toFixed(1) || 0 }}</div>
            <div class="metric-label">平均反思轮次</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <div class="card chart-card">
          <h4>查询类型分布</h4>
          <div ref="pieChartRef" style="height: 300px"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card chart-card">
          <h4>查询趋势</h4>
          <div ref="lineChartRef" style="height: 300px"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <div class="card">
          <h4>最近追踪</h4>
          <el-table :data="recentTraces" stripe>
            <el-table-column prop="trace_id" label="Trace ID" width="120">
              <template #default="{ row }">
                <code>{{ row.trace_id }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="query" label="查询" min-width="300" show-overflow-tooltip />
            <el-table-column prop="query_type" label="类型" width="100" />
            <el-table-column prop="total_latency_ms" label="延迟" width="100" />
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, CircleCheck, Timer, Refresh } from '@element-plus/icons-vue'
import { observabilityApi } from '@/services/api'
import * as echarts from 'echarts'

const dashboard = ref({
  total_queries: 0,
  success_rate: 0,
  avg_response_time_ms: 0,
  avg_reflection_rounds: 0,
})

const queryTypeDistribution = ref({})
const recentTraces = ref([])

const pieChartRef = ref(null)
const lineChartRef = ref(null)
let pieChart = null
let lineChart = null

async function fetchDashboard() {
  try {
    const response = await observabilityApi.dashboard()
    dashboard.value = response.overview || {}
    queryTypeDistribution.value = response.query_types || {}
    recentTraces.value = response.recent_traces || []
    updateCharts()
  } catch (error) {
    ElMessage.error('获取仪表盘数据失败')
  }
}

function updateCharts() {
  if (pieChartRef.value) {
    if (pieChart) pieChart.dispose()
    pieChart = echarts.init(pieChartRef.value)

    const data = Object.entries(queryTypeDistribution.value).map(([name, value]) => ({
      name,
      value,
    }))

    pieChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        data,
        label: { formatter: '{b}: {c} ({d}%)' },
      }],
    })
  }

  if (lineChartRef.value) {
    if (lineChart) lineChart.dispose()
    lineChart = echarts.init(lineChartRef.value)

    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`)
    const data = Array.from({ length: 24 }, () => Math.floor(Math.random() * 20))

    lineChart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: hours },
      yAxis: { type: 'value', name: '查询数' },
      series: [{
        type: 'line',
        smooth: true,
        data,
        areaStyle: { opacity: 0.3 },
      }],
    })
  }
}

onMounted(() => {
  fetchDashboard()
  window.addEventListener('resize', updateCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateCharts)
  if (pieChart) pieChart.dispose()
  if (lineChart) lineChart.dispose()
})
</script>

<style lang="scss" scoped>
.metrics-panel {
  .metric-card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    .metric-icon {
      width: 60px;
      height: 60px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .metric-content {
      .metric-value {
        font-size: 28px;
        font-weight: 600;
        color: #333;
      }
      .metric-label {
        font-size: 13px;
        color: #666;
        margin-top: 4px;
      }
    }
  }
  .chart-card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    h4 { margin: 0 0 16px 0; }
  }
}
</style>
