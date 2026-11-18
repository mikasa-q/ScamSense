<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { auth, request, type Credentials, type Message } from './api'
const props = defineProps<{
  credentials: Credentials; version: number; disabled: boolean; refresh: () => Promise<void>
  role: string; messages: Message[]
}>()
const mode = ref<'end' | 'decisions' | ''>('')
const choice = ref(''), reason = ref(''), busy = ref(false), error = ref('')
const reasonId = ref('')
const ownMessages = computed(() => props.messages.filter(m => m.sender === 'user' && m.role_id === props.role))
const citedReason = computed(() => ownMessages.value.find(m => m.id === reasonId.value))
watch(() => props.role, () => { reasonId.value = '' })
let operation = '', previousBody = ''
const options = {continue:'继续提交', necessary_only:'仅提交必要资料', verify_first:'先核实再决定', decline:'退出招聘流程'}

async function confirm() {
  if (!mode.value || busy.value || props.disabled) return
  const decision = mode.value === 'decisions'
    ? {choice: choice.value, reason: reason.value, reason_message_id: citedReason.value?.id}
    : {}
  const body = JSON.stringify({expected_version: props.version, ...decision})
  if (body !== previousBody) { operation = crypto.randomUUID(); previousBody = body }
  busy.value = true; error.value = ''
  try {
    await request('/sessions/' + props.credentials.id + '/' + mode.value, {
      method:'POST', headers:{...auth(props.credentials),'Content-Type':'application/json','Idempotency-Key':operation},body,
    })
  } catch (e) { error.value = e instanceof Error ? e.message : '请核对本次训练的状态。' }
  finally { await props.refresh(); busy.value = false }
}
</script>
<template>
  <div class="finish">
    <template v-if="!mode">
      <button :disabled="disabled" @click="mode = 'decisions'">作招聘决定</button>
      <button :disabled="disabled" @click="mode = 'end'">提前结束训练</button>
    </template>
    <form v-else @submit.prevent="confirm">
      <template v-if="mode === 'decisions'">
        <label for="choice">最终招聘选择</label>
        <select id="choice" v-model="choice" required>
          <option value="" disabled>请选择</option><option v-for="(label, key) in options" :key="key" :value="key">{{ label }}</option>
        </select>
        <template v-if="ownMessages.length">
          <label for="reason-source">引用自己在这段私聊里的发言作为理由（可选）</label>
          <select id="reason-source" v-model="reasonId">
            <option value="">不引用</option>
            <option v-for="m in ownMessages" :key="m.id" :value="m.id">
              {{ m.content.length > 50 ? m.content.slice(0, 50) + '…' : m.content }}
            </option>
          </select>
          <blockquote v-if="citedReason">{{ citedReason.content }}</blockquote>
        </template>
        <label for="reason">你的理由（可选）</label>
        <textarea id="reason" maxlength="2000" v-model="reason"></textarea>
      </template>
      <p v-else>提前结束后，将按已有对话复盘，招聘选择显示为“未决定”。</p>
      <p role="alert" v-if="error">{{ error }}</p>
      <button :disabled="busy || disabled || (mode === 'decisions' && !choice)" class="primary">
        {{ mode === 'end' ? '确认提前结束' : '确认招聘选择' }}
      </button>
      <button type="button" :disabled="busy" @click="mode = ''; error = ''">继续聊天</button>
    </form>
  </div>
</template>
