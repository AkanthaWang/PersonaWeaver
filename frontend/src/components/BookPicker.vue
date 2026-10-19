<template>
  <el-select v-model="workspace.selectedId" placeholder="选择作品" filterable class="book-picker" :loading="workspace.loading" aria-label="当前作品">
    <el-option v-for="book in workspace.books" :key="book.book_id" :label="book.title" :value="book.book_id" />
  </el-select>
</template>
<script setup>
import { useWorkspaceStore } from "../stores/workspace";
const workspace = useWorkspaceStore();
</script>
