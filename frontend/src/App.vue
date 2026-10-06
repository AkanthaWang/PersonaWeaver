<template>
  <RouterView v-slot="{ Component, route }">
    <component :is="Component" v-if="route.meta.plain" />

    <AppLayout v-else>
      <KeepAlive>
        <component :is="Component" v-if="route.meta.keepAlive" />
      </KeepAlive>
      <component :is="Component" v-if="!route.meta.keepAlive" />
    </AppLayout>
  </RouterView>
</template>

<script setup>
import { RouterView } from "vue-router";
import AppLayout from "./components/AppLayout.vue";
</script>
