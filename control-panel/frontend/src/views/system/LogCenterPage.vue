<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElButton,
  ElCard,
  ElTable,
  ElTableColumn,
  ElDrawer,
  ElMessage,
  ElBreadcrumb,
  ElBreadcrumbItem,
  ElSelect,
  ElOption,
  vLoading,
} from 'element-plus';
import { Search } from '@element-plus/icons-vue';
import { getLokiFilenames, type FileEntry } from '@/api/logs';
import { fetchHardwareNodes } from '@/api/appliance';
import { useLogs } from '@/composables/useLogs';
import jiuwenswarmIcon from '@/assets/images/log-center/jiuwen.png';
import vllmIcon from '@/assets/images/log-center/vllm.png';
import controlPanelIcon from '@/assets/images/log-center/control_panel.png';

defineOptions({
  directives: {
    loading: vLoading,
  },
});

const categoryIcons: Record<string, string> = {
  vllm: vllmIcon,
  control_panel: controlPanelIcon,
  jiuwenswarm: jiuwenswarmIcon,
  'agent-runtime': jiuwenswarmIcon,
  'agent-gateway': jiuwenswarmIcon,
  'agent-registry': jiuwenswarmIcon,
  jiuwenbox: jiuwenswarmIcon,
};

const router = useRouter();

const { categories, categoriesLoading, fileEntries, fileEntriesLoading, fetchCategories } = useLogs();

const activeCategoryKey = ref<string>('');
const activeCategoryLabel = computed(() => {
  const cat = categories.value.find((c) => c.key === activeCategoryKey.value);
  return cat?.label || activeCategoryKey.value;
});
const showComponentDrawer = ref(false);
const selectedComponent = ref<{ id: string; name: string } | null>(null);

const MAX_DEPTH = 5;
const currentPathStack = ref<{ name: string; path: string }[]>([]);
const currentDepth = computed(() => currentPathStack.value.length + 1);

interface DirNode {
  name: string;
  path: string;
  isDir: boolean;
  children: Map<string, DirNode>;
}

const nodeOptions = ref<{ label: string; value: string }[]>([]);
const nodesLoading = ref(false);
const selectedNodeIp = ref('');
const treeRoot = ref<Map<string, DirNode>>(new Map());

// 将 Loki 返回的文件路径列表解析为树状目录结构
function buildFileTree(paths: string[]): Map<string, DirNode> {
  const root = new Map<string, DirNode>();
  for (const rawPath of paths) {
    const segments = rawPath.split('/').filter(Boolean);
    let level = root;
    let currentPath = '';
    segments.forEach((segment, index) => {
      currentPath = currentPath ? `${currentPath}/${segment}` : segment;
      let node = level.get(segment);
      if (!node) {
        node = {
          name: segment,
          path: currentPath,
          isDir: index < segments.length - 1,
          children: new Map(),
        };
        level.set(segment, node);
      }
      level = node.children;
    });
  }
  return root;
}

// 根据当前目录栈从树中取出当前层级的文件/目录列表
function deriveEntries() {
  let level = treeRoot.value;
  for (const seg of currentPathStack.value) {
    const child = level.get(seg.name);
    if (!child) {
      level = new Map();
      break;
    }
    level = child.children;
  }
  const entries: FileEntry[] = Array.from(level.values()).map((node) => ({
    name: node.name,
    path: node.path,
    size: 0,
    modified: '',
    is_dir: node.isDir,
  }));
  entries.sort((a, b) => (a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1));
  fileEntries.value = entries;
}

// 通过 Loki 获取选中节点的文件路径，并重建目录树
async function loadTree() {
  if (!selectedComponent.value) return;
  if (!selectedNodeIp.value) {
    fileEntries.value = [];
    return;
  }
  fileEntries.value = [];
  fileEntriesLoading.value = true;
  try {
    const paths = await getLokiFilenames(selectedNodeIp.value, activeCategoryKey.value || undefined);
    treeRoot.value = buildFileTree(paths);
  } catch {
    ElMessage.error('读取目录失败');
    treeRoot.value = new Map();
  } finally {
    fileEntriesLoading.value = false;
    deriveEntries();
  }
}

// 获取主节点/从节点 IP 列表，默认选中主节点
async function ensureNodes() {
  if (nodeOptions.value.length > 0) return;
  nodesLoading.value = true;
  try {
    const { nodes } = await fetchHardwareNodes();
    nodeOptions.value = nodes.map((node) => ({
      label: `${node.role.toLowerCase() === 'master' ? '主节点' : '从节点'} (${node.host})`,
      value: node.host,
    }));
    const master = nodes.find((node) => node.role.toLowerCase() === 'master');
    selectedNodeIp.value = (master ?? nodes[0])?.host ?? '';
  } catch {
    ElMessage.error('获取节点列表失败');
  } finally {
    nodesLoading.value = false;
  }
}

watch(selectedNodeIp, () => {
  if (!showComponentDrawer.value) return;
  currentPathStack.value = [];
  loadTree();
});

function navigateToDir(row: FileEntry) {
  if (currentDepth.value >= MAX_DEPTH) {
    ElMessage.warning(`已达到最大目录深度（${MAX_DEPTH} 级）`);
    return;
  }
  currentPathStack.value.push({ name: row.name, path: row.path });
  deriveEntries();
}

