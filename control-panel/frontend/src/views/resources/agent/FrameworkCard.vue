<script setup lang="ts">
import type { FrameworkItem } from '@/api/framework';
import defaultIcon from '@/assets/images/framework-page/default-framework-icon.png';

defineProps<{
  framework: FrameworkItem;
  mode: 'grid' | 'list';
}>();

function onIconError(e: Event) {
  const img = e.target as HTMLImageElement;
  img.src = defaultIcon;
}
</script>

<template>
  <div
    class="framework-card"
    :class="mode === 'grid' ? 'framework-card--grid' : 'framework-card--list'"
  >
    <img
      :src="defaultIcon"
      :alt="framework.agent_name"
      class="framework-card__icon"
      :class="mode === 'grid' ? 'framework-card__icon--grid' : 'framework-card__icon--list'"
      @error="onIconError"
    />
    <div class="framework-card__info">
      <span class="framework-card__name">{{ framework.agent_name }}</span>
      <span class="framework-card__version">v{{ framework.version }}</span>
    </div>
  </div>
</template>

<style scoped>
.framework-card {
  background: rgba(255, 255, 255, 1);
  border-radius: 8px;
  display: flex;
}

/* ── Grid mode ── */
.framework-card--grid {
  width: 100%;
  height: 108px;
  flex-direction: row;
  justify-content: flex-start;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
}

.framework-card--grid .framework-card__info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.framework-card__icon--grid {
  width: 52px;
  height: 52px;
  border-radius: 13px;
  border: 1.08px solid var(--border-separator);
  box-shadow: 0px 1.08px 6.5px 0px rgba(0, 0, 0, 0.08);
  object-fit: contain;
  flex-shrink: 0;
}

/* ── List mode ── */
.framework-card--list {
  width: 100%;
  flex-direction: row;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
}

.framework-card--list .framework-card__info {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 12px;
}

.framework-card__icon--list {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-separator);
  object-fit: contain;
  flex-shrink: 0;
}

/* ── Shared typography ── */
.framework-card__name {
  font-size: 20px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 28px;
}

.framework-card__version {
  display: inline-block;
  width: fit-content;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-primary);
  background: rgba(25, 25, 25, 0.05);
  border-radius: 4px;
  padding: 2px 8px;
  line-height: 20px;
  white-space: nowrap;
}
</style>
