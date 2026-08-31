<script setup lang="ts">
import { computed } from 'vue';
import { ElMessage, ElButton } from 'element-plus';
import { CopyDocument } from '@element-plus/icons-vue';

const props = withDefaults(
  defineProps<{
    /** 语言/类型标签，如 Shell、YAML */
    label: string;
    /** 代码正文 */
    code: string;
    /** 复制成功提示前缀，默认用 label */
    copyLabel?: string;
    /** 无障碍区域名 */
    ariaLabel?: string;
  }>(),
  {
    copyLabel: '',
    ariaLabel: '',
  },
);

const lines = computed(() => props.code.split('\n'));
const regionLabel = computed(() => props.ariaLabel || `${props.label} 代码`);
const successLabel = computed(() => props.copyLabel || props.label);

async function handleCopy() {
  try {
    await navigator.clipboard.writeText(props.code);
    ElMessage.success(`${successLabel.value} 已复制到剪贴板`);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = props.code;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    ElMessage.success(`${successLabel.value} 已复制到剪贴板`);
  }
}
</script>

<template>
  <div class="code-block">
    <div class="code-block__header">
      <span class="code-block__label">{{ label }}</span>
      <ElButton class="code-block__copy-btn" :icon="CopyDocument" text size="small" @click="handleCopy">
        复制
      </ElButton>
    </div>
    <div class="code-block__body" role="region" :aria-label="regionLabel">
      <div v-for="(line, index) in lines" :key="index" class="code-block__line">
        <span class="code-block__line-no" aria-hidden="true">{{ index + 1 }}</span>
        <code class="code-block__line-text">{{ line }}</code>
      </div>
    </div>
  </div>
</template>

<style scoped>
.code-block {
  border: 1px solid var(--border-separator);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-2);
}

.code-block__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 16px;
  background: var(--border-separator-subtle);
  border-bottom: 1px solid var(--border-separator);
}

.code-block__label {
  font-size: 12px;
  font-weight: 400;
  line-height: 20px;
  color: var(--text-primary);
}

.code-block__copy-btn {
  height: 20px;
  padding: 0;
  color: var(--text-primary) !important;
  font-size: 12px;
  font-weight: 400;
  line-height: 20px;
}

.code-block__copy-btn:hover {
  color: var(--color-primary) !important;
}

.code-block__body {
  margin: 0;
  padding: 16px 0;
  overflow-x: auto;
  font-family: 'Consolas', 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  font-weight: 400;
  line-height: 20px;
  background: var(--bg-2);
}

.code-block__line {
  display: flex;
  align-items: flex-start;
  min-height: 20px;
  padding-right: 24px;
}

.code-block__line-no {
  flex: 0 0 40px;
  width: 40px;
  padding-right: 12px;
  text-align: right;
  color: #595959;
  user-select: none;
}

.code-block__line-text {
  flex: 1;
  min-width: 0;
  white-space: pre;
  color: var(--text-primary);
}
</style>
