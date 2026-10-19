<template>
  <el-form class="model-selection" label-position="top" @submit.prevent="save">
    <div class="selection-heading">
      <h2>模型选用</h2>
      <p>从您已配置的模型仓库中，挑选用于特定功能的模型。如需添加新模型，请前往<button type="button" class="link-button" @click="$emit('manage', 'llm')">模型设置</button>。</p>
    </div>
    <section v-for="item in functions" :key="item.key" class="selection-section">
      <div class="selection-section-heading">
        <el-icon class="selection-icon"><component :is="item.icon" /></el-icon>
        <div><h3>{{ item.label }}</h3><p>{{ item.description }}</p></div>
      </div>
      <el-form-item :label="item.selectLabel" :class="{ 'selection-invalid': invalid(item) }">
        <el-select v-model="draft[item.field]" class="wide-control" :aria-label="item.selectLabel"
          :disabled="!groups(item.type).length && !draft[item.field]" :clearable="item.key !== 'reranker'"
          :placeholder="groups(item.type).length ? '请选择模型' : '暂无可用模型'" @clear="draft[item.field] = null">
          <el-option v-if="item.key === 'reranker'" :value="''" label="不使用（仅使用向量检索）" />
          <el-option v-if="invalid(item)" :value="draft[item.field]" :label="invalidLabel(item)" disabled />
          <el-option-group v-for="group in groups(item.type)" :key="group.name" :label="group.name">
            <el-option v-for="model in group.models" :key="model.id" :value="model.id"
              :label="`${model.name || model.model} · ${group.name}`">
              <span class="selection-option">{{ model.name || model.model }}<small>{{ model.model }}</small></span>
            </el-option>
          </el-option-group>
        </el-select>
        <p v-if="invalid(item)" class="selection-error" role="alert"><el-icon><WarningFilled /></el-icon>{{ invalidMessage(item) }}</p>
        <button v-if="!groups(item.type).length" type="button" class="selection-guide" @click="$emit('manage', item.type)">暂无可用模型，请先前往「模型设置」添加并测试连接<el-icon><ArrowRight /></el-icon></button>
        <p v-else-if="item.key === 'extraction'" class="field-help">仅显示已通过连接测试的大语言模型。已选模型被删除或不可用时会标红。</p>
      </el-form-item>
      <el-alert v-if="item.key === 'embedding'" :type="embeddingChanged ? 'warning' : 'info'" show-icon :closable="false"
        :title="embeddingChanged ? 'Embedding 模型已更改' : 'Embedding 索引'"
        description="切换 Embedding 模型可能导致现有知识库向量维度不匹配，需要重新索引。保存后，首次检索会自动重建所需索引。" />
      <el-form-item v-if="item.key === 'reranker' && draft.reranker_model_id" label="精排后保留结果数（Top-K）" class="reranker-top-k">
        <el-input-number v-model="draft.reranker_top_k" :min="1" :max="100" :precision="0" controls-position="right" aria-label="精排后保留结果数（Top-K）" />
      </el-form-item>
    </section>
    <div class="selection-actions">
      <el-button type="primary" native-type="submit" :icon="Check" :loading="saving" :disabled="!canSave">保存选用配置</el-button>
      <span v-if="dirty" class="selection-unsaved">有未保存的修改</span>
      <span v-else-if="saved" class="selection-saved" role="status">选用配置已保存</span>
    </div>
  </el-form>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ArrowRight, Check, Cpu, Search, Sort, WarningFilled } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { saveModelSelection } from "../client.js";
import { report } from "../../../lib/ui";

const props = defineProps({ profiles: { type: Array, required: true }, selection: { type: Object, required: true } });
const emit = defineEmits(["manage", "saved"]);
const fields = ["extraction_model_id", "embedding_model_id", "reranker_model_id", "reranker_top_k"];
const draft = reactive({ extraction_model_id: null, embedding_model_id: null, reranker_model_id: "", reranker_top_k: 5 });
const saving = ref(false), saved = ref(false);
const functions = [
  { key: "extraction", field: "extraction_model_id", type: "llm", label: "提取模型", selectLabel: "选择提取模型", icon: Cpu, description: "用于从故事资料中提取实体、关系或关键剧情。" },
  { key: "embedding", field: "embedding_model_id", type: "embedding", label: "Embedding 模型", selectLabel: "选择 Embedding 模型", icon: Search, description: "用于将故事文本向量化，支持语义检索。" },
  { key: "reranker", field: "reranker_model_id", type: "reranker", label: "Reranker 模型", selectLabel: "选择 Reranker 模型", icon: Sort, description: "对向量检索结果进行二次精排，提高上下文质量。不选择时跳过精排阶段。" },
];
watch(() => fields.map((field) => props.selection[field]), () => {
  for (const field of fields) draft[field] = props.selection[field] ?? (field === "reranker_top_k" ? 5 : field === "reranker_model_id" ? "" : null);
}, { immediate: true });
const dirty = computed(() => fields.some((field) => (draft[field] || null) !== (props.selection[field] || null)));
const embeddingChanged = computed(() => Boolean(props.selection.embedding_model_id) && draft.embedding_model_id !== props.selection.embedding_model_id);
function groups(type) {
  const result = new Map();
  for (const model of props.profiles.filter((model) => (model.model_type || "llm") === type && model.test_status === "passed")) {
    const name = model.provider_name || model.provider;
    if (!result.has(name)) result.set(name, { name, models: [] });
    result.get(name).models.push(model);
  }
  return [...result.values()];
}
function invalid(item) {
  const id = draft[item.field];
  return Boolean(id) && !props.profiles.some((model) => model.id === id && (model.model_type || "llm") === item.type && model.test_status === "passed");
}
function invalidLabel(item) {
  const model = props.profiles.find((model) => model.id === draft[item.field]) || props.selection.statuses?.[item.key]?.model;
  return model ? `${model.name || model.model}（不可用）` : "已删除的模型";
}
function invalidMessage(item) {
  if (!props.profiles.some((model) => model.id === draft[item.field])) return "该模型已被删除，请重新选择";
  return props.selection.statuses?.[item.key]?.message || "该模型不可用，请重新测试连接或选择其他模型";
}
const canSave = computed(() => Boolean(props.selection.statuses) && !functions.some(invalid) && Number.isInteger(draft.reranker_top_k) && draft.reranker_top_k >= 1 && draft.reranker_top_k <= 100);
async function save() {
  if (saving.value || !canSave.value) return;
  saving.value = true;
  try {
    const result = await saveModelSelection({ ...draft, reranker_model_id: draft.reranker_model_id || null });
    emit("saved", result);
    saved.value = true;
    ElMessage.success("选用配置已保存");
  } catch (error) { report(error); } finally { saving.value = false; }
}
</script>

<style scoped src="../../../styles/model-selection.css"></style>
