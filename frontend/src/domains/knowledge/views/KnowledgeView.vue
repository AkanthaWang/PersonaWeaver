<template>
  <header class="page-header page-header-compact">
    <div><p class="eyebrow">KNOWLEDGE BASE</p><h1>知识库</h1></div>
    <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
  </header>
  <section class="toolbar">
    <el-select v-model="bookId" placeholder="选择作品" filterable @change="load">
      <el-option v-for="book in workspace.books" :key="book.book_id" :label="book.title" :value="book.book_id" />
    </el-select>
    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="人物" name="characters" />
      <el-tab-pane label="事件" name="events" />
      <el-tab-pane label="关系" name="relations">
        <div v-if="tab === 'relations' && bookId" class="relations-content">
          <div class="relations-toolbar">
            <el-input
              v-model="searchQuery"
              placeholder="搜索人物"
              :prefix-icon="Search"
              clearable
              @input="handleSearch"
            />
            <el-button :icon="DataLine" @click="showGraph = !showGraph">
              {{ showGraph ? '表格视图' : '图谱视图' }}
            </el-button>
          </div>
          
          <div v-if="showGraph" class="graph-container">
            <div v-loading="graphLoading" class="graph-content">
              <div v-if="graphError" class="error-message">
                {{ graphError }}
              </div>
              <div v-else-if="!graphCharacters.length" class="empty-message">
                暂无人物关系数据
              </div>
              <div v-else ref="graphContainer" class="graph-canvas"></div>
            </div>
          </div>
          
          <el-table v-else :data="rows" empty-text="暂无关系记录">
            <el-table-column label="关系" min-width="300"><template #default="{ row }">
              <span class="relation-subject">{{ getCharacterName(row.subject_id) }}</span>
              <el-tag :type="getRelationTypeColor(row.relation_type)" size="small" class="relation-tag">
                {{ getRelationTypeName(row.relation_type) }}
              </el-tag>
              <span class="relation-object">{{ getCharacterName(row.object_id) }}</span>
            </template></el-table-column>
            <el-table-column label="关系强度" width="120">
              <template #default="{ row }">
                <el-progress :percentage="row.value_json?.strength || 50" :stroke-width="6" />
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180" />
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane label="伏笔" name="clues" />
      <el-tab-pane label="待审核" name="reviews" />
    </el-tabs>
  </section>
  <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
  <el-table v-loading="loading" :data="rows" empty-text="暂无知识记录">
    <el-table-column v-if="tab === 'characters'" prop="canonical_name" label="人物" min-width="160" />
    <el-table-column v-if="tab === 'characters'" label="别名" min-width="200"><template #default="{ row }">{{ aliases(row.aliases_json) }}</template></el-table-column>
    <el-table-column v-if="tab === 'events'" prop="title" label="事件" min-width="180" />
    <el-table-column v-if="tab === 'events'" prop="description" label="描述" min-width="300" show-overflow-tooltip />
    <el-table-column v-if="tab === 'relations'" label="关系" min-width="300"><template #default="{ row }">{{ row.subject_id }} → {{ row.relation_type }} → {{ row.object_id }}</template></el-table-column>
    <el-table-column v-if="tab === 'clues'" prop="title" label="线索" min-width="180" />
    <el-table-column v-if="tab === 'clues'" prop="state" label="状态" width="130" />
    <el-table-column v-if="tab === 'reviews'" prop="review_type" label="审核类型" width="140" />
    <el-table-column v-if="tab === 'reviews'" prop="payload_json" label="内容" min-width="360" show-overflow-tooltip />
    <el-table-column v-if="tab === 'reviews'" label="操作" width="180" fixed="right">
      <template #default="{ row }">
        <el-button size="small" type="success" @click="resolve(row, 'approve')">通过</el-button>
        <el-button size="small" type="danger" @click="resolve(row, 'reject')">拒绝</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from "vue";
import { Refresh, Search, DataLine } from "@element-plus/icons-vue";
import { Graph } from "@antv/g6";
import { api } from "../../../api/client.js";
import { useWorkspaceStore } from "../../../stores/workspace.js";
import { report } from "../../../lib/ui.js";

const workspace = useWorkspaceStore();
const bookId = ref(workspace.selectedId), tab = ref("characters");
const rows = ref([]), loading = ref(false), error = ref("");
const showGraph = ref(false);
const searchQuery = ref("");
const graphLoading = ref(false);
const graphError = ref("");
const graphCharacters = ref([]);
const graphRelations = ref([]);
const graphContainer = ref(null);
const graph = ref(null);

const aliases = (value) => { try { return JSON.parse(value || "[]").join("、"); } catch { return ""; } };

// 关系类型映射
const relationTypeMap = {
  'family': '家庭关系',
  'friend': '朋友关系', 
  'lover': '恋人关系',
  'enemy': '敌对关系',
  'colleague': '同事关系',
  'mentor': '导师关系',
  'student': '学生关系',
  'ally': '盟友关系',
  'neutral': '中立关系'
};

