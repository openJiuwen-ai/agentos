<script setup lang="ts">
import { useRouter } from 'vue-router';
import PerformanceMonitor from './PerformanceMonitor.vue';

const router = useRouter();

function goBack() {
  router.push({ name: 'inference-model' });
}
</script>

<template>
  <div class="detail-page">
    <header class="detail-page__banner">
      <div class="detail-page__banner-content">
        <button type="button" class="detail-page__back" @click="goBack">←</button>
        <h1 class="detail-page__title">推理模型详情</h1>
      </div>
    </header>

    <section class="detail-page__body">
      <PerformanceMonitor />
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
  min-height: 176px;
  padding: 28px 32px;
  background: linear-gradient(180deg, #fff 0%, rgb(255 255 255 / 0%) 100%);
}

.detail-page__banner-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.detail-page__back {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 4px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  color: #191919;
  font-size: 20px;
  line-height: 20px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.detail-page__back:hover {
  opacity: 0.7;
  background: transparent;
  color: #191919;
}

.detail-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: #191919;
}

.detail-page__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg-page);
}
</style>
