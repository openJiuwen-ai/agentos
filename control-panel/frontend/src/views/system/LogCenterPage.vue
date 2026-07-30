<script setup lang="ts">
import { h, ref, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import {
  ElButton,
  ElTable,
  ElTableColumn,
  ElDrawer,
  ElMessage,
} from "element-plus";
import { Monitor, Download } from "@element-plus/icons-vue";
import {
  createArchive,
  type FileEntry,
} from "@/api/logs";
import { useLogs } from "@/composables/useLogs";
import vllmIcon from "@/assets/images/log-center/vllm.png";
import controlPanelIcon from "@/assets/images/log-center/control_panel.png";
import jiuwenIcon from "@/assets/images/log-center/jiuwen.png";
import yuanrongIcon from "@/assets/images/log-center/yuanrong.png";
import tongtuIcon from "@/assets/images/log-center/tongtu.png";

const router = useRouter();

const {
  categories,
  categoriesLoading,
  fileEntries,
  fileEntriesLoading,
  fetchCategories,
  fetchComponentFiles,
} = useLogs();

const CATEGORY_ICONS: Record<string, string> = {
  vllm: vllmIcon,
  control_panel: controlPanelIcon,
  jiuwen: jiuwenIcon,
  yuanrong: yuanrongIcon,
  tongtu: tongtuIcon,
};

const activeCategoryKey = ref<string>("");
const activeCategoryLabel = computed(() => {
  const cat = categories.value.find((c) => c.key === activeCategoryKey.value);
  return cat?.label || activeCategoryKey.value;
});
const showComponentDrawer = ref(false);
const selectedComponent = ref<{ id: string; name: string } | null>(null);

async function onCategoryClick(key: string) {
  const cat = categories.value.find((c) => c.key === key);
  if (!cat || !cat.component_id) return;
  activeCategoryKey.value = key;
  showComponentDrawer.value = true;
  selectedComponent.value = { id: cat.component_id, name: cat.label };
  fileEntries.value = [];
  try {
    await fetchComponentFiles(cat.component_id);
  } catch {
    ElMessage.error("读取目录失败");
  }
}

function onComponentDrawerClose() {
  activeCategoryKey.value = "";
  selectedComponent.value = null;
  fileEntries.value = [];
}

function openLiveLog(fileEntry: FileEntry) {
  router.push({
    name: "log-live",
    query: {
      component_id: selectedComponent.value?.id,
      name: fileEntry.name,
    },
  });
}

function buildTaskMessage(type: string, taskId: string) {
  return h("span", [
    `${type}已创建: ${taskId} `,
    h(
      "a",
      {
        href: "#",
        onClick: (e: Event) => {
          e.preventDefault();
          router.push({ name: "task-center" });
        },
        style: { color: "var(--el-color-primary)", textDecoration: "underline" },
      },
      "查看任务",
    ),
  ]);
}

async function handleDownloadFile(fileEntry: FileEntry) {
  if (!selectedComponent.value) {
    ElMessage.error("请先选择日志组件");
    return;
  }
  try {
    const result = await createArchive(selectedComponent.value.id, fileEntry.path);
    ElMessage({ message: buildTaskMessage("下载任务", result.task_id), type: "success" });
  } catch {
    ElMessage.error("创建下载任务失败");
  }
}

async function handleArchiveDir(fileEntry: FileEntry) {
  if (!selectedComponent.value) {
    ElMessage.error("请先选择日志组件");
    return;
  }
  try {
    const result = await createArchive(selectedComponent.value.id, fileEntry.path);
    ElMessage({ message: buildTaskMessage("打包任务", result.task_id), type: "success" });
  } catch {
    ElMessage.error("创建打包任务失败");
  }
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + " " + units[i];
}

function goToTaskCenter() {
  router.push({ name: "task-center" });
}

onMounted(() => fetchCategories());
</script>

<template>
  <section class="page">
    <div class="page-header-row">
      <h1 class="page-title">日志中心</h1>
      <el-button
        type="primary"
        :icon="Monitor"
        size="small"
        @click="goToTaskCenter"
      >
        任务中心
      </el-button>
    </div>

    <div class="category-row" v-loading="categoriesLoading">
      <div
        v-for="cat in categories"
        :key="cat.key"
        class="category-card"
        :class="{ 'category-card--active': activeCategoryKey === cat.key }"
        @click="onCategoryClick(cat.key)"
      >
        <div class="category-card__icon">
          <img
            v-if="CATEGORY_ICONS[cat.key]"
            :src="CATEGORY_ICONS[cat.key]"
            :alt="cat.label"
            class="category-card__icon-img"
          />
          <span v-else class="category-card__icon-fallback">📄</span>
        </div>
        <div class="category-card__info">
          <div class="category-card__label">{{ cat.label }}</div>
          <div class="category-card__count">{{ cat.count }} 个组件</div>
        </div>
      </div>
    </div>

    <div v-if="!activeCategoryKey && !categoriesLoading" class="category-hint">
      请点击上方分类卡片查看对应的日志文件
    </div>

    <el-drawer
      v-model="showComponentDrawer"
      direction="rtl"
      size="45%"
      destroy-on-close
      @closed="onComponentDrawerClose"
    >
      <template #header>
        <div class="drawer-header">
          <span class="drawer-title">{{ activeCategoryLabel }}</span>
          <span class="drawer-subtitle">日志文件</span>
        </div>
      </template>

      <el-table
        :data="fileEntries"
        v-loading="fileEntriesLoading"
        stripe
      >
        <el-table-column label="文件名" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'entry-dir': row.is_dir, 'entry-file': !row.is_dir }">
              {{ row.name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="修改时间" width="190">
          <template #default="{ row }">
            {{ new Date(row.modified).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">
            {{ row.is_dir ? "—" : formatFileSize(row.size) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="!row.is_dir">
              <el-button
                type="primary"
                link
                :icon="Monitor"
                size="small"
                @click="openLiveLog(row)"
              >实时日志</el-button>
              <el-button
                type="primary"
                link
                :icon="Download"
                size="small"
                @click="handleDownloadFile(row)"
              >下载日志</el-button>
            </template>
            <template v-else>
              <el-button
                type="primary"
                link
                :icon="Download"
                size="small"
                @click="handleArchiveDir(row)"
              >打包下载</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </section>
</template>

<style scoped>
.page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding-bottom: 24px;
}

.page-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.category-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
  min-height: 80px;
}

.category-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 28px;
  border-radius: 12px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  cursor: pointer;
  transition: all 0.2s;
}

.category-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.category-card--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.category-card__icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.category-card__icon-img {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: block;
  object-position: center;
}

.category-card__icon-fallback {
  font-size: 36px;
  line-height: 1;
}

.category-card__info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.category-card__label {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.category-card__count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.category-hint {
  text-align: center;
  padding: 60px 0;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drawer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.drawer-subtitle {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.entry-dir {
  font-weight: 600;
}

.entry-file {
  font-weight: 400;
}
</style>