// 获取关系类型颜色
function getRelationTypeColor(type) {
  const colorMap = {
    'family': 'danger',
    'lover': 'warning',
    'friend': 'success',
    'ally': 'primary',
    'colleague': 'info',
    'mentor': 'warning',
    'student': 'success',
    'enemy': 'danger',
    'neutral': ''
  };
  return colorMap[type] || '';
}

// 获取关系类型名称
function getRelationTypeName(type) {
  return relationTypeMap[type] || type;
}

// 获取人物名称
function getCharacterName(characterId) {
  const character = graphCharacters.value.find(char => char.id === characterId);
  return character ? character.canonical_name : characterId;
}

// 加载图谱数据
async function loadGraphData() {
  if (!bookId.value) return;
  
  graphLoading.value = true;
  graphError.value = '';
  
  try {
    const [charactersResult, relationsResult] = await Promise.all([
      api.get('/knowledge/characters', { params: { book_id: bookId.value } }),
      api.get('/knowledge/relations', { params: { book_id: bookId.value } })
    ]);
    
    graphCharacters.value = charactersResult.characters || [];
    graphRelations.value = relationsResult.relations || [];
    
    // 过滤掉被删除的人物和关系
    graphCharacters.value = graphCharacters.value.filter(char => char.state === 'active');
    graphRelations.value = graphRelations.value.filter(rel => rel.state === 'active');
    
    // 过滤关系，确保相关人物都存在
    graphRelations.value = graphRelations.value.filter(rel => {
      const subjectExists = graphCharacters.value.some(char => 
        char.id === rel.subject_id && char.state === 'active'
      );
      const objectExists = graphCharacters.value.some(char => 
        char.id === rel.object_id && char.state === 'active'
      );
      return subjectExists && objectExists;
    });
    
    renderGraph();
  } catch (err) {
    graphError.value = '加载人物关系数据失败';
    console.error(err);
  } finally {
    graphLoading.value = false;
  }
}

// 渲染图谱
function renderGraph() {
  if (!graphContainer.value || !graphCharacters.value.length) return;
  
  // 清理之前的图谱
  if (graph.value) {
    graph.value.destroy();
  }
  
  // 构建图谱数据
  const nodes = graphCharacters.value.map(char => ({
    id: char.id,
    label: char.canonical_name,
    x: Math.random() * 800,
    y: Math.random() * 600,
    style: {
      fill: '#409eff',
      stroke: '#1e40af',
      lineWidth: 2
    },
    labelCfg: {
      style: {
        fill: '#333',
        fontSize: 12,
        fontWeight: 'bold'
      }
    },
    size: 40 + (char.frequency || 0) * 2
  }));
  
  const edges = graphRelations.value.map(rel => {
    const relationType = rel.relation_type || 'neutral';
    const edgeStyle = {
      stroke: getEdgeColor(relationType),
      lineWidth: Math.max(1, (rel.value_json?.strength || 1) * 2)
    };
    
    return {
      source: rel.subject_id,
      target: rel.object_id,
      label: relationTypeMap[relationType] || relationType,
      style: edgeStyle,
      labelCfg: {
        style: {
          fill: '#666',
          fontSize: 10
        },
        refY: -10
      }
    };
  });
  
  // 创建图谱实例
  graph.value = new Graph({
    container: graphContainer.value,
    width: graphContainer.value.clientWidth,
    height: 600,
    modes: {
      default: [
        'drag-node',
        'zoom-canvas',
        'drag-canvas',
        'tooltip'
      ]
    },
    data: {
      nodes,
      edges
    },
    layout: {
      type: 'force',
      nodeSize: 40,
      preventOverlap: true,
      alphaDecay: 0.028,
      minMovement: 0.1,
      collide: {
        strength: 100
      },
      link: {
        distance: 100
      }
    },
    fitView: true,
    animate: true
  });
  
  // 绑定事件
  graph.value.on('node:click', (evt) => {
    const node = evt.item;
    showCharacterDetail(node.getModel());
  });
  
  // 渲染图谱
  graph.value.render();
}

// 获取边的颜色
function getEdgeColor(relationType) {
  const colorMap = {
    'family': '#ff6b6b',
    'lover': '#ff69b4',
    'friend': '#51cf66',
    'ally': '#339af0',
    'colleague': '#845ef7',
    'mentor': '#fd7e14',
    'student': '#20c997',
    'enemy': '#fa5252',
    'neutral': '#868e96'
  };
  return colorMap[relationType] || '#868e96';
}

