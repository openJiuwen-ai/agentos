<script setup lang="ts">
import { useRouter } from 'vue-router';
import { ElButton } from 'element-plus';
import { ArrowLeft } from '@element-plus/icons-vue';
import CallAnalysis from './CallAnalysis.vue';

const router = useRouter();

function goBack() {
  router.push({ name: 'inference-model-dashboard' });
}
</script>

<template>
  <div class="detail-page">
    <header class="detail-page__banner">
      <div class="detail-page__banner-content">
        <ElButton class="detail-page__back" text :icon="ArrowLeft" @click="goBack" />
        <h1 class="detail-page__title">推理模型调用分析</h1>
      </div>
    </header>

    <section class="detail-page__body">
      <CallAnalysis />
    </section>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.detail-page__banner {
  padding: 12px 32px;
}

.detail-page__banner-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.detail-page__back {
  width: 36px;
  height: 36px;
  padding: 0;
  color: var(--text-secondary);
}

.detail-page__back:hover {
  color: var(--text-primary);
}

.detail-page__title {
  margin: 0;
  font-style: normal;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  letter-spacing: 0;
  color: var(--text-primary);
}

.detail-page__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg-page);
}
</style>
