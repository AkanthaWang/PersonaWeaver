<template>
  <el-drawer :model-value="modelValue" :title="title || '章节原文'" size="min(100vw, 1000px)" append-to-body @close="$emit('update:modelValue', false)">
    <div class="reader" v-loading="loading">
      <nav aria-label="章节目录">
        <button v-for="chapter in chapters" :key="chapter.id" :class="{ active: selected?.id === chapter.id }" @click="read(chapter.id)">
          {{ chapter.chapter_no }}. {{ chapter.title }}
        </button>
      </nav>
      <section class="reader-content">
        <h2>{{ selected?.title }}</h2>
        <pre class="document-text">{{ parts[0] }}<mark v-if="parts[1]" ref="highlight">{{ parts[1] }}</mark>{{ parts[2] }}</pre>
        <el-empty v-if="!selected && !loading" description="暂无章节" />
      </section>
    </div>
  </el-drawer>
</template>
<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { api } from "../../../api/client";
import { report } from "../../../lib/ui";
import { citationParts } from "../citations";
const props = defineProps({ modelValue: Boolean, bookId: String, chapterId: String, citation: Object, title: String });
defineEmits(["update:modelValue"]);
const chapters = ref([]), selected = ref(null), loading = ref(false), highlight = ref(null);
let generation = 0;
const parts = computed(() => citationParts(selected.value?.content, selected.value?.id === props.citation?.chapter_id ? props.citation : null));
async function read(id) {
  const current = ++generation;
  loading.value = true;
  try {
    const result = await api.get(`/books/${props.bookId}/chapters/${id}`);
    if (current !== generation) return;
    selected.value = result;
    await nextTick();
    highlight.value?.scrollIntoView({ block: "center", behavior: "instant" });
  } catch (error) { if (current === generation) report(error); }
  finally { if (current === generation) loading.value = false; }
}
watch(() => [props.modelValue, props.bookId, props.chapterId, props.citation], async () => {
  const current = ++generation;
  if (!props.modelValue || !props.bookId) return;
  selected.value = null; chapters.value = []; loading.value = true;
  try {
    const result = await api.get(`/books/${props.bookId}/chapters`);
    if (current !== generation) return;
    chapters.value = result.chapters;
    const id = props.chapterId || props.citation?.chapter_id || chapters.value[0]?.id;
    if (id) await read(id);
  } catch (error) { if (current === generation) report(error); }
  finally { if (current === generation) loading.value = false; }
}, { immediate: true });
</script>
<style scoped>
.reader { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 24px; min-height: 70vh; }
nav { border-right: 1px solid #dfe4e1; padding-right: 12px; max-height: 78vh; overflow: auto; }
nav button { display: block; width: 100%; padding: 10px; margin-bottom: 4px; border: 0; border-radius: 4px; background: none; text-align: left; font: inherit; overflow-wrap: anywhere; cursor: pointer; }
nav button.active { color: #176758; background: #e4f3ec; }
.reader-content { min-width: 0; max-height: 78vh; overflow: auto; }
h2 { font-size: 20px; overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
mark { background: #fff0a8; color: #202c26; padding: 2px 0; }
@media (max-width: 700px) { .reader { grid-template-columns: minmax(0, 1fr); gap: 16px; } nav { max-height: 140px; border-right: 0; border-bottom: 1px solid #dfe4e1; } .reader-content { max-height: 55vh; } }
</style>
