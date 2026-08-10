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
</style>
