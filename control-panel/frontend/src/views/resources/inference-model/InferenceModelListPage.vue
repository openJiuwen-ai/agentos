<script setup lang="ts">
import { useRouter } from 'vue-router';

interface InferenceModelItem {
  id: string;
  name: string;
  version: string;
  status: string;
}

const router = useRouter();

const modelList: InferenceModelItem[] = [
  { id: '1', name: 'Qwen2.5-72B', version: 'v1.0', status: '运行中' },
  { id: '2', name: 'DeepSeek-R1', version: 'v2.1', status: '运行中' },
  { id: '3', name: 'GLM-4-Air', version: 'v1.2', status: '已停止' },
];

function goToCallAnalysis() {
  router.push({ name: 'inference-model-call-analysis' });
}

function goToDetail(id: string) {
  router.push({ name: 'inference-model-detail', params: { id } });
}
</script>

<template>
  <section class="inference-page">
    <h1 class="inference-page__title">推理模型</h1>

    <section class="section-card">
      <div class="section-card__header">
        <h2 class="section-card__title">调用分析</h2>
        <button type="button" class="section-card__action" @click="goToCallAnalysis">查看详情</button>
      </div>
      <div class="section-card__body">
        <p class="section-card__summary">查看推理模型调用量、响应耗时与成功率等统计数据。</p>
      </div>
    </section>

    <section class="section-card">
      <div class="section-card__header">
        <h2 class="section-card__title">可用推理模型</h2>
      </div>
      <div class="section-card__body">
        <ul class="model-list">
          <li v-for="item in modelList" :key="item.id" class="model-card" @click="goToDetail(item.id)">
            <div class="model-card__info">
              <span class="model-card__name">{{ item.name }}</span>
              <span class="model-card__version">{{ item.version }}</span>
            </div>
            <span class="model-card__status" :class="{ 'model-card__status--active': item.status === '运行中' }">
              {{ item.status }}
            </span>
          </li>
        </ul>
      </div>
    </section>
  </section>
</template>

<style scoped>
.inference-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px 32px;
}

.inference-page__title {
  margin: 0;
  font-family: 'HarmonyOS Sans SC', 'HarmonyOS Sans', sans-serif;
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  color: #191919;
}

.section-card {
  border: none;
  border-radius: 8px;
  background: #fff;
  box-shadow: none;
}

.section-card:nth-child(3) {
  border-radius: 12px;
}

.section-card:nth-child(2) {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px 20px 24px;
}

.section-card:nth-child(3) {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px;
}

.section-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0;
}

.section-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #191919;
}

.section-card__action {
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  color: #0067d1;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.section-card__action:hover {
  opacity: 0.8;
  background: transparent;
}

.section-card__body {
  padding: 0;
}

.section-card__summary {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: #777777;
}

.model-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 28px;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 1200px) {
  .model-list {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .model-list {
    grid-template-columns: 1fr;
  }
}

.model-card {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  min-height: 244px;
  padding: 20px;
  border: 2px solid #f3f3f3;
  border-radius: 24px;
  background: linear-gradient(180deg, #e9f4ff 0%, rgb(237 246 255 / 78%) 22%, rgb(255 255 255 / 0%) 100%), #fff;
  box-shadow: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

.model-card:hover {
  border-color: #dfdfdf;
  box-shadow: none;
}

.model-card__info {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.model-card__name {
  font-size: 18px;
  font-weight: 500;
  line-height: 26px;
  color: #191919;
}

.model-card__version {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgb(208 216 253 / 50%);
  font-size: 12px;
  line-height: 20px;
  color: #1f55b5;
}

.model-card__status {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  color: #191919;
}

.model-card__status::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #aeaeae;
}

.model-card__status--active::before {
  background: #09aa71;
}
</style>
