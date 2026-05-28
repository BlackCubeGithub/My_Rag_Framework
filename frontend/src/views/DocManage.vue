<template>
  <div class="doc-manage">
    <el-row :gutter="20">
      <el-col :span="16">
        <div class="card">
          <div class="section-header">
            <h3>文档列表</h3>
            <el-button type="primary" @click="showUploadDialog = true">
              <el-icon><Upload /></el-icon>
              上传文档
            </el-button>
          </div>

          <el-table :data="documents" v-loading="loading" stripe>
            <el-table-column prop="file_name" label="文件名" />
            <el-table-column prop="chunks_count" label="分块数" width="100" />
            <el-table-column prop="created_at" label="上传时间" width="180">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="viewChunks(row)">查看分块</el-button>
                <el-button size="small" type="danger" @click="deleteDocument(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="pagination.page"
            :page-size="pagination.limit"
            :total="pagination.total"
            layout="total, prev, pager, next"
            @current-change="fetchDocuments"
            style="margin-top: 16px; justify-content: flex-end"
          />
        </div>
      </el-col>

      <el-col :span="8">
        <div class="card">
          <h4>统计信息</h4>
          <div class="stats-grid">
            <div class="stat-box">
              <div class="stat-value">{{ stats.total_documents }}</div>
              <div class="stat-label">文档总数</div>
            </div>
            <div class="stat-box">
              <div class="stat-value">{{ stats.total_chunks }}</div>
              <div class="stat-label">分块总数</div>
            </div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px;">
          <h4>支持的格式</h4>
          <el-tag v-for="fmt in supportedFormats" :key="fmt" style="margin: 4px">
            {{ fmt }}
          </el-tag>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="showUploadDialog" title="上传文档" width="600px">
      <el-form label-width="120px">
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="10"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            accept=".pdf,.docx,.doc,.txt,.md,.html"
            multiple
            drag
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                支持 PDF、Word、Markdown、HTML、TXT 格式，单文件不超过 100MB
              </div>
            </template>
          </el-upload>
          <div v-if="uploadError" class="upload-error">{{ uploadError }}</div>
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="uploadConfig.chunkSize" :min="100" :max="2000" :step="100" />
        </el-form-item>
        <el-form-item label="重叠大小">
          <el-input-number v-model="uploadConfig.chunkOverlap" :min="0" :max="500" :step="32" />
        </el-form-item>
        <el-form-item label="分块策略">
          <el-select v-model="uploadConfig.chunkStrategy">
            <el-option label="递归字符分割" value="recursive" />
            <el-option label="固定大小分块" value="fixed" />
            <el-option label="语义分块" value="semantic" />
          </el-select>
        </el-form-item>
        <el-form-item label="集合名称">
          <el-input v-model="uploadConfig.collectionName" placeholder="documents" />
        </el-form-item>
      </el-form>
      <el-progress
        v-if="uploading"
        :percentage="uploadProgress"
        :status="uploadProgress === 100 ? 'success' : undefined"
        style="margin-top: 16px"
      />
      <template #footer>
        <el-button @click="showUploadDialog = false" :disabled="uploading">取消</el-button>
        <el-button type="primary" @click="handleUpload" :loading="uploading">
          {{ uploading ? `上传中 ${uploadProgress}%` : '开始上传' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showChunksDialog" title="文档分块" width="900px">
      <div v-if="currentChunks.length === 0" style="text-align:center; padding: 40px; color: #999;">
        暂无分块数据
      </div>
      <template v-else>
        <div style="margin-bottom: 12px; color: #666; font-size: 13px;">
          共 {{ currentChunks.length }} 个分块
        </div>
        <el-input
          v-model="chunkSearch"
          placeholder="搜索分块内容"
          prefix-icon="Search"
          style="margin-bottom: 12px"
          clearable
        />
        <div class="chunks-list">
          <div
            v-for="(chunk, idx) in filteredChunks"
            :key="chunk.chunk_id"
            class="chunk-item"
          >
            <div class="chunk-header">
              <span class="chunk-index">#{{ idx + 1 }}</span>
              <span class="chunk-id">{{ chunk.chunk_id?.slice(0, 8) }}...</span>
              <span class="chunk-chars">{{ (chunk.text || '').length }} 字</span>
            </div>
            <div class="chunk-text">{{ (chunk.text || '').slice(0, 500) }}{{ (chunk.text || '').length > 500 ? '...' : '' }}</div>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Search, UploadFilled } from '@element-plus/icons-vue'
import { ingestApi } from '@/services/api'

const uploadRef = ref(null)
const selectedFiles = ref([])
const documents = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const showUploadDialog = ref(false)
const showChunksDialog = ref(false)
const currentChunks = ref([])
const chunkSearch = ref('')
const uploadError = ref('')

const pagination = ref({
  page: 1,
  limit: 10,
  total: 0,
})

const uploadConfig = ref({
  chunkSize: 512,
  chunkOverlap: 128,
  chunkStrategy: 'recursive',
  collectionName: 'documents',
})

const stats = ref({
  total_documents: 0,
  total_chunks: 0,
})

const supportedFormats = ['PDF', 'Word (.docx)', 'Markdown (.md)', 'HTML', 'TXT']

const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB
const ALLOWED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
  'text/plain',
  'text/markdown',
  'text/html',
]
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.txt', '.md', '.html', '.htm']

