<script setup lang="ts">
import { useRouter } from 'vue-router';
import { ElResult, ElButton } from 'element-plus';

const router = useRouter();

function goHome() {
  router.push({ name: 'overview' });
}
</script>

<template>
  <section class="page">
    <ElResult icon="warning" title="403" sub-title="无权访问此页面">
      <template #extra>
        <ElButton type="primary" @click="goHome">返回首页</ElButton>
      </template>
    </ElResult>
  </section>
</template>
