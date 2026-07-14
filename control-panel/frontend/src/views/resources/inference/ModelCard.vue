<script setup lang="ts">
import { ElTag, ElDropdown, ElDropdownMenu, ElDropdownItem, ElIcon } from 'element-plus';
import { Edit, Refresh, Delete, MoreFilled, ArrowUp, ArrowDown } from '@element-plus/icons-vue';

defineProps<{
  name: string;
  iconSrc?: string;
  status: 'success' | 'error' | 'warning';
  statusText: string;
  tags?: string[];
  e2eP95: string;
  e2eTrend?: string;
  todayCalls: string;
  todayTokens: string;
  meta?: string[];
}>();

const emit = defineEmits<{
  click: [];
  delete: [];
  edit: [];
  restart: [];
}>();

function handleAction(action: string) {
  if (action === 'edit') emit('edit');
  else if (action === 'restart') emit('restart');
  else if (action === 'delete') emit('delete');
}
</script>

<template>
  <div class="model-card" @click="$emit('click')">
    <div class="model-card__header">
      <div class="model-card__info">
        <div class="model-card__icon">
          <img v-if="iconSrc" :src="iconSrc" :alt="name" class="model-card__icon-img" />
          <slot v-else name="icon" />
        </div>
        <div>
          <div class="model-card__name-row">
            <span class="model-card__name">{{ name }}</span>
          </div>
          <div v-if="tags?.length" class="model-card__tags">
            <ElTag v-for="tag in tags" :key="tag" size="small" type="info">{{ tag }}</ElTag>
          </div>
        </div>
      </div>
      <div class="model-card__status" :class="`model-card__status--${status}`">
        <span class="model-card__status-dot"></span>
        {{ statusText }}
      </div>
    </div>
    <div class="model-card__metrics">
      <div class="model-metric">
        <span class="model-metric__label">E2E_P95</span>
        <span class="model-metric__value">
          {{ e2eP95 }}<span class="model-metric__unit"> S</span>
          <span v-if="e2eTrend" class="model-card__trend" :class="e2eTrend.startsWith('-') ? 'trend-down' : 'trend-up'">
            <el-icon :size="12"><ArrowDown v-if="e2eTrend.startsWith('-')" /><ArrowUp v-else /></el-icon>
            {{ e2eTrend }}
          </span>
        </span>
      </div>
      <div class="model-metric">
        <span class="model-metric__label">今日调用次数</span>
        <span class="model-metric__value">{{ todayCalls }}<span class="model-metric__unit"> 次</span></span>
      </div>
      <div class="model-metric">
        <span class="model-metric__label">今日 Token 数</span>
        <span class="model-metric__value">{{ todayTokens }}</span>
      </div>
    </div>
    <div class="model-card__footer">
      <span v-if="meta?.length" class="model-card__meta">{{ meta.join(' · ') }}</span>
      <ElDropdown trigger="click" @command="handleAction">
        <button class="model-card__more" title="更多" @click.stop>
          <el-icon :size="16"><MoreFilled /></el-icon>
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="edit">
              <el-icon><Edit /></el-icon>
              编辑信息
            </ElDropdownItem>
            <ElDropdownItem command="restart">
              <el-icon><Refresh /></el-icon>
              重启服务
            </ElDropdownItem>
            <el-dropdown-item divided command="delete">
              <span style="color: #ef4444">
                <el-icon><Delete /></el-icon>
                删除模型
              </span>
            </el-dropdown-item>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </div>
  </div>
</template>

<style scoped>
.model-card {
  background: linear-gradient(180deg, #e9f4ff 0%, rgba(237, 246, 255, 0.78) 22%, rgba(255, 255, 255, 0) 100%), #fff;
  border-radius: 24px;
  border: 2px solid #f3f3f3;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.model-card:hover {
  border-color: #dfdfdf;
}

.model-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.model-card__info {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.model-card__icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.model-card__icon-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 4px;
}

.model-card__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-card__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.model-card__tags {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.model-card__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #374151;
}

.model-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #9ca3af;
}

.model-card__status--success .model-card__status-dot {
  background: #22c55e;
}

.model-card__status--error .model-card__status-dot {
  background: #ef4444;
}

.model-card__status--warning .model-card__status-dot {
  background: #f59e0b;
}

.model-card__metrics {
  display: flex;
  gap: 32px;
  padding: 16px 0;
  border-top: 1px solid #f3f4f6;
  border-bottom: 1px solid #f3f4f6;
}

.model-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-card__meta {
  font-size: 12px;
  color: var(--text-secondary);
}

.model-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-metric__label {
  font-size: 12px;
  color: #6b7280;
}

.model-metric__value {
  font-size: 24px;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.model-metric__unit {
  font-size: 12px;
  font-weight: 400;
  color: #6b7280;
}

.model-card__trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 500;
  margin-left: 8px;
}

.trend-down {
  color: #22c55e;
}

.trend-up {
  color: #ef4444;
}

.model-card__more {
  border: none;
  background: none;
  cursor: pointer;
  padding: 6px;
  display: flex;
  align-items: center;
  border-radius: 6px;
  color: #9ca3af;
  transition: all 0.2s;
}

.model-card__more:hover {
  background: #f3f4f6;
  color: #6b7280;
}
</style>
