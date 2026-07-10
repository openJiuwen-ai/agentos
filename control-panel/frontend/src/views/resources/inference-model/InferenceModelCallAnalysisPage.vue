<script setup lang="ts">
import { useRouter } from 'vue-router';
import CallAnalysis from './CallAnalysis.vue';

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
  min-height: 120px;
  padding: 16px 24px;
  background: #fff;
}

.detail-page__banner-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.detail-page__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s;
}

.detail-page__back:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.detail-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.detail-page__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg-page);
}
</style>
