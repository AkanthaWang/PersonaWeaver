<template>
  <div class="relationship-graph-container">
    <div class="graph-toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索人物"
        :prefix-icon="Search"
        clearable
        @input="handleSearch"
      />
      <el-button :icon="Refresh" :loading="loading" @click="loadData" />
      <el-select v-model="selectedBook" placeholder="选择书籍" @change="handleBookChange">
        <el-option
          v-for="book in books"
          :key="book.book_id"
          :label="book.title"
          :value="book.book_id"
        />
      </el-select>
    </div>
    
    <div v-loading="loading" class="graph-content">
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
      <div v-else-if="!characters.length" class="empty-message">
        暂无人物数据
      </div>
      <div v-else ref="graphContainer" class="graph-canvas"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { Graph } from '@antv/g6'
import { api, getBooks } from '../../../api/client'
import { useWorkspaceStore } from '../../../stores/workspace'

const workspace = useWorkspaceStore()
const graphContainer = ref(null)
const graph = ref(null)
const characters = ref([])
const relationships = ref([])
const books = ref([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const selectedBook = ref(null)

// 人物关系类型映射
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
}

// 获取所有书籍
async function loadBooks() {
  try {
    const result = await getBooks()
    books.value = result.books
    if (books.value.length > 0) {
      selectedBook.value = books.value[0].book_id
    }
  } catch (err) {
    error.value = '加载书籍列表失败'
    console.error(err)
  }
}

// 加载人物关系数据
async function loadData() {
  if (!selectedBook.value) return
  
  loading.value = true
  error.value = ''
  
  try {
    const [charactersResult, relationshipsResult] = await Promise.all([
      api.get('/knowledge/characters', { params: { book_id: selectedBook.value } }),
      api.get('/knowledge/relations', { params: { book_id: selectedBook.value } })
    ])
    
    characters.value = charactersResult.characters || []
    relationships.value = relationshipsResult.relations || []
    
    // 过滤掉被删除的人物
    characters.value = characters.value.filter(char => char.state === 'active')
    
    // 过滤掉被删除的关系
    relationships.value = relationships.value.filter(rel => rel.state === 'active')
    
    // 过滤关系，确保相关人物都存在
    relationships.value = relationships.value.filter(rel => {
      const subjectExists = characters.value.some(char => 
        char.id === rel.subject_id && char.state === 'active'
      )
      const objectExists = characters.value.some(char => 
        char.id === rel.object_id && char.state === 'active'
      )
      return subjectExists && objectExists
    })
    
    renderGraph()
  } catch (err) {
    error.value = '加载人物关系数据失败'
    console.error(err)
  } finally {
    loading.value = false
  }
}

// 渲染图谱
function renderGraph() {
  if (!graphContainer.value || !characters.value.length) return
  
  // 清理之前的图谱
  if (graph.value) {
    graph.value.destroy()
  }
  
  // 构建图谱数据
  const nodes = characters.value.map(char => ({
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
  }))
  
  const edges = relationships.value.map(rel => {
    const relationType = rel.relation_type || 'neutral'
    const edgeStyle = {
      stroke: getEdgeColor(relationType),
      lineWidth: Math.max(1, (rel.value_json?.strength || 1) * 2)
    }
    
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
    }
  })
  
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
  })
  
  // 绑定事件
  graph.value.on('node:click', (evt) => {
    const node = evt.item
    showCharacterDetail(node.getModel())
  })
  
  // 渲染图谱
  graph.value.render()
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
  }
  return colorMap[relationType] || '#868e96'
}

// 显示人物详情
function showCharacterDetail(character) {
  const characterData = characters.value.find(char => char.id === character.id)
  if (characterData) {
    // 创建详情弹窗
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
    `
    
    // 创建临时div显示详情
    const tempDiv = document.createElement('div')
    tempDiv.innerHTML = detailHtml
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
    `
    
    document.body.appendChild(tempDiv)
    
    // 点击外部关闭
    const closeHandler = (e) => {
      if (!tempDiv.contains(e.target)) {
        document.body.removeChild(tempDiv)
        document.removeEventListener('click', closeHandler)
      }
    }
    setTimeout(() => {
      document.addEventListener('click', closeHandler)
    }, 100)
  }
}

// 获取人物的关系
function getRelationshipsForCharacter(characterId) {
  const relatedRelations = relationships.value.filter(rel => 
    rel.subject_id === characterId || rel.object_id === characterId
  )
  
  if (!relatedRelations.length) return '<p style="color: #999;">暂无关系记录</p>'
  
  return relatedRelations.map(rel => {
    const otherCharacterId = rel.subject_id === characterId ? rel.object_id : rel.subject_id
    const otherCharacter = characters.value.find(char => char.id === otherCharacterId)
    const relationType = rel.relation_type || 'neutral'
    const direction = rel.subject_id === characterId ? '→' : '←'
    
    return `
      <div style="margin: 5px 0; padding: 5px; background: #f8f9fa; border-radius: 4px;">
        <strong>${otherCharacter?.canonical_name || '未知人物'}</strong>
        <span style="color: #666; margin: 0 5px;">${direction}</span>
        <span style="color: ${getEdgeColor(relationType)};">${relationTypeMap[relationType] || relationType}</span>
      </div>
    `
  }).join('')
}

// 搜索处理
function handleSearch() {
  if (!searchQuery.value.trim()) {
    renderGraph()
    return
  }
  
  const filteredCharacters = characters.value.filter(char => 
    char.canonical_name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    JSON.parse(char.aliases_json || '[]').some(alias => 
      alias.toLowerCase().includes(searchQuery.value.toLowerCase())
    )
  )
  
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
    }))
    
    graph.value.updateData({
      nodes: updatedNodes,
      edges: relationships.value.filter(rel => 
        filteredCharacters.some(char => char.id === rel.subject_id) &&
        filteredCharacters.some(char => char.id === rel.object_id)
      )
    })
  }
}

// 书籍变更处理
function handleBookChange() {
  loadData()
}

// 适应容器大小变化
function handleResize() {
  if (graph.value && graphContainer.value) {
    graph.value.changeSize(
      graphContainer.value.clientWidth,
      600
    )
    graph.value.fitView()
  }
}

onMounted(async () => {
  await loadBooks()
  if (selectedBook.value) {
    await loadData()
  }
  
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (graph.value) {
    graph.value.destroy()
  }
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.relationship-graph-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.graph-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.graph-content {
  flex: 1;
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
</style>