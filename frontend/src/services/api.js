import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export const ragApi = {
  query: (data) => api.post('/rag/query', data, {
    timeout: 600000,  // 10 min — RAG chain involves multiple LLM calls
  }),
  health: () => api.get('/rag/health'),
}

export const ingestApi = {
  upload: (formData) => api.post('/ingest/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  list: (params) => api.get('/ingest/documents', { params }),
  delete: (id) => api.delete(`/ingest/documents/${id}`),
  chunks: (id, params) => api.get(`/ingest/documents/${id}/chunks`, { params }),
}

export const observabilityApi = {
  traces: (params) => api.get('/observability/traces', { params }),
  trace: (id) => api.get(`/observability/traces/${id}`),
  dashboard: () => api.get('/observability/dashboard'),
  metrics: (params) => api.get('/observability/metrics', { params }),
}

export const debugApi = {
  step: (step, query) => api.post('/observability/debug/step', null, { params: { step, query } }),
  trace: (data) => api.post('/observability/debug/trace', data),
}

export default api
