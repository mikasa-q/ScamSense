<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { useAccess } from './access'
import ChatComposer from './ChatComposer.vue'
import FinishPanel from './FinishPanel.vue'
import ReportView from './ReportView.vue'
import { auth, request, type Credentials, type Message, type Session } from './api'

const access = useAccess()
const { saved } = storeToRefs(access)
const route = useRoute(), router = useRouter()
const session = ref<Session | null>(null)
const selected = ref('')
const messages = ref<Message[]>([])
const quote = ref<Message>()
const error = ref('')
const historyError = ref('')
const busy = ref(false)
const consent = ref(false)
const talking = ref(false)
const modelAvailable = ref(false), shareWithModel = ref(false)
const pauseError = ref('')
let pauseRequest: { command: string; version: number; key: string } | undefined

const unavailable = computed(() => route.name !== 'home' && (!saved.value || !('token' in saved.value)))
const finished = computed(() => session.value?.status === 'evaluating' || session.value?.status === 'completed')
function showCurrentPage() {
  if (!session.value || route.name === 'evidence') return
  const name = finished.value ? 'report' : 'training'
  if (route.name !== name) void router.replace({ name })
}

async function enter(newSession = false) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    if (newSession || !saved.value) access.remember({ key: crypto.randomUUID(), notice: shareWithModel.value && modelAvailable.value ? 'model-demo-v1' : 'local-demo-v1' })
    const current = saved.value!
    if ('key' in current) {
      const created = await request<{ session: Session; session_token: string }>('/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': current.key },
        body: JSON.stringify({ scenario_id: 'internship_v1', privacy_notice_version: current.notice || 'local-demo-v1' }),
      })
      access.remember({ id: created.session.id, token: created.session_token })
      session.value = created.session
    } else {
      session.value = await request<Session>('/sessions/' + current.id, { headers: auth(current) })
    }
    selected.value = session.value.roles[0].id
    showCurrentPage()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '未能进入训练，请重试。'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  void request<{model_available:boolean}>('/training-options').then(r => { modelAvailable.value = r.model_available }).catch(() => {})
  try {
    access.restore()
    if (saved.value && 'token' in saved.value) void enter()
    else if (saved.value) error.value = '上次创建结果待确认，可用原请求重试。'
  } catch {
    error.value = '浏览器无法读取本次训练的凭证。'
  }
})

