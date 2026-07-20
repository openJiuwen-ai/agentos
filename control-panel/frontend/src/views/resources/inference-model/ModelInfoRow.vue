<script setup lang="ts">
defineProps<{
  label: string;
  value?: string;
  span?: 'full' | 'half';
}>();
</script>

<template>
  <div class="info-row" :style="span === 'full' ? 'grid-column: span 2' : undefined">
    <span class="info-row__label">{{ label }}</span>
    <span class="info-row__value">
      <slot>{{ value ?? '--' }}</slot>
    </span>
  </div>
</template>
