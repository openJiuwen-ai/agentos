<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElTabs, ElTabPane, ElLink, ElTable, ElTableColumn } from 'element-plus';
import CodeBlock from '@/components/CodeBlock.vue';

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

const gatewayBase = computed(() => props.gatewayUrl || 'http://<your-gateway>');

const modelName = computed(() => props.exampleModelName || 'deepseek-v4-flash');

const contextWindow = computed(() => props.exampleContextWindow ?? 131072);

type ParamRow = {
  param: string;
  desc: string;
  example: string;
  linkApiKey?: boolean;
};

const paramRows = computed<ParamRow[]>(() => [
  {
    param: 'api_key',
    desc: 'API 认证密钥，用于验证调用方身份，请在 API Key 管理页面申请',
    example: '<<您的apikey>>',
    linkApiKey: true,
  },
  {
    param: 'api_base / base_url',
    desc: '模型服务的访问地址（LiteLLM Gateway 统一入口）',
    example: gatewayBase.value,
  },
  {
    param: 'model_name',
    desc: '模型标识名称，指定要调用的具体模型',
    example: modelName.value,
  },
  {
    param: 'context_window',
    desc: '模型支持的最大上下文长度（tokens），超出会截断或报错',
    example: String(contextWindow.value),
  },
]);

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
  <section class="usage-guide-section">
    <h2 class="title-l2">使用指南</h2>

    <div class="card usage-guide-card">
      <ElTabs v-model="activeTab" class="usage-guide-card__tabs">
        <!-- 参数说明 -->
        <ElTabPane label="参数说明" name="params">
          <p class="usage-guide-card__desc">在调用推理模型前，请确认以下关键参数已正确配置：</p>
          <ElTable :data="paramRows" class="app-table usage-guide-card__table" :border="false">
            <ElTableColumn label="参数" prop="param" min-width="160">
              <template #default="{ row }">
                <code>{{ row.param }}</code>
              </template>
            </ElTableColumn>
            <ElTableColumn label="说明" prop="desc" min-width="280">
              <template #default="{ row }">
                <template v-if="row.linkApiKey">
                  API 认证密钥，用于验证调用方身份，请在
                  <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
                  页面申请
                </template>
                <template v-else>{{ row.desc }}</template>
              </template>
            </ElTableColumn>
            <ElTableColumn label="示例" prop="example" min-width="200">
              <template #default="{ row }">
                <code>{{ row.example }}</code>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElTabPane>

        <!-- curl 示例 -->
        <ElTabPane label="curl 示例" name="curl">
          <p class="usage-guide-card__desc">
            通过 OpenAI 兼容接口直接调用已部署的模型，<code>&lt;&lt;您的apikey&gt;&gt;</code> 请替换为
            <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
            中申请的密钥：
          </p>
          <CodeBlock label="Shell" :code="curlExample" copy-label="curl 示例" />
        </ElTabPane>

        <!-- JiuwenSwarm 客户端 接入 -->
        <ElTabPane label="JiuwenSwarm 客户端接入" name="jiuwenswarm">
          <p class="usage-guide-card__desc">
            在 JiuwenSwarm 配置文件<code>config.yaml</code> 的 <code>models</code> 字段中添加以下内容，即可将模型接入
            Agent 编排流程。请将 <code>api_key</code> 替换为
            <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
            中申请的密钥，<code>api_base</code> 和 <code>model_name</code> 替换为实际值：
          </p>
          <CodeBlock label="YAML" :code="jiuwenswarmYaml" copy-label="JiuwenSwarm 配置" />
        </ElTabPane>

        <!-- JiuwenSwarm TUI 接入 -->
        <ElTabPane label="JiuwenSwarm TUI 接入" name="jiuwenswarm-tui">
          <p class="usage-guide-card__desc">
            在 JiuwenSwarm TUI 中使用 <code>/model add</code> 命令添加模型，<code>&lt;&lt;您的apikey&gt;&gt;</code>
            请替换为
            <ElLink type="primary" underline="never" @click="goToApiKeyPage">API Key 管理</ElLink>
            中申请的密钥：
          </p>
          <CodeBlock label="Shell" :code="jiuwenswarmTuiCmd" copy-label="JiuwenSwarm TUI 命令" />
        </ElTabPane>
      </ElTabs>
    </div>
  </section>
</template>

<style scoped>
.usage-guide-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
  flex-shrink: 0;
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

.usage-guide-card__desc code,
.usage-guide-card__table :deep(code) {
  background: var(--bg-3, #f0f0f0);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--text-primary);
}
</style>
