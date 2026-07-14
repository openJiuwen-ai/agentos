<script setup lang="ts">
interface Column {
  key: string;
  label: string;
  color?: string;
}

defineProps<{
  columns: Column[];
  data: Record<string, any>[];
}>();
</script>

<template>
  <table class="data-table">
    <thead>
      <tr>
        <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, index) in data" :key="index">
        <td v-for="col in columns" :key="col.key">
          <span v-if="col.color" class="data-dot" :style="{ background: col.color }"></span>
          {{ row[col.key] }}
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.data-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
</style>
