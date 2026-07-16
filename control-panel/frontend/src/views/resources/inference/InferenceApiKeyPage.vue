<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ElPagination, ElMessageBox, ElMessage, ElSkeleton, ElDialog, ElForm, ElFormItem, ElInput, ElIcon } from 'element-plus';
import { Delete, CopyDocument, Warning } from '@element-plus/icons-vue';
import { fetchApiKeyList, createApiKey, deleteApiKey } from '@/api/inference';
import type { ApiKeyItem, CreateApiKeyResponse } from '@/api/inference';

// 状态
const loading = ref(false);
const apiKeys = ref<ApiKeyItem[]>([]);
const currentPage = ref(1);
const pageSize = ref(10);

const paginatedApiKeys = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return apiKeys.value.slice(start, start + pageSize.value);
});

// 新建弹窗
const showCreateDialog = ref(false);
const createForm = ref({ name: '' });
const createLoading = ref(false);

// 创建成功弹窗
const showCreatedDialog = ref(false);
const createdKey = ref<CreateApiKeyResponse | null>(null);

// 加载 API Key 列表
async function loadApiKeys() {
  loading.value = true;
  try {
    const data = await fetchApiKeyList();
    apiKeys.value = data.keys;
  } catch (e) {
    console.error('加载 API Key 列表失败:', e);
  } finally {
    loading.value = false;
  }
}

// 删除 API Key
async function handleDeleteKey(key_alias: string) {
  try {
    await ElMessageBox.confirm('确定要删除这个 API Key 吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await deleteApiKey(key_alias);
    ElMessage.success('删除成功');
    await loadApiKeys();
  } catch (e) {
    if (e !== 'cancel') {
      console.error('删除 API Key 失败:', e);
    }
  }
}

// 复制Key
async function copyKey(key: string) {
  try {
    await navigator.clipboard.writeText(key);
    ElMessage.success('已复制到剪贴板');
  } catch {
    // fallback for non-secure contexts
    const ta = document.createElement('textarea');
    ta.value = key;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    ElMessage.success('已复制到剪贴板');
  }
}

// 打开新建弹窗
function openCreateDialog() {
  createForm.value = { name: '' };
  showCreateDialog.value = true;
}

// 创建 API Key
async function handleCreateKey() {
  createLoading.value = true;
  try {
    const result = await createApiKey({});
    createdKey.value = result;
    showCreateDialog.value = false;
    showCreatedDialog.value = true;
    await loadApiKeys();
  } catch (e) {
    ElMessage.error('创建失败: ' + (e instanceof Error ? e.message : '未知错误'));
  } finally {
    createLoading.value = false;
  }
}

// 关闭创建成功弹窗
function closeCreatedDialog() {
  showCreatedDialog.value = false;
  createdKey.value = null;
}

// 格式化日期
function formatDate(dateStr: string | null) {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleString('zh-CN');
}

// 初始化加载
onMounted(() => {
  loadApiKeys();
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1 class="page-header__title">API Key</h1>
      <button class="btn btn--primary" @click="openCreateDialog">新建API Key</button>
    </div>

    <div class="card">
      <!-- 加载状态 -->
      <ElSkeleton v-if="loading" :rows="5" animated style="padding: 20px" />

      <!-- 数据表格 -->
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>Key预览</th>
            <th>绑定模型</th>
            <th>创建日期</th>
            <th>过期时间</th>
            <th style="text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="apiKey in paginatedApiKeys" :key="apiKey.key_alias">
            <td style="font-family: monospace">{{ apiKey.key_preview }}</td>
            <td>{{ apiKey.bound_model || '所有模型' }}</td>
            <td>{{ formatDate(apiKey.created_at) }}</td>
            <td>{{ apiKey.expires_at ? formatDate(apiKey.expires_at) : '永不过期' }}</td>
            <td style="text-align: right">
              <button class="btn btn--danger btn--text" title="删除" @click="handleDeleteKey(apiKey.key_alias)">
                <el-icon :size="16"><Delete /></el-icon>
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <ElPagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="apiKeys.length"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
      />
    </div>

    <!-- 新建 API Key 弹窗 -->
    <ElDialog
      v-model="showCreateDialog"
      title="新建 API Key"
      width="400px"
      :close-on-click-modal="false"
    >
      <ElForm :model="createForm" label-position="top">
        <ElFormItem label="名称" required>
          <ElInput
            v-model="createForm.name"
            placeholder="请输入 API Key 名称"
            maxlength="50"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <button class="btn" @click="showCreateDialog = false">取消</button>
        <button class="btn btn--primary" :disabled="createLoading" @click="handleCreateKey">
          {{ createLoading ? '创建中...' : '确定' }}
        </button>
      </template>
    </ElDialog>

    <!-- 创建成功弹窗 -->
    <ElDialog
      v-model="showCreatedDialog"
      title="API Key 创建成功"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="created-key-info">
        <div class="created-key-warning">
          <ElIcon :size="16" color="#f59e0b"><Warning /></ElIcon>
          <span>请立即复制并保存您的API Key，关闭后将无法再次查看完整Key。</span>
        </div>
        
        <div class="created-key-item">
          <label>API Key</label>
          <div class="created-key-value created-key-value--full">
            <code>{{ createdKey?.key }}</code>
            <button class="copy-btn" @click="copyKey(createdKey?.key || '')">
              <ElIcon :size="14"><CopyDocument /></ElIcon>
              复制
            </button>
          </div>
        </div>
      </div>
      
      <template #footer>
        <button class="btn btn--primary" @click="closeCreatedDialog">我已保存，关闭</button>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.created-key-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.created-key-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  color: #92400e;
  font-size: 13px;
}

.created-key-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.created-key-item label {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.created-key-value {
  padding: 10px 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 14px;
  color: #1f2937;
}

.created-key-value--full {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.created-key-value--full code {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  word-break: break-all;
}

.created-key-value--mono {
  font-family: ui-monospace, monospace;
  font-size: 13px;
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.copy-btn:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.btn {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover {
  background: #f3f4f6;
}

.btn--primary {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.btn--primary:hover {
  background: #1d4ed8;
}

.btn--danger {
  color: #dc2626;
  background: transparent;
  border: none;
}

.btn--danger:hover {
  background: #fef2f2;
}
</style>