function navigateToBreadcrumb(index: number) {
  if (index < 0) {
    currentPathStack.value = [];
  } else {
    currentPathStack.value = currentPathStack.value.slice(0, index + 1);
  }
  deriveEntries();
}

async function onCategoryClick(key: string) {
  const cat = categories.value.find((c) => c.key === key);
  if (!cat || !cat.component_id) return;
  activeCategoryKey.value = key;
  showComponentDrawer.value = true;
  selectedComponent.value = { id: cat.component_id, name: cat.label };
  currentPathStack.value = [];
  await ensureNodes();
  await loadTree();
}

function onComponentDrawerClose() {
  activeCategoryKey.value = '';
  selectedComponent.value = null;
  fileEntries.value = [];
  currentPathStack.value = [];
  treeRoot.value = new Map();
}

function openLiveLog(fileEntry: FileEntry) {
  router.push({
    name: 'log-explore',
    query: {
      category: activeCategoryKey.value,
      ip: selectedNodeIp.value || undefined,
      file_path: fileEntry.path || fileEntry.name,
    },
  });
}

onMounted(() => {
  fetchCategories();
  ensureNodes();
});
</script>

<template>
  <section class="page">
    <div class="page-header-row">
      <h1 class="title-l1">日志中心</h1>
    </div>

    <div class="category-row" v-loading="categoriesLoading">
      <ElCard
        v-for="cat in categories"
        :key="cat.key"
        shadow="never"
        class="category-card"
        :class="{ 'category-card--active': activeCategoryKey === cat.key }"
        body-class="category-card__body"
        @click="onCategoryClick(cat.key)"
      >
        <div class="category-card__icon">
          <img :src="categoryIcons[cat.key] || controlPanelIcon" :alt="cat.label" class="category-card__icon-img" />
        </div>
        <div class="category-card__info">
          <div class="title-l2 category-card__label">{{ cat.label }}</div>
          <div class="category-card__count">{{ cat.count }} 个组件</div>
        </div>
      </ElCard>
    </div>

    <div v-if="!activeCategoryKey && !categoriesLoading" class="category-hint">
      请点击上方分类卡片查看对应的日志文件
    </div>

    <ElDrawer
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

      <div class="drawer-node-row">
        <span class="drawer-node-label">节点</span>
        <ElSelect
          v-model="selectedNodeIp"
          v-loading="nodesLoading"
          placeholder="选择节点"
          size="small"
          style="width: 260px"
        >
          <ElOption v-for="opt in nodeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </ElSelect>
      </div>

      <div class="drawer-breadcrumb" v-if="currentPathStack.length > 0">
        <ElBreadcrumb separator="/">
          <ElBreadcrumbItem>
            <a href="#" @click.prevent="navigateToBreadcrumb(-1)">
              {{ activeCategoryLabel }}
            </a>
          </ElBreadcrumbItem>
          <ElBreadcrumbItem v-for="(seg, idx) in currentPathStack" :key="idx">
            <a v-if="idx < currentPathStack.length - 1" href="#" @click.prevent="navigateToBreadcrumb(idx)">{{
              seg.name
            }}</a>
            <span v-else>{{ seg.name }}</span>
          </ElBreadcrumbItem>
        </ElBreadcrumb>
        <span class="breadcrumb-depth-hint"> {{ currentDepth }} / {{ MAX_DEPTH }} 级 </span>
      </div>

      <ElTable
        :data="fileEntries"
        v-loading="fileEntriesLoading"
        stripe
        @row-click="(row: FileEntry) => row.is_dir && navigateToDir(row)"
      >
        <ElTableColumn label="文件名" min-width="180">
          <template #default="{ row }">
            <span
              :class="{
                'entry-dir': row.is_dir,
                'entry-file': !row.is_dir,
              }"
            >
              {{ row.name }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="修改时间" width="190">
          <template #default="{ row }">
            {{ row.modified ? new Date(row.modified).toLocaleString() : '—' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <template v-if="!row.is_dir">
              <ElButton type="primary" link :icon="Search" size="small" @click="openLiveLog(row)">日志预览</ElButton>
            </template>
          </template>
        </ElTableColumn>
      </ElTable>
    </ElDrawer>
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
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.category-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  min-height: 80px;
}

.category-card {
  --el-card-border-color: transparent;
  --el-card-border-radius: var(--radius-2xl, 24px);
  border: none;
  border-radius: var(--radius-2xl, 24px);
  background: var(--bg-2);
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    background-color 0.2s ease;
}

.category-card :deep(.category-card__body) {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 24px;
}

.category-card:hover {
  box-shadow: 0 4px 16px rgba(25, 25, 25, 0.06);
}

.category-card--active {
  background: var(--bg-active);
}

.category-card__icon {
  width: 48px;
  height: 48px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 16px;
  border: 1px solid var(--bg-1);
  background: var(--bg-2);
  overflow: hidden;
}

.category-card__icon-img {
  width: 48px;
  height: 48px;
  display: block;
  object-fit: cover;
  object-position: center;
}

.category-card__info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.category-card__label {
  min-width: 0;
}

.category-card__count {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
}

.category-hint {
  text-align: center;
  padding: 60px 0;
  color: var(--text-placeholder);
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
  cursor: pointer;
  color: var(--el-color-primary);
}

.entry-file {
  font-weight: 400;
}

.drawer-node-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 0 4px;
}

.drawer-node-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.drawer-breadcrumb {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 0 4px;
}

.breadcrumb-depth-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  margin-left: 12px;
}
</style>
