<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import ChatComposer from './ChatComposer.vue'
import { auth, request, type Credentials, type Message, type Saved, type Session } from './api'

const storageKey = 'scamsense.training.v1'
const saved = ref<Saved | null>(null)
const session = ref<Session | null>(null)
const selected = ref('')
const messages = ref<Message[]>([])
const error = ref('')
const historyError = ref('')
const busy = ref(false)
const consent = ref(false)
const talking = ref(false)

function remember(value: Saved) {
  sessionStorage.setItem(storageKey, JSON.stringify(value))
  saved.value = value
}

async function enter(newSession = false) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    if (newSession || !saved.value) remember({ key: crypto.randomUUID() })
    const current = saved.value!
    if ('key' in current) {
      const created = await request<{ session: Session; session_token: string }>('/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': current.key },
        body: JSON.stringify({ scenario_id: 'internship_v1', privacy_notice_version: 'local-demo-v1' }),
      })
      remember({ id: created.session.id, token: created.session_token })
      session.value = created.session
    } else {
      session.value = await request<Session>('/sessions/' + current.id, { headers: auth(current) })
    }
    selected.value = session.value.roles[0].id
  } catch (e) {
    error.value = e instanceof Error ? e.message : '未能进入训练，请重试。'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  try {
    saved.value = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
    if (saved.value && 'token' in saved.value) void enter()
    else if (saved.value) error.value = '上次创建结果待确认，可用原请求重试。'
  } catch {
    error.value = '浏览器无法读取本次训练的凭证。'
  }
})

async function loadHistory(role: string) {
  const c = saved.value as Credentials
  messages.value = []
  historyError.value = ''
  try {
    const history = await request<{items: Message[]}>('/sessions/' + c.id + '/messages?role_id=' + role, { headers: auth(c) })
    if (selected.value === role) messages.value = history.items
  } catch {
    if (selected.value === role) historyError.value = '暂时无法读取这段私聊。'
  }
}
watch(selected, loadHistory)

async function refresh() {
  const c = saved.value as Credentials
  try {
    session.value = await request<Session>('/sessions/' + c.id, { headers: auth(c) })
    await loadHistory(selected.value)
  } catch { historyError.value = '暂时无法核对训练状态，请刷新页面。' }
}
</script>

<template>
  <header><strong>拆招</strong><span>ScamSense</span></header>
  <main v-if="!session" class="entry">
    <p class="label">求职反诈模拟训练</p>
    <h1>那个看起来很正规的<br>实习机会</h1>
    <p>你正在寻找 Python 后端实习。两位招聘联系人和一位大学朋友发来了消息。</p>
    <label><input type="checkbox" v-model="consent"> 我会使用虚构资料。本机演示保存训练对话，会话可访问 24 小时。</label>
    <p role="alert" v-if="error">{{ error }}</p>
    <button class="primary" :disabled="busy || (!consent && !saved)" @click="enter()">
      {{ busy ? '正在进入…' : saved ? '重试本次训练' : '开始训练' }}
    </button>
    <button v-if="saved && error" :disabled="busy || !consent" @click="enter(true)">另开训练</button>
  </main>
  <main v-else class="workspace">
    <aside><p class="label">联系人</p>
      <button v-for="r in session.roles" :key="r.id" :disabled="talking" :aria-pressed="selected === r.id" @click="selected = r.id">
        <b>{{ r.name }}</b><small>{{ r.public_title }}</small>
      </button>
    </aside>
    <section><p class="label">私聊 · {{ session.stage }}</p>
      <h1>{{ session.roles.find(r => r.id === selected)?.name }}</h1>
      <p v-for="m in messages" :key="m.id" class="bubble" :class="{ mine: m.sender === 'user' }"><small v-if="m.sender === 'user'">我</small>{{ m.content }}</p>
      <p role="alert" v-if="historyError">{{ historyError }} <button @click="loadHistory(selected)">重试</button></p>
      <ChatComposer v-if="saved && 'token' in saved && selected" :key="selected" :credentials="saved"
        :role="selected" :version="session.state_version" :refresh="refresh" @busy="talking = $event" />
    </section>
  </main>
</template>
