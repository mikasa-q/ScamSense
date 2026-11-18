<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { useRouter } from 'vue-router'
import { useAccess } from './access'
import { auth, request, type Message } from './api'
const props = defineProps<{ role: string; name: string; message: string }>()
const router = useRouter(), access = useAccess()
const context = ref<Message[]>([]), error = ref('')
let generation = 0
async function load() {
  const turn = ++generation, saved = access.saved
  context.value = []; error.value = ''
  if (!saved || !('token' in saved)) { error.value = '缺少训练凭证。'; return }
  try {
    const history = await request<{items: Message[]}>('/sessions/' + saved.id + '/messages?role_id=' + props.role, {headers:auth(saved)})
    if (turn !== generation) return
    const index = history.items.findIndex(m => m.id === props.message && m.role_id === props.role)
    if (index < 0) throw Error()
    context.value = history.items.slice(Math.max(index - 1, 0), index + 2)
  } catch { if (turn === generation) error.value = '暂时无法读取这条引用。' }
}
watch(() => [props.role, props.message], load, {immediate:true})
</script>
<template>
  <ElDialog :model-value="true" :title="'原对话 · ' + name" width="min(34rem, 92vw)" @close="router.replace({name:'report'})">
    <p v-if="error" role="alert">{{ error }} <button @click="load">重试</button></p>
    <p v-else-if="!context.length" role="status">正在读取原对话…</p>
    <ol v-else class="source-messages"><li v-for="m in context" :key="m.id" :aria-current="m.id === message ? 'true' : undefined">
      <small>{{ m.sender === 'user' ? '我' : name }}{{ m.id === message ? ' · 复盘引用' : '' }}</small>{{ m.content }}
    </li></ol>
    <template #footer><button @click="router.replace({name:'report'})">返回复盘</button></template>
  </ElDialog>
</template>
