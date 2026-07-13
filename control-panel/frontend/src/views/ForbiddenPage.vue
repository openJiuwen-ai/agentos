<template>
  <section class="page">
    <h1 class="page-title">403</h1>
    <p class="forbidden-msg">无权访问此页面</p>
    <router-link to="/overview" class="link">返回首页</router-link>
  </section>
</template>

<style scoped>
.forbidden-msg {
  margin: 16px 0;
  font-size: 16px;
  color: #777777;
}

.link {
  color: #0067d1;
  text-decoration: none;
}

.link:hover {
  text-decoration: underline;
}
</style>
