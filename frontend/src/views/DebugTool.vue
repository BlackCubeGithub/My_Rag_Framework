<template>
  <div class="debug-tool">
    <el-row :gutter="20">
      <el-col :span="16">
        <div class="card">
          <h3>Agent 调试工具</h3>

          <el-input
            v-model="testQuery"
            type="textarea"
            :rows="3"
            placeholder="输入测试查询..."
            style="margin: 20px 0"
          />

          <div class="debug-actions">
            <el-button type="primary" @click="runFullDebug" :loading="loading">
              运行完整调试
            </el-button>
            <el-button-group>
              <el-button @click="debugStep('analyze')">分析</el-button>
              <el-button @click="debugStep('plan')">规划</el-button>
              <el-button @click="debugStep('retrieve')">检索</el-button>
              <el-button @click="debugStep('generate')">生成</el-button>
            </el-button-group>
          </div>
        </div>

        <div class="card" style="margin-top: 20px" v-if="debugResult">
          <h4>调试结果</h4>

          <el-timeline>
            <el-timeline-item
              v-for="(step, idx) in debugResult.steps"
              :key="idx"
              :type="step.status === 'success' ? 'success' : 'danger'"
              :timestamp="`${step.duration_ms.toFixed(1)}ms`"
            >
              <h5>{{ step.step }}</h5>
              <p>{{ step.status }}</p>
              <pre v-if="step.result" class="result-json">{{ JSON.stringify(step.result, null, 2) }}</pre>
              <el-alert v-if="step.error" type="error" :title="step.error" />
            </el-timeline-item>
          </el-timeline>

          <div class="total-time">
            总耗时: {{ debugResult.total_duration_ms.toFixed(1) }}ms
          </div>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="card">
          <h4>Agent 状态</h4>
          <div class="agent-state">
            <div class="state-item" v-for="(status, component) in agentState" :key="component">
              <span class="state-label">{{ component }}</span>
              <el-tag :type="status === 'ready' ? 'success' : 'warning'" size="small">
                {{ status }}
              </el-tag>
            </div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px">
          <h4>Pipeline 流程图</h4>
          <div class="pipeline-diagram">
            <div class="pipeline-step" :class="{ active: pipelineStep === 'analyze' }">
              <div class="step-icon">1</div>
              <div class="step-name">问题分析</div>
            </div>
            <div class="pipeline-arrow">-&gt;</div>
            <div class="pipeline-step" :class="{ active: pipelineStep === 'plan' }">
              <div class="step-icon">2</div>
              <div class="step-name">规划</div>
            </div>
            <div class="pipeline-arrow">-&gt;</div>
            <div class="pipeline-step" :class="{ active: pipelineStep === 'retrieve' }">
              <div class="step-icon">3</div>
              <div class="step-name">检索</div>
            </div>
            <div class="pipeline-arrow">-&gt;</div>
            <div class="pipeline-step" :class="{ active: pipelineStep === 'reflect' }">
              <div class="step-icon">4</div>
              <div class="step-name">反思</div>
            </div>
            <div class="pipeline-arrow">-&gt;</div>
            <div class="pipeline-step" :class="{ active: pipelineStep === 'generate' }">
              <div class="step-icon">5</div>
              <div class="step-name">生成</div>
            </div>
            <div class="pipeline-arrow">-&gt;</div>
            <div class="pipeline-step" :class="{ active: pipelineStep === 'verify' }">
              <div class="step-icon">6</div>
              <div class="step-name">验证</div>
            </div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px">
          <h4>快速示例</h4>
          <div class="example-list">
            <el-tag
              v-for="example in examples"
              :key="example"
              class="example-tag"
              @click="testQuery = example"
            >
              {{ example }}
            </el-tag>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { debugApi } from '@/services/api'

const testQuery = ref('')
const loading = ref(false)
const debugResult = ref(null)
const pipelineStep = ref('')

const agentState = ref({
  'generator': 'ready',
  'retriever': 'ready',
  'reranker': 'ready',
  'query_rewriter': 'ready',
  'query_analyzer': 'ready',
  'planner': 'ready',
})

const examples = [
  '什么是 RAG？',
  'RAG 和微调的区别是什么？',
  '如何优化 RAG 的检索质量？',
]

async function runFullDebug() {
  if (!testQuery.value.trim()) {
    ElMessage.warning('请输入测试查询')
    return
  }

  loading.value = true
  debugResult.value = null

  try {
    const result = await debugApi.trace({
      query: testQuery.value,
      verbose: true,
    })
    debugResult.value = result
  } catch (error) {
    ElMessage.error('调试失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

async function debugStep(step) {
  if (!testQuery.value.trim()) {
    ElMessage.warning('请输入测试查询')
    return
  }

  pipelineStep.value = step

  try {
    const result = await debugApi.step(step, testQuery.value)
    ElMessage.success(`${step} 步骤: ${result.status}`)
  } catch (error) {
    ElMessage.error(`步骤 ${step} 失败`)
  }
}
</script>

<style lang="scss" scoped>
.debug-tool {
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    h3, h4 { margin: 0 0 16px 0; }
  }
  .debug-actions {
    display: flex;
    gap: 12px;
  }
  .result-json {
    background: #f5f7fa;
    padding: 12px;
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
  }
  .total-time {
    margin-top: 16px;
    text-align: right;
    font-weight: 600;
    color: #409eff;
  }
  .agent-state {
    .state-item {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid #eee;
      &:last-child { border-bottom: none; }
      .state-label { color: #666; }
    }
  }
  .pipeline-diagram {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    .pipeline-step {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: #f5f7fa;
      border-radius: 8px;
      opacity: 0.6;
      &.active {
        background: #ecf5ff;
        opacity: 1;
        .step-icon { background: #409eff; }
      }
      .step-icon {
        width: 24px;
        height: 24px;
        background: #909399;
        color: #fff;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
      }
      .step-name { font-size: 12px; }
    }
    .pipeline-arrow { color: #909399; }
  }
  .example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    .example-tag {
      cursor: pointer;
    }
  }
}
</style>
