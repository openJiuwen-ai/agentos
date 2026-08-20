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
        <div class="model-card__identity">
          <div class="model-card__name-row">
            <span class="model-card__name">{{ name }}</span>
          </div>
          <div v-if="tags?.length" class="model-card__tags">
            <ElTag v-for="tag in tags" :key="tag" size="small" effect="light" class="model-card__tag">
              {{ tag }}
            </ElTag>
          </div>
        </div>
      </div>
      <div class="model-card__status" :class="`model-card__status--${status}`">
        <span class="model-card__status-dot"></span>
        <span class="model-card__status-text">{{ statusText }}</span>
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
      <span v-else class="model-card__meta"></span>
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
  background: var(--bg-2);
  border-radius: var(--radius-2xl);
  border: none;
  padding: 20px 24px;
  cursor: pointer;
  transition: box-shadow 0.2s;
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
  box-sizing: border-box;
}

.model-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.model-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.model-card__info {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  min-width: 0;
}

.model-card__icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--bg-1);
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

.model-card__identity {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.model-card__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.model-card__name {
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card__tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.model-card__tag {
  --el-tag-bg-color: rgba(208, 216, 253, 0.5);
  --el-tag-border-color: transparent;
  --el-tag-text-color: #1f55b5;
  height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}

.model-card__status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-top: 2px;
}

.model-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.model-card__status-text {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-primary);
}

.model-card__status--success .model-card__status-dot {
  background: #36c18d;
}

.model-card__status--error .model-card__status-dot {
  background: #e02128;
}

.model-card__status--warning .model-card__status-dot {
  background: var(--alert);
}

.model-card__info-section {
  display: flex;
  gap: 24px;
  padding-bottom: 4px;
}

.model-info-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.model-info-item__label {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
}

.model-info-item__value {
  font-size: 28px;
  font-weight: 700;
  line-height: 36px;
  color: var(--text-primary);
  opacity: 0.89;
}

.model-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.model-card__meta {
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card__more {
  width: 16px;
  height: 16px;
  padding: 0;
  min-height: unset;
  color: var(--text-secondary);
}

.model-card__more:hover {
  color: var(--text-primary);
}

.model-card__delete {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--error);
}
</style>
