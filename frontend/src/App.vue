<template>
  <el-container class="app-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <h2>RAG Framework</h2>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><ChatDotRound /></el-icon>
          <span>对话</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Document /></el-icon>
          <span>文档管理</span>
        </el-menu-item>
        <el-menu-item index="/traces">
          <el-icon><Connection /></el-icon>
          <span>链路追踪</span>
        </el-menu-item>
        <el-menu-item index="/metrics">
          <el-icon><DataAnalysis /></el-icon>
          <span>指标监控</span>
        </el-menu-item>
        <el-menu-item index="/debug">
          <el-icon><Tools /></el-icon>
          <span>调试工具</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <h3>{{ pageTitle }}</h3>
        <div class="header-actions">
          <el-tag type="success">v1.0.0</el-tag>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Document,
  Connection,
  DataAnalysis,
  Tools
} from '@element-plus/icons-vue'

const route = useRoute()

const pageTitle = computed(() => {
  const titles = {
    '/': 'RAG 对话',
    '/documents': '文档管理',
    '/traces': '链路追踪',
    '/metrics': '指标监控',
    '/debug': '调试工具',
  }
  return titles[route.path] || 'RAG Framework'
})
</script>

<style lang="scss" scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background: #1a1a2e;
  .logo {
    padding: 20px;
    h2 {
      color: #fff;
      font-size: 18px;
      text-align: center;
    }
  }
  :deep(.el-menu) {
    background: transparent;
    border: none;
    .el-menu-item {
      color: #a0a0a0;
      &.is-active {
        background: #16213e;
        color: #00d9ff;
      }
      &:hover {
        background: #16213e;
      }
    }
  }
}

.header {
  background: #fff;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  h3 {
    color: #333;
    font-weight: 500;
  }
}

.main-content {
  background: #f5f7fa;
  padding: 20px;
}
</style>