const filteredChunks = computed(() => {
  if (!chunkSearch.value) return currentChunks.value
  const search = chunkSearch.value.toLowerCase()
  return currentChunks.value.filter(c =>
    c.text?.toLowerCase().includes(search)
  )
})

async function fetchDocuments() {
  loading.value = true
  try {
    const response = await ingestApi.list({
      skip: (pagination.value.page - 1) * pagination.value.limit,
      limit: pagination.value.limit,
    })
    documents.value = response.documents || []
    pagination.value.total = response.total || 0
    const allStats = await ingestApi.list({ skip: 0, limit: 1000 })
    stats.value.total_documents = allStats.documents?.length || 0
    stats.value.total_chunks = (allStats.documents || []).reduce((sum, d) => sum + (d.chunks_count || 0), 0)
  } catch (error) {
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

function handleFileChange(file, fileList) {
  uploadError.value = ''
  selectedFiles.value = fileList
}

function handleFileRemove(file, fileList) {
  selectedFiles.value = fileList
}

async function handleUpload() {
  uploadError.value = ''
  const files = selectedFiles.value

  if (!files || files.length === 0) {
    uploadError.value = '请选择至少一个文件'
    return
  }

  for (const fileItem of files) {
    const rawFile = fileItem.raw || fileItem
    const fileName = rawFile.name || ''
    const fileSize = rawFile.size || 0
    const ext = '.' + (fileName.split('.').pop() || '').toLowerCase()

    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      uploadError.value = `不支持的文件类型: ${ext}。支持: ${ALLOWED_EXTENSIONS.join(', ')}`
      return
    }
    if (fileSize > MAX_FILE_SIZE) {
      uploadError.value = `文件过大: ${fileName}。最大支持 ${MAX_FILE_SIZE / 1024 / 1024}MB`
      return
    }
  }

  uploading.value = true
  uploadProgress.value = 0
  let successCount = 0
  let failCount = 0
  const total = files.length

  for (let i = 0; i < files.length; i++) {
    const fileItem = files[i]
    const rawFile = fileItem.raw || fileItem
    const formData = new FormData()
    formData.append('file', rawFile)
    formData.append('collection_name', uploadConfig.value.collectionName)
    formData.append('chunk_size', String(uploadConfig.value.chunkSize))
    formData.append('chunk_overlap', String(uploadConfig.value.chunkOverlap))

    try {
      const fileName = rawFile.name
      await ingestApi.upload(formData)
      successCount++
      uploadProgress.value = Math.round(((i + 1) / total) * 100)
    } catch (error) {
      failCount++
      const msg = error?.response?.data?.detail || error?.message || '未知错误'
      ElMessage.error(`${rawFile.name} 上传失败: ${msg}`)
    }
  }

  uploading.value = false
  uploadProgress.value = 100

  if (failCount === 0 && successCount > 0) {
    ElMessage.success(`成功上传 ${successCount} 个文档`)
    showUploadDialog.value = false
    selectedFiles.value = []
    if (uploadRef.value?.clearFiles) {
      uploadRef.value.clearFiles()
    }
    fetchDocuments()
  } else if (successCount > 0) {
    ElMessage.warning(`上传完成: ${successCount} 成功, ${failCount} 失败`)
    fetchDocuments()
  } else {
    ElMessage.error('所有文件上传失败')
  }
}

async function viewChunks(row) {
  try {
    const response = await ingestApi.chunks(row.document_id)
    currentChunks.value = response.chunks || []
    showChunksDialog.value = true
  } catch (error) {
    ElMessage.error('获取分块失败')
  }
}

async function deleteDocument(row) {
  try {
    await ElMessageBox.confirm('确定要删除这个文档吗？', '确认删除', {
      type: 'warning',
    })
    await ingestApi.delete(row.document_id)
    ElMessage.success('删除成功')
    fetchDocuments()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败')
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchDocuments()
})
</script>

<style lang="scss" scoped>
.upload-error {
  color: #f56c6c;
  font-size: 13px;
  margin-top: 8px;
}

.chunks-list {
  max-height: 500px;
  overflow-y: auto;

  .chunk-item {
    padding: 12px;
    margin-bottom: 8px;
    background: #f5f7fa;
    border-radius: 6px;
    border-left: 3px solid #409eff;

    .chunk-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      font-size: 12px;
      color: #999;
    }

    .chunk-index {
      font-weight: 600;
      color: #409eff;
    }

    .chunk-id {
      font-family: monospace;
    }

    .chunk-chars {
      margin-left: auto;
    }

    .chunk-text {
      font-size: 13px;
      line-height: 1.6;
      color: #333;
      white-space: pre-wrap;
      word-break: break-all;
    }
  }
}

.doc-manage {
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
  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    .stat-box {
      text-align: center;
      padding: 20px;
      background: #f5f7fa;
      border-radius: 8px;
      .stat-value {
        font-size: 28px;
        font-weight: 600;
        color: #409eff;
      }
      .stat-label {
        font-size: 13px;
        color: #666;
        margin-top: 4px;
      }
    }
  }
}
</style>
