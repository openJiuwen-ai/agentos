<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  ElPagination,
  ElMessageBox,
  ElMessage,
  ElSkeleton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElIcon,
  ElButton,
  ElTable,
  ElTableColumn,
  ElAlert,
} from 'element-plus';
import { Delete, CopyDocument } from '@element-plus/icons-vue';
import { fetchApiKeyList, createApiKey, deleteApiKey } from '@/api/inference';
import type { ApiKeyItem, CreateApiKeyResponse } from '@/api/inference';

const loading = ref(false);
const apiKeys = ref<ApiKeyItem[]>([]);
const currentPage = ref(1);
const pageSize = ref(10);

const paginatedApiKeys = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return apiKeys.value.slice(start, start + pageSize.value);
});

const showCreateDialog = ref(false);
const createForm = ref({ name: '' });
const createLoading = ref(false);
const createFormRef = ref<InstanceType<typeof ElForm> | null>(null);

const createFormRules = {
  name: [
    { required: true, message: '请输入 API Key 名称', trigger: 'blur' },
    { max: 256, message: 'API Key 名称不能超过 256 个字符', trigger: 'blur' },
  ],
};

const showCreatedDialog = ref(false);
const createdKey = ref<CreateApiKeyResponse | null>(null);

async function loadApiKeys() {
  loading.value = true;
  try {
    const data = await fetchApiKeyList();
    apiKeys.value = data?.keys || [];
  } catch (e) {
    console.error('加载 API Key 列表失败:', e);
  } finally {
    loading.value = false;
  }
}

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

async function copyKey(key: string) {
  try {
    await navigator.clipboard.writeText(key);
    ElMessage.success('已复制到剪贴板');
  } catch {
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

function openCreateDialog() {
  createForm.value = { name: '' };
  showCreateDialog.value = true;
}

async function handleCreateKey() {
  if (!createFormRef.value) return;
  try {
    await createFormRef.value.validate();
  } catch {
    return;
  }
  createLoading.value = true;
  try {
    const result = await createApiKey({ key_name: createForm.value.name || undefined });
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

function closeCreatedDialog() {
  showCreatedDialog.value = false;
  createdKey.value = null;
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleString('zh-CN');
}

onMounted(() => {
  loadApiKeys();
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1 class="page-header__title">API Key</h1>
      <ElButton type="primary" @click="openCreateDialog">新建API Key</ElButton>
    </div>

    <div class="card">
      <ElSkeleton v-if="loading" :rows="5" animated style="padding: 20px" />

      <ElTable v-else :data="paginatedApiKeys" style="width: 100%">
        <ElTableColumn label="名称" min-width="140">
          <template #default="{ row }">
            {{ row.key_name || row.key_preview }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="key_preview" label="Key预览" min-width="180">
          <template #default="{ row }">
            <span class="mono-text">{{ row.key_preview }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="绑定模型" min-width="140">
          <template #default="{ row }">
            {{ row.bound_model || '所有模型' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="创建日期" min-width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="过期时间" min-width="180">
          <template #default="{ row }">
            {{ row.expires_at ? formatDate(row.expires_at) : '永不过期' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="100" align="right">
          <template #default="{ row }">
            <ElButton
              v-if="!row.is_default"
              type="danger"
              link
              title="删除"
              @click="handleDeleteKey(row.key_alias)"
            >
              <ElIcon :size="16"><Delete /></ElIcon>
            </ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <ElPagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="apiKeys.length"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
      />
    </div>

    <ElDialog
      v-model="showCreateDialog"
      title="新建 API Key"
      width="400px"
      :close-on-click-modal="false"
    >
      <ElForm ref="createFormRef" :model="createForm" :rules="createFormRules" label-position="top" @submit.prevent="handleCreateKey">
        <ElFormItem label="名称" prop="name">
          <ElInput
            v-model="createForm.name"
            placeholder="请输入 API Key 名称"
            maxlength="256"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showCreateDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="createLoading" @click="handleCreateKey">
          确定
        </ElButton>
      </template>
    </ElDialog>

    <ElDialog
      v-model="showCreatedDialog"
      title="API Key 创建成功"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="created-key-info">
        <ElAlert
          title="请立即复制并保存您的 API Key，关闭后将无法再次查看完整 Key。"
          type="warning"
          show-icon
          :closable="false"
        />

        <div class="created-key-item">
          <label>API Key</label>
          <div class="created-key-value created-key-value--full">
            <code>{{ createdKey?.key }}</code>
            <ElButton size="small" @click="copyKey(createdKey?.key || '')">
              <ElIcon :size="14"><CopyDocument /></ElIcon>
              复制
            </ElButton>
          </div>
        </div>
      </div>

      <template #footer>
        <ElButton type="primary" @click="closeCreatedDialog">我已保存，关闭</ElButton>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.mono-text {
  font-family: ui-monospace, monospace;
}

.created-key-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.created-key-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.created-key-item label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.created-key-value {
  padding: 10px 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  color: var(--text-primary);
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
</style>
