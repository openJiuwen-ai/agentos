<script setup lang="ts">
import { useRouter } from 'vue-router';
import { ElButton } from 'element-plus';
import CallAnalysis from './CallAnalysis.vue';
import arrowLeftIcon from '@/assets/images/arrow-left.svg';

const router = useRouter();

function goBack() {
  router.push({ name: 'inference-model-dashboard' });
}
</script>

<template>
  <div class="detail-page">
    <div class="detail-page__header">
      <ElButton class="detail-page__back" text @click="goBack">
        <img :src="arrowLeftIcon" alt="" class="detail-page__back-icon" width="20" height="20" />
      </ElButton>
      <h1 class="title-l1">推理模型调用分析</h1>
    </div>

    <div class="detail-page__body">
      <CallAnalysis />
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-height: 100%;
  padding: 24px 32px;
  box-sizing: border-box;
  background: var(--bg-page);
}

.detail-page__header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.detail-page__back {
  width: 20px;
  height: 20px;
  min-height: unset;
  padding: 0;
  margin: 0;
  border: none;
}

.detail-page__back :deep(> span) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.detail-page__back-icon {
  display: block;
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.detail-page__body {
  flex: 1;
  min-height: 0;
}
</style>
