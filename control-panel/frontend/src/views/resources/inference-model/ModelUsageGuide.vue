<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElTabs, ElTabPane, ElLink, ElButton } from 'element-plus';
import { CopyDocument } from '@element-plus/icons-vue';

const props = defineProps<{
  gatewayUrl?: string;
  exampleModelName?: string;
  exampleContextWindow?: number | null;
}>();

const router = useRouter();
const activeTab = ref('params');

function goToApiKeyPage() {
  void router.push({ name: 'inference-model-api-key' });
}

async function copyToClipboard(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(`${label} 已复制到剪贴板`);
  } catch {
    // 非安全上下文（HTTP/IP 访问）或低版本浏览器没有 ClipboardItem / navigator.clipboard，
    // 回退到 execCommand('copy')。
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    ElMessage.success(`${label} 已复制到剪贴板`);
  }
}

const gatewayBase = computed(() => props.gatewayUrl || 'http://<your-gateway>');

const modelName = computed(() => props.exampleModelName || 'deepseek-v4-flash');

const contextWindow = computed(() => props.exampleContextWindow ?? 131072);

const curlExample = computed(
  () => `curl -X POST "${gatewayBase.value}/v1/chat/completions" \\
  -H "Authorization: Bearer <<您的apikey>>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${modelName.value}",
    "messages": [{"role": "user", "content": "你好"}]
  }'`,
);

const jiuwenswarmYaml = computed(
  () => `models:
  defaults:
    - model_client_config:
        api_base: ${gatewayBase.value}/v1
        api_key: <<您的apikey>>
        model_name: ${modelName.value}
        client_provider: DeepSeek
        timeout: 1800
        verify_ssl: false
        custom_headers: {}
      model_config_obj:
        temperature: 0.95
      is_default: true`,
);

const modelAlias = computed(() =>
  props.exampleModelName ? props.exampleModelName.toLowerCase().replace(/[^a-z0-9.-]/g, '') : 'my-model',
);

const jiuwenswarmTuiCmd = computed(
  () =>
    `/model add ${modelAlias.value} api_base=${gatewayBase.value} model=${modelName.value} model_provider=OpenAI api_key=<<您的apikey>>`,
);
</script>