// 显示人物详情
function showCharacterDetail(character) {
  const characterData = graphCharacters.value.find(char => char.id === character.id);
  if (characterData) {
    const detailHtml = `
      <div style="padding: 20px;">
        <h3 style="margin: 0 0 10px 0; color: #409eff;">${characterData.canonical_name}</h3>
        <p style="margin: 5px 0;"><strong>出现频率:</strong> ${characterData.frequency || 0}</p>
        <p style="margin: 5px 0;"><strong>别名:</strong> ${JSON.parse(characterData.aliases_json || '[]').join(', ') || '无'}</p>
        <div style="margin-top: 15px;">
          <h4 style="margin: 0 0 10px 0;">相关关系:</h4>
          ${getRelationshipsForCharacter(character.id)}
        </div>
      </div>
    `;
    
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = detailHtml;
    tempDiv.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      z-index: 1000;
      max-width: 400px;
      max-height: 500px;
      overflow-y: auto;
    `;
    
    document.body.appendChild(tempDiv);
    
    const closeHandler = (e) => {
      if (!tempDiv.contains(e.target)) {
        document.body.removeChild(tempDiv);
        document.removeEventListener('click', closeHandler);
      }
    };
    setTimeout(() => {
      document.addEventListener('click', closeHandler);
    }, 100);
  }
}

// 获取人物的关系
function getRelationshipsForCharacter(characterId) {
  const relatedRelations = graphRelations.value.filter(rel => 
    rel.subject_id === characterId || rel.object_id === characterId
  );
  
  if (!relatedRelations.length) return '<p style="color: #999;">暂无关系记录</p>';
  
  return relatedRelations.map(rel => {
    const otherCharacterId = rel.subject_id === characterId ? rel.object_id : rel.subject_id;
    const otherCharacter = graphCharacters.value.find(char => char.id === otherCharacterId);
    const relationType = rel.relation_type || 'neutral';
    const direction = rel.subject_id === characterId ? '→' : '←';
    
    return `
      <div style="margin: 5px 0; padding: 5px; background: #f8f9fa; border-radius: 4px;">
        <strong>${otherCharacter?.canonical_name || '未知人物'}</strong>
        <span style="color: #666; margin: 0 5px;">${direction}</span>
        <span style="color: ${getEdgeColor(relationType)};">${relationTypeMap[relationType] || relationType}</span>
      </div>
    `;
  }).join('');
}

// 搜索处理
function handleSearch() {
  if (!searchQuery.value.trim()) {
    renderGraph();
    return;
  }
  
  const filteredCharacters = graphCharacters.value.filter(char => 
    char.canonical_name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    JSON.parse(char.aliases_json || '[]').some(alias => 
      alias.toLowerCase().includes(searchQuery.value.toLowerCase())
    )
  );
  
  // 更新图谱节点
  if (graph.value) {
    const updatedNodes = filteredCharacters.map(char => ({
      id: char.id,
      label: char.canonical_name,
      style: {
        fill: '#409eff',
        stroke: '#1e40af',
        lineWidth: 2
      },
      labelCfg: {
        style: {
          fill: '#333',
          fontSize: 12,
          fontWeight: 'bold'
        }
      },
      size: 40 + (char.frequency || 0) * 2
    }));
    
    graph.value.updateData({
      nodes: updatedNodes,
      edges: graphRelations.value.filter(rel => 
        filteredCharacters.some(char => char.id === rel.subject_id) &&
        filteredCharacters.some(char => char.id === rel.object_id)
      )
    });
  }
}

// 适应容器大小变化
function handleResize() {
  if (graph.value && graphContainer.value) {
    graph.value.changeSize(
      graphContainer.value.clientWidth,
      600
    );
    graph.value.fitView();
  }
}

async function load() {
  if (!bookId.value) return;
  loading.value = true; error.value = "";
  try {
    rows.value = await api.get(`/books/${bookId.value}/knowledge/${tab.value}`);
    
    // 如果切换到关系标签页且显示图谱，则加载图谱数据
    if (tab.value === 'relations' && showGraph.value) {
      await loadGraphData();
    }
  } catch (err) { error.value = err.message; } finally { loading.value = false; }
}

async function resolve(row, action) {
  try {
    await api.post(`/books/${bookId.value}/knowledge/reviews/${row.id}/resolve`, { action });
    await load();
  } catch (err) { report(err); }
}

watch(() => workspace.selectedId, (value) => { bookId.value = value; load(); }, { immediate: true });

// 监听标签页变化
watch(() => tab.value, (newTab) => {
  if (newTab === 'relations' && showGraph.value) {
    loadGraphData();
  }
});

// 监听图谱显示状态
watch(showGraph, (newValue) => {
  if (newValue && tab.value === 'relations') {
    loadGraphData();
  }
});

onMounted(() => {
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  if (graph.value) {
    graph.value.destroy();
  }
  window.removeEventListener('resize', handleResize);
});
</script>

<style scoped>
.relations-content {
  margin-top: 20px;
}

.relations-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  align-items: center;
}

.graph-container {
  margin-top: 20px;
}

.graph-content {
  position: relative;
}

.graph-canvas {
  width: 100%;
  height: 600px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #fafafa;
}

.error-message {
  color: #f56c6c;
  text-align: center;
  padding: 40px;
  background: #fef0f0;
  border-radius: 8px;
}

.empty-message {
  color: #909399;
  text-align: center;
  padding: 40px;
  background: #f4f4f5;
  border-radius: 8px;
}

.relation-subject {
  color: #409eff;
  font-weight: 500;
}

.relation-tag {
  margin: 0 8px;
}

.relation-object {
  color: #67c23a;
  font-weight: 500;
}
</style>
