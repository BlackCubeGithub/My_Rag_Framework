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

    <el-dialog v-model="showUploadDialog" title="上传文档" width="500px">
      <el-form label-width="120px">
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="10"
            accept=".pdf,.docx,.doc,.txt,.md,.html"
          >
            <el-button>选择文件</el-button>
          </el-upload>
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
          <el-input v-model="uploadConfig.collectionName" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showChunksDialog" title="文档分块" width="800px">
      <el-input
        v-model="chunkSearch"
        placeholder="搜索分块内容"
        prefix-icon="Search"
        style="margin-bottom: 16px"
      />
      <el-table :data="filteredChunks" height="400">
        <el-table-column prop="chunk_id" label="Chunk ID" width="150" show-overflow-tooltip />
        <el-table-column prop="text" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column prop="index" label="索引" width="80" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Search } from '@element-plus/icons-vue'
import { ingestApi } from '@/services/api'

const documents = ref([])
const loading = ref(false)
const showUploadDialog = ref(false)
const showChunksDialog = ref(false)
const currentChunks = ref([])
const chunkSearch = ref('')

const pagination = ref({
  page: 1,
  limit: 10,
  total: 0,
})

const uploadConfig = ref({
  chunkSize: 512,
  chunkOverlap: 128,
  chunkStrategy: 'recursive',
  collectionName: 'default',
})

const stats = ref({
  total_documents: 0,
  total_chunks: 0,
})

const supportedFormats = ['PDF', 'Word (.docx)', 'Markdown (.md)', 'HTML', 'TXT']

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
    stats.value.total_documents = documents.value.length
    stats.value.total_chunks = documents.value.reduce((sum, d) => sum + (d.chunks_count || 0), 0)
  } catch (error) {
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
  ElMessage.info('请通过 API 上传文档')
  showUploadDialog.value = false
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