<template>
  <div class="card usage-guide-card">
    <h2 class="usage-guide-card__title">使用指南</h2>

    <ElTabs v-model="activeTab" class="usage-guide-card__tabs">
      <!-- 参数说明 -->
      <ElTabPane label="参数说明" name="params">
        <p class="usage-guide-card__desc">在调用推理模型前，请确认以下关键参数已正确配置：</p>
        <div class="usage-guide-card__table-wrap">
          <table class="usage-guide-card__table">
            <thead>
              <tr>
                <th>参数</th>
                <th>说明</th>
                <th>示例</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>api_key</code></td>
                <td>
                  API 认证密钥，用于验证调用方身份，请在
                  <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
                  页面申请
                </td>
                <td><code>&lt;&lt;您的apikey&gt;&gt;</code></td>
              </tr>
              <tr>
                <td><code>api_base</code> / <code>base_url</code></td>
                <td>模型服务的访问地址（LiteLLM Gateway 统一入口）</td>
                <td>
                  <code>{{ gatewayBase }}</code>
                </td>
              </tr>
              <tr>
                <td><code>model_name</code></td>
                <td>模型标识名称，指定要调用的具体模型</td>
                <td>
                  <code>{{ modelName }}</code>
                </td>
              </tr>
              <tr>
                <td><code>context_window</code></td>
                <td>模型支持的最大上下文长度（tokens），超出会截断或报错</td>
                <td>
                  <code>{{ contextWindow }}</code>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </ElTabPane>

      <!-- curl 示例 -->
      <ElTabPane label="curl 示例" name="curl">
        <p class="usage-guide-card__desc">
          通过 OpenAI 兼容接口直接调用已部署的模型，<code>&lt;&lt;您的apikey&gt;&gt;</code> 请替换为
          <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
          中申请的密钥：
        </p>
        <div class="usage-guide-card__code-block">
          <div class="usage-guide-card__code-header">
            <span class="usage-guide-card__code-label">Shell</span>
            <ElButton
              class="usage-guide-card__copy-btn"
              :icon="CopyDocument"
              text
              size="small"
              @click="copyToClipboard(curlExample, 'curl 示例')"
            >
              复制
            </ElButton>
          </div>
          <pre class="usage-guide-card__code"><code>{{ curlExample }}</code></pre>
        </div>
      </ElTabPane>

      <!-- JiuwenSwarm 客户端 接入 -->
      <ElTabPane label="JiuwenSwarm 客户端接入" name="jiuwenswarm">
        <p class="usage-guide-card__desc">
          在 JiuwenSwarm 配置文件<code>config.yaml</code> 的 <code>models</code> 字段中添加以下内容，即可将模型接入
          Agent 编排流程。请将 <code>api_key</code> 替换为
          <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
          中申请的密钥，<code>api_base</code> 和 <code>model_name</code> 替换为实际值：
        </p>
        <div class="usage-guide-card__code-block">
          <div class="usage-guide-card__code-header">
            <span class="usage-guide-card__code-label">YAML</span>
            <ElButton
              class="usage-guide-card__copy-btn"
              :icon="CopyDocument"
              text
              size="small"
              @click="copyToClipboard(jiuwenswarmYaml, 'JiuwenSwarm 配置')"
            >
              复制
            </ElButton>
          </div>
          <pre class="usage-guide-card__code"><code>{{ jiuwenswarmYaml }}</code></pre>
        </div>
      </ElTabPane>

      <!-- JiuwenSwarm TUI 接入 -->
      <ElTabPane label="JiuwenSwarm TUI 接入" name="jiuwenswarm-tui">
        <p class="usage-guide-card__desc">
          在 JiuwenSwarm TUI 中使用 <code>/model add</code> 命令添加模型，<code>&lt;&lt;您的apikey&gt;&gt;</code>
          请替换为
          <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
          中申请的密钥：
        </p>
        <div class="usage-guide-card__code-block">
          <div class="usage-guide-card__code-header">
            <span class="usage-guide-card__code-label">Shell</span>
            <ElButton
              class="usage-guide-card__copy-btn"
              :icon="CopyDocument"
              text
              size="small"
              @click="copyToClipboard(jiuwenswarmTuiCmd, 'JiuwenSwarm TUI 命令')"
            >
              复制
            </ElButton>
          </div>
          <pre class="usage-guide-card__code"><code>{{ jiuwenswarmTuiCmd }}</code></pre>
        </div>
      </ElTabPane>
    </ElTabs>
  </div>
</template>

<style scoped>
.usage-guide-card {
  background: var(--bg-2);
  border-radius: var(--radius-2xl);
  padding: 24px;
  flex-shrink: 0;
}

.usage-guide-card__title {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.usage-guide-card__tabs {
  --el-tabs-header-height: 36px;
}

.usage-guide-card__tabs :deep(.el-tab-pane) {
  min-height: 360px;
}

.usage-guide-card__desc {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.usage-guide-card__desc :deep(.el-link),
.usage-guide-card__table :deep(.el-link) {
  font-size: inherit;
  vertical-align: baseline;
}

.usage-guide-card__desc code {
  background: var(--bg-3, #f0f0f0);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--text-primary);
}

/* 参数表格 */
.usage-guide-card__table-wrap {
  overflow-x: auto;
}

.usage-guide-card__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.usage-guide-card__table th,
.usage-guide-card__table td {
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.usage-guide-card__table th {
  background: var(--bg-3, #f8f8f8);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.usage-guide-card__table td {
  color: var(--text-secondary);
}

.usage-guide-card__table code {
  background: var(--bg-3, #f0f0f0);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--text-primary);
}

/* 代码块 */
.usage-guide-card__code-block {
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.usage-guide-card__code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.usage-guide-card__code-label {
  font-size: 12px;
  color: #9ca3af;
}

.usage-guide-card__copy-btn {
  color: #9ca3af !important;
  font-size: 12px;
  cursor: pointer;
}

.usage-guide-card__copy-btn:hover {
  color: #fff !important;
}

.usage-guide-card__code {
  margin: 0;
  padding: 16px;
  overflow-x: auto;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: #e5e7eb;
}

.usage-guide-card__code code {
  white-space: pre;
}
</style>
