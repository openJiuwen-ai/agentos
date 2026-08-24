import { ref } from 'vue';
import {
  getLogComponents,
  getLogCategories,
  getExports,
  type LogCategoryItem,
  type LogComponent,
  type LogExportTask,
  type FileEntry,
} from '@/api/logs';

export interface LogLine {
  raw: string;
}

const categories = ref<LogCategoryItem[]>([]);
const categoriesLoading = ref(false);

const components = ref<LogComponent[]>([]);
const componentsLoading = ref(false);

const fileEntries = ref<FileEntry[]>([]);
const fileEntriesLoading = ref(false);

const logLines = ref<LogLine[]>([]);
const wsConnected = ref(false);

const maxLogLines = 10000;

const exportTasks = ref<LogExportTask[]>([]);
const exportTasksLoading = ref(false);

export function useLogs() {
  async function fetchCategories() {
    categoriesLoading.value = true;
    try {
      categories.value = await getLogCategories();
    } finally {
      categoriesLoading.value = false;
    }
  }

  async function fetchComponents(category?: string) {
    componentsLoading.value = true;
    try {
      components.value = await getLogComponents(category);
    } finally {
      componentsLoading.value = false;
    }
  }

  function addLogLines(lines: LogLine[]) {
    logLines.value.push(...lines);
    if (logLines.value.length > maxLogLines) {
      logLines.value = logLines.value.slice(logLines.value.length - maxLogLines);
    }
  }

  function clearLogLines() {
    logLines.value = [];
  }

  async function fetchLogExportTasks() {
    exportTasksLoading.value = true;
    try {
      exportTasks.value = await getExports();
    } finally {
      exportTasksLoading.value = false;
    }
  }

  return {
    categories,
    categoriesLoading,
    components,
    componentsLoading,
    fileEntries,
    fileEntriesLoading,
    logLines,
    wsConnected,
    maxLogLines,
    exportTasks,
    exportTasksLoading,
    fetchCategories,
    fetchComponents,
    addLogLines,
    clearLogLines,
    fetchLogExportTasks,
  };
}
