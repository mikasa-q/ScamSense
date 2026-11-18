<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { auth, request, type Credentials, type Role } from './api'
const props = defineProps<{ credentials: Credentials; status: string; roles: Role[] }>()
const emit = defineEmits<{ restart: [] }>()
interface Evidence { id?: string; operation?: string; role_id?: string; content: string; source?: {id:string; content:string} }
interface Report {
  choice_label: string; ended_early: boolean; reason: string; total_score: number | null
  dimensions: {name: string; weight: number; score: number | null; explanation: string; evidence: Evidence[]}[]
  disclosures: {message_id:string; role_id:string; excerpt:string; visibility:string}[]
}
const report = ref<Report>(), error = ref(''), loading = ref(false)
const roleName = (id?: string) => props.roles.find(r => r.id === id)?.name
async function load() {
  loading.value = true; error.value = ''
  const generate = props.status === 'evaluating'
  try {
    report.value = await request<Report>('/sessions/' + props.credentials.id + '/report' + (generate ? '/retry' : ''), {
      method:generate ? 'POST' : 'GET', headers:{...auth(props.credentials), ...(generate ? {'Idempotency-Key':crypto.randomUUID()} : {})},
    })
  } catch (e) { error.value = e instanceof Error ? e.message : '复盘读取失败。' }
  finally { loading.value = false }
}
onMounted(() => { if (props.status === 'completed') void load() })
</script>
<template>
  <main class="report">
    <p class="label">求职训练</p><h1>训练复盘</h1>
    <template v-if="report">
      <h2>招聘选择 · {{ report.choice_label }}</h2>
      <p>{{ report.ended_early ? '你选择了提前结束训练。' : report.reason || '本次没有填写决定理由。' }}</p>
      <p>总分 · {{ report.total_score ?? '无法评估' }}</p>
      <section v-for="d in report.dimensions" :key="d.name">
        <h3>{{ d.name }} · {{ d.weight }}% · {{ d.score ?? '无法评估' }}</h3>
        <p>{{ d.explanation }}</p>
        <blockquote v-for="e in d.evidence" :key="e.id || e.operation">
          <small>{{ roleName(e.role_id) ? '与' + roleName(e.role_id) + '私聊中的原话' : '确认选择时的理由' }}</small>{{ e.content }}
          <p v-if="e.source"><small>所据的角色原话</small>{{ e.source.content }}</p>
        </blockquote>
      </section>
      <section v-if="report.disclosures.length"><h3>对话中出现的线索</h3>
        <blockquote v-for="d in report.disclosures" :key="d.message_id + d.excerpt"><small>{{ roleName(d.role_id) }} · {{ d.visibility }}</small>{{ d.excerpt }}</blockquote>
      </section>
      <button @click="emit('restart')">另开训练</button>
    </template>
    <template v-else><p role="status">{{ error || (loading ? '正在读取复盘…' : '对话已结束，可用已保存的证据生成复盘。') }}</p>
      <button v-if="!loading" @click="load">重试复盘</button>
    </template>
  </main>
</template>