async function loadHistory(role: string) {
  if (!role || session.value?.status !== 'active' || !saved.value || !('token' in saved.value)) return
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
watch(selected, role => { quote.value = undefined; void loadHistory(role) })

async function refresh() {
  const c = saved.value as Credentials
  try {
    session.value = await request<Session>('/sessions/' + c.id, { headers: auth(c) })
    showCurrentPage()
    if (session.value.status === 'active') await loadHistory(selected.value)
  } catch { historyError.value = '暂时无法核对训练状态，请刷新页面。' }
}

async function togglePause() {
  const current = session.value, credentials = saved.value
  if (!current || !credentials || !('token' in credentials) || busy.value || talking.value) return
  const command = current.status === 'paused' ? 'resume' : 'pause'
  if (pauseRequest?.command !== command || pauseRequest.version !== current.state_version) {
    pauseRequest = { command, version: current.state_version, key: crypto.randomUUID() }
  }
  busy.value = true
  pauseError.value = ''
  try {
    const result = await request<{session: Session}>('/sessions/' + credentials.id + '/' + command, {
      method: 'POST', headers: { ...auth(credentials), 'Content-Type': 'application/json', 'Idempotency-Key': pauseRequest.key },
      body: JSON.stringify({expected_version: pauseRequest.version}),
    })
    session.value = result.session
    pauseRequest = undefined
  } catch (e) {
    pauseError.value = e instanceof Error ? e.message : '暂时无法核对暂停状态。'
  } finally {
    await refresh()
    if (session.value?.status !== current.status) pauseError.value = ''
    busy.value = false
  }
}

function restart() {
  access.clear()
  pauseRequest = undefined
  pauseError.value = ''
  historyError.value = ''
  session.value = null; selected.value = ''; consent.value = false; shareWithModel.value = false; error.value = ''
  void router.replace({name:'home'})
}
watch(() => route.name, showCurrentPage)
</script>

<template>
  <header><strong>拆招</strong><span>ScamSense</span></header>
  <main v-if="unavailable" class="entry"><h1>无法恢复这次训练</h1><p>此标签页没有访问原对话的训练凭证。</p>
    <RouterLink to="/">返回训练入口</RouterLink></main>
  <main v-else-if="route.name === 'evidence' && session && !finished" class="entry">
    <p>该引用不在当前训练的复盘中。</p><RouterLink to="/training">返回当前训练</RouterLink></main>
  <main v-else-if="!session" class="entry">
    <p class="label">求职反诈模拟训练</p>
    <h1>那个看起来很正规的<br>实习机会</h1>
    <p>你正在寻找 Python 后端实习。两位招聘联系人和一位大学朋友发来了消息。</p>
    <label><input type="checkbox" v-model="consent"> 我会使用虚构资料。本机演示保存训练对话，会话可访问 24 小时。</label>
    <label v-if="modelAvailable"><input type="checkbox" v-model="shareWithModel" :disabled="!!saved && !error"> 允许本次训练将当前问题和该角色最近的私聊发送给已配置的模型服务组织回复。</label>
    <p role="alert" v-if="error">{{ error }}</p>
    <button class="primary" :disabled="busy || (!consent && !saved)" @click="enter()">
      {{ busy ? '正在进入…' : saved ? '重试本次训练' : '开始训练' }}
    </button>
    <button v-if="saved && error" :disabled="busy || !consent" @click="enter(true)">另开训练</button>
  </main>
  <main v-else-if="session.status === 'paused'" class="entry">
    <h1>训练已暂停</h1>
    <p>当前阶段 {{ session.stage }}。恢复后可以继续原来的私聊。</p>
    <p v-if="pauseError || historyError" role="alert">{{ pauseError || historyError }}</p>
    <button class="primary" :disabled="busy" @click="togglePause">恢复训练</button>
  </main>
  <ReportView v-else-if="finished && saved && 'token' in saved" :credentials="saved"
    :status="session.status" :roles="session.roles" @restart="restart" />
  <main v-else class="workspace">
    <aside><p class="label">联系人</p>
      <button v-for="r in session.roles" :key="r.id" :disabled="busy || talking" :aria-pressed="selected === r.id" @click="selected = r.id">
        <b>{{ r.name }}</b><small>{{ r.public_title }}</small>
      </button>
    </aside>
    <section><p class="label">私聊 · {{ session.stage }}</p>
      <h1>{{ session.roles.find(r => r.id === selected)?.name }}</h1>
      <div v-for="m in messages" :key="m.id" class="bubble" :class="{ mine: m.sender === 'user' }"><small v-if="m.sender === 'user'">我</small>{{ m.content }}
        <small v-if="m.reply_mode === 'fallback'">模型回复不可用，本轮使用剧情预设。</small>
        <small v-else-if="m.reply_mode === 'model'">模型依据本轮获准材料组织回复</small>
        <button v-if="m.sender === 'assistant'" type="button" class="cite" :disabled="talking" @click="quote = m">引用</button>
      </div>
      <p role="alert" v-if="historyError">{{ historyError }} <button @click="loadHistory(selected)">重试</button></p>
      <ChatComposer v-if="saved && 'token' in saved && selected" :key="selected" :disabled="busy" :credentials="saved"
        :role="selected" :version="session.state_version" :quote="quote" :refresh="refresh"
        @busy="talking = $event" @clear-quote="quote = undefined" />
      <FinishPanel v-if="saved && 'token' in saved" :credentials="saved" :version="session.state_version"
        :role="selected" :messages="messages" :disabled="talking || busy" :refresh="refresh" />
      <p v-if="pauseError" role="alert">{{ pauseError }}</p>
      <button :disabled="talking || busy" @click="togglePause">暂停训练</button>
    </section>
  </main>
</template>
