<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElIcon,
  ElProgress, ElTable, ElTableColumn, ElTag, ElMessage,
  ElUpload,
} from 'element-plus'
import { Plus, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import {
  listFrameworks, uploadPackage, triggerBuild, getBuildStatus,
  type FrameworkItem, type BuildTaskStatus,
} from '@/api/framework'

// ── framework list ──
const frameworks = ref<FrameworkItem[]>([])
const loading = ref(false)

async function loadFrameworks() {
  loading.value = true
  try {
    frameworks.value = await listFrameworks()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ── step 1: upload dialog ──
const showUpload = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)
const uploadedMeta = ref<FrameworkItem | null>(null)

function openUpload() {
  uploadedMeta.value = null
  uploadPercent.value = 0
  showUpload.value = true
}

async function handleUpload(file: UploadFile) {
  uploading.value = true
  uploadPercent.value = 0
  try {
    const raw = file.raw
    if (!raw) return
    uploadPercent.value = 30
    uploadedMeta.value = await uploadPackage(raw)
    uploadPercent.value = 100
    showUpload.value = false
    showConfirm.value = true
    form.value.agent_name = uploadedMeta.value.agent_name
    form.value.version = uploadedMeta.value.version
    form.value.display_name = uploadedMeta.value.display_name
    form.value.entrypoint = uploadedMeta.value.entrypoint
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

// ── step 2: confirm dialog ──
const showConfirm = ref(false)
const form = ref({ agent_name: '', version: '', display_name: '', entrypoint: '' })

// ── step 3: build progress dialog ──
const showBuild = ref(false)
const building = ref(false)
const buildTaskId = ref('')
const buildStatus = ref<BuildTaskStatus | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function confirmBuild() {
  showConfirm.value = false
  showBuild.value = true
  building.value = true
  try {
    const { task_id } = await triggerBuild(form.value)
    buildTaskId.value = task_id
    startPolling(task_id)
  } catch (e: any) {
    ElMessage.error(e.message || '构建失败')
    showBuild.value = false
    building.value = false
  }
}

function startPolling(taskId: string) {
  pollTimer = setInterval(async () => {
    try {
      buildStatus.value = await getBuildStatus(taskId)
      if (buildStatus.value.status === 'done' || buildStatus.value.status === 'failed') {
        clearInterval(pollTimer!)
        building.value = false
        loadFrameworks()
      }
    } catch {
      // retry on next tick
    }
  }, 2000)
}

function closeBuild() {
  if (pollTimer) clearInterval(pollTimer)
  showBuild.value = false
  building.value = false
}

function startBuildFromList(item: FrameworkItem) {
  form.value.agent_name = item.agent_name
  form.value.version = item.version
  form.value.display_name = item.display_name
  form.value.entrypoint = item.entrypoint
  showConfirm.value = true
}

function buildLabel(status: string) {
  const map: Record<string, string> = { pending: '等待中', building: '构建中', done: '完成', failed: '失败' }
  return map[status] || status
}

function buildTagType(status: string) {
  const map: Record<string, string> = { pending: 'info', building: 'warning', done: 'success', failed: 'danger' }
  return (map[status] || 'info') as 'info' | 'warning' | 'success' | 'danger'
}

onMounted(loadFrameworks)
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1 class="page-title">框架管理</h1>
      <ElButton type="primary" :icon="Plus" @click="openUpload">接入新框架</ElButton>
    </div>

    <!-- Framework list -->
    <ElTable :data="frameworks" v-loading="loading" empty-text="暂无已接入框架" style="margin-top:16px">
      <ElTableColumn prop="agent_name" label="Agent 名称" min-width="120" />
      <ElTableColumn prop="display_name" label="显示名称" min-width="140" />
      <ElTableColumn prop="version" label="版本" width="100" />
      <ElTableColumn prop="entrypoint" label="入口命令" width="120" />
      <ElTableColumn label="构建状态" width="100">
        <template #default="{ row }">
          <ElTag v-if="row.build_status" :type="buildTagType(row.build_status)" size="small">
            {{ buildLabel(row.build_status) }}
          </ElTag>
          <span v-else style="color:#909399">—</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="100">
        <template #default="{ row }">
          <ElButton size="small" @click="startBuildFromList(row)">启动构建</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <!-- Upload dialog -->
    <ElDialog v-model="showUpload" title="上传新框架" width="480px" :close-on-click-modal="false">
      <ElUpload
        :auto-upload="false"
        :on-change="handleUpload"
        accept=".tgz,.tar.gz"
        :limit="1"
        drag
      >
        <ElIcon :size="48"><UploadFilled /></ElIcon>
        <div style="margin-top:8px">拖拽或点击选择 .tgz 文件</div>
      </ElUpload>
      <div v-if="uploading" style="margin-top:12px">
        <ElProgress :percentage="uploadPercent" :show-text="uploadPercent > 0" />
        <div style="color:#909399;font-size:13px;margin-top:4px">正在上传并解析框架包…</div>
      </div>
    </ElDialog>

    <!-- Confirm dialog -->
    <ElDialog v-model="showConfirm" title="确认框架信息" width="460px" :close-on-click-modal="false">
      <ElForm :model="form" label-width="90px">
        <ElFormItem label="Agent 名称">
          <ElInput v-model="form.agent_name" disabled />
        </ElFormItem>
        <ElFormItem label="版本号">
          <ElInput v-model="form.version" disabled />
        </ElFormItem>
        <ElFormItem label="显示名称">
          <ElInput v-model="form.display_name" />
        </ElFormItem>
        <ElFormItem label="入口命令">
          <ElInput v-model="form.entrypoint" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showConfirm = false">取消</ElButton>
        <ElButton type="primary" @click="confirmBuild">确认接入</ElButton>
      </template>
    </ElDialog>

    <!-- Build progress dialog -->
    <ElDialog v-model="showBuild" title="构建进度" width="440px" :close-on-click-modal="false" :show-close="false">
      <div v-if="buildStatus">
        <div style="margin-bottom:8px">
          <ElTag :type="buildTagType(buildStatus.status)">{{ buildLabel(buildStatus.status) }}</ElTag>
        </div>
        <ElProgress
          :percentage="buildStatus.progress"
          :status="buildStatus.status === 'failed' ? 'exception' : undefined"
        />
        <div v-if="buildStatus.image" style="margin-top:12px;font-size:13px;color:#606266">
          镜像: {{ buildStatus.image }}
        </div>
        <div v-if="buildStatus.status === 'failed' && buildStatus.error_message" style="margin-top:8px;font-size:13px;color:#f56c6c">
          {{ buildStatus.error_message }}
        </div>
      </div>
      <template #footer v-if="!building">
        <ElButton @click="closeBuild">关闭</ElButton>
      </template>
    </ElDialog>
  </section>
</template>

<style scoped>
.page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.page-title { font-size: 20px; font-weight: 600; margin: 0; }
</style>
