<script setup lang="ts">
import { ElTag, ElDropdown, ElDropdownMenu, ElDropdownItem, ElIcon, ElButton } from 'element-plus';
import { Edit, Refresh, Delete, MoreFilled, Monitor } from '@element-plus/icons-vue';

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
  contextWindow?: number | null;
  isAdmin?: boolean;
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
          <slot v-else name="icon">
            <ElIcon :size="24" color="#6b7280"><Monitor /></ElIcon>
          </slot>
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
    <div class="model-card__info-section">
      <div class="model-info-item">
        <span class="model-info-item__label">上下文长度</span>
        <span class="model-info-item__value">{{ contextWindow ?? '-' }}</span>
      </div>
    </div>
    <div class="model-card__footer">
      <span v-if="meta?.length" class="model-card__meta">{{ meta.join(' · ') }}</span>
      <ElDropdown v-if="isAdmin" trigger="click" @command="handleAction">
        <ElButton class="model-card__more" text :icon="MoreFilled" title="更多" @click.stop />
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="edit">
              <ElIcon><Edit /></ElIcon>
              编辑信息
            </ElDropdownItem>
            <ElDropdownItem command="restart">
              <ElIcon><Refresh /></ElIcon>
              重启服务
            </ElDropdownItem>
            <ElDropdownItem divided command="delete">
              <span class="model-card__delete">
                <ElIcon><Delete /></ElIcon>
                删除模型
              </span>
            </ElDropdownItem>
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
  border: 2px solid var(--border-separator-subtle);
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.model-card:hover {
  border-color: var(--border-separator);
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
  background: var(--bg-2);
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
  color: var(--text-primary);
}

.model-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.model-card__status--success .model-card__status-dot {
  background: var(--success);
}

.model-card__status--error .model-card__status-dot {
  background: var(--error);
}

.model-card__status--warning .model-card__status-dot {
  background: var(--alert);
}

.model-card__info-section {
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

.model-info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-info-item__label {
  font-size: 12px;
  color: var(--text-secondary);
}

.model-info-item__value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.model-card__more {
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-secondary);
}

.model-card__more:hover {
  color: var(--text-secondary);
}

.model-card__delete {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--error);
}
</style>
