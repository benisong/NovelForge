<template>
  <van-config-provider>
    <router-view />
  </van-config-provider>
</template>

<script setup>
</script>

<style>
/* 移动端基础重置 */
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  overflow: hidden; /* 防止全局滚动，交由内部组件控制 */
  background-color: #f7f8fa;
  font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, Segoe UI, Arial, Roboto, 'PingFang SC', 'miui', 'Hiragino Sans GB', 'Microsoft Yahei', sans-serif;
}

#app {
  height: 100%;
  width: 100%;
}
</style>
