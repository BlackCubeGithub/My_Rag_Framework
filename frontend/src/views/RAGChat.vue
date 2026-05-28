<template>
  <div class="rag-chat">
    <el-row :gutter="20">
      <el-col :span="16">
        <div class="chat-container">
          <div class="chat-header">
            <h3>Agentic RAG 对话</h3>
          </div>

          <div class="chat-messages" ref="messagesRef">
            <div v-if="messages.length === 0" class="empty-state">
              <el-icon :size="64" color="#409eff"><ChatDotRound /></el-icon>
              <p>开始对话吧！</p>
              <div class="example-queries">
                <el-tag
                  v-for="q in exampleQueries"
                  :key="q"
                  class="query-tag"
                  @click="sendQuery(q)"
                >
                  {{ q }}
                </el-tag>
              </div>
            </div>

            <div v-else>
              <div
                v-for="(msg, index) in messages"
                :key="index"
                class="message"
                :class="msg.role"
              >
                <div class="message-avatar">
                  <el-avatar>
                    {{ msg.role === 'user' ? 'U' : 'AI' }}
                  </el-avatar>
                </div>
                <div class="message-content">
                  <div class="message-text" v-html="formatMessage(msg.content)"></div>
                  <div v-if="msg.sources && msg.sources.length > 0" class="sources-panel">
                    <div class="sources-header" @click="msg.showSources = !msg.showSources">
                      <el-icon><Document /></el-icon>
                      <span>引用来源 ({{ msg.sources.length }})</span>
                      <el-icon><ArrowDown /></el-icon>
                    </div>
                    <div v-if="msg.showSources" class="sources-list">
                      <div
                        v-for="(source, idx) in msg.sources"
                        :key="idx"
                        class="source-item"
                      >
                        <span class="source-index">[{{ idx + 1 }}]</span>
                        <span class="source-text">{{ source.text }}</span>
                        <span class="source-score">得分: {{ (source.score * 100).toFixed(1) }}%</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="msg.metadata" class="message-meta">
                    <el-tag size="small" type="info">{{ msg.metadata.query_type }}</el-tag>
                    <span class="meta-item">检索轮次: {{ msg.metadata.retrieval_rounds }}</span>
                    <span class="meta-item">反思轮次: {{ msg.metadata.reflection_rounds }}</span>
                    <span class="meta-item">耗时: {{ msg.metadata.total_latency_ms }}ms</span>
                  </div>
                </div>
              </div>

              <div v-if="loading" class="message assistant loading">
                <div class="message-avatar">
                  <el-avatar>AI</el-avatar>
                </div>
                <div class="message-content">
                  <div class="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="chat-input">
            <el-input
              v-model="inputQuery"
              type="textarea"
              :rows="2"
              placeholder="输入你的问题..."
              @keyup.enter.ctrl="sendMessage"
            />
            <el-button
              type="primary"
              :loading="loading"
              @click="sendMessage"
              :disabled="!inputQuery.trim()"
            >
              发送
            </el-button>
          </div>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="config-panel">
          <div class="card">
            <h4>检索配置</h4>
            <el-form label-width="100px" size="small">
              <el-form-item label="Top-K">
                <el-slider v-model="config.topK" :min="1" :max="50" :step="1" show-stops />
              </el-form-item>
              <el-form-item label="混合检索权重">
                <el-slider v-model="config.alpha" :min="0" :max="1" :step="0.1" show-input />
              </el-form-item>
              <el-form-item label="启用反思">
                <el-switch v-model="config.enableReflection" />
              </el-form-item>
              <el-form-item label="启用验证">
                <el-switch v-model="config.enableVerification" />
              </el-form-item>
            </el-form>
          </div>

          <div class="card" style="margin-top: 16px;">
            <h4>Agent 统计</h4>
            <div class="stats">
              <div class="stat-item">
                <span class="stat-label">当前对话数</span>
                <span class="stat-value">{{ messages.length / 2 }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">平均反思轮次</span>
                <span class="stat-value">{{ avgReflectionRounds }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">平均响应时间</span>
                <span class="stat-value">{{ avgLatency }}ms</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Document, ArrowDown, UserFilled, Service } from '@element-plus/icons-vue'
import { ragApi } from '@/services/api'

const messages = ref([])
const inputQuery = ref('')
const loading = ref(false)
const messagesRef = ref(null)

const config = ref({
  topK: 10,
  alpha: 0.5,
  enableReflection: true,
  enableVerification: true,
})

const exampleQueries = [
  '什么是 RAG？',
  'RAG 和传统检索有什么区别？',
  '如何优化 RAG 的检索质量？',
]

const avgReflectionRounds = computed(() => {
  const completed = messages.value.filter(m => m.metadata?.reflection_rounds)
  if (completed.length === 0) return '0'
  const total = completed.reduce((sum, m) => sum + m.metadata.reflection_rounds, 0)
  return (total / completed.length).toFixed(1)
})

const avgLatency = computed(() => {
  const completed = messages.value.filter(m => m.metadata?.total_latency_ms)
  if (completed.length === 0) return '0'
  const total = completed.reduce((sum, m) => sum + m.metadata.total_latency_ms, 0)
  return Math.round(total / completed.length)
})

async function sendMessage() {
  if (!inputQuery.value.trim() || loading.value) return

  const query = inputQuery.value.trim()
  inputQuery.value = ''

  messages.value.push({
    role: 'user',
    content: query,
    sources: [],
    metadata: null,
  })

  loading.value = true
  scrollToBottom()

  try {
    const response = await ragApi.query({
      query,
      enable_reflection: config.value.enableReflection,
      enable_verification: config.value.enableVerification,
      top_k: config.value.topK,
    })

    messages.value.push({
      role: 'assistant',
      content: response.answer,
      sources: response.sources || [],
      metadata: response.metadata || {},
      showSources: false,
    })

  } catch (error) {
    ElMessage.error('查询失败: ' + (error.message || '未知错误'))
    messages.value.push({
      role: 'assistant',
      content: '抱歉，发生了错误。请稍后重试。',
      sources: [],
      metadata: null,
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function sendQuery(query) {
  inputQuery.value = query
  sendMessage()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function formatMessage(content) {
  if (!content) return ''
  return content
    .replace(/\[来源(\d+)\]/g, '<span class="citation">[$1]</span>')
    .replace(/\n/g, '<br>')
}
</script>

<style lang="scss" scoped>
.rag-chat {
  height: calc(100vh - 120px);
}

.chat-container {
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.chat-header {
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  h3 { margin: 0; }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  p { margin: 16px 0; color: #666; }
  .example-queries {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: center;
    .query-tag {
      cursor: pointer;
    }
  }
}

.message {
  display: flex;
  margin-bottom: 20px;
  &.user { flex-direction: row-reverse; }
  &.assistant { flex-direction: row; }
}

.message-content {
  max-width: 70%;
  margin: 0 12px;
}

.message-text {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  :deep(.citation) {
    color: #409eff;
    font-weight: bold;
    background: #ecf5ff;
    padding: 2px 6px;
    border-radius: 4px;
  }
}

.user .message-text {
  background: #409eff;
  color: #fff;
}

.assistant .message-text {
  background: #f5f7fa;
  color: #333;
}

.sources-panel {
  margin-top: 8px;
  background: #fafafa;
  border-radius: 8px;
  overflow: hidden;
}

.sources-header {
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
  &:hover { background: #f0f0f0; }
}

.sources-list {
  padding: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.source-item {
  padding: 8px;
  border-bottom: 1px solid #eee;
  font-size: 13px;
  display: flex;
  gap: 8px;
  &:last-child { border-bottom: none; }
  .source-index { color: #409eff; font-weight: bold; }
  .source-text { flex: 1; color: #666; }
  .source-score { color: #909399; font-size: 12px; }
}

.message-meta {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 12px;
  span {
    width: 8px;
    height: 8px;
    background: #909399;
    border-radius: 50%;
    animation: typing 1.4s infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-8px); }
}

.chat-input {
  padding: 16px 20px;
  border-top: 1px solid #eee;
  display: flex;
  gap: 12px;
  :deep(.el-textarea) { flex: 1; }
}

.config-panel {
  .card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    h4 { margin: 0 0 16px 0; font-size: 14px; }
  }
  .stats {
    display: flex;
    flex-direction: column;
    gap: 12px;
    .stat-item {
      display: flex;
      justify-content: space-between;
      .stat-label { color: #666; font-size: 13px; }
      .stat-value { color: #409eff; font-weight: 600; }
    }
  }
}
</style>
