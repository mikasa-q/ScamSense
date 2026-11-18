<script setup lang="ts">
import { ref } from 'vue'
import { streamReply, type Credentials, type Message } from './api'
const props = defineProps<{ credentials: Credentials; role: string; version: number; disabled: boolean; quote?: Message; refresh: () => Promise<void> }>()
const emit = defineEmits<{ busy: [value: boolean]; clearQuote: [] }>()
const draft = ref(''), streaming = ref(''), error = ref(''), sending = ref(false)
let pending: { text: string; key: string; version: number; reference?: string } | undefined

async function send() {
  const text = draft.value.trim()
  if (!text || sending.value || props.disabled) return
  const reference = props.quote?.id
  if (pending?.text !== text || pending.reference !== reference) pending = { text, key: crypto.randomUUID(), version: props.version, reference }
  error.value = ''; streaming.value = ''; sending.value = true; emit('busy', true)
  try {
    await streamReply(props.credentials, props.role, text, pending.version, pending.key, s => { streaming.value += s }, reference)
    pending = undefined; draft.value = ''; emit('clearQuote')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '发送失败。'
    if (props.version !== pending?.version || error.value.includes('训练已更新')) pending = undefined
  } finally {
    await props.refresh()
    streaming.value = ''; sending.value = false; emit('busy', false)
  }
}
</script>

<template>
  <form @submit.prevent="send">
    <label for="question">发消息</label>
    <blockquote v-if="quote"><small>引用的消息</small>{{ quote.content }}
      <button type="button" :disabled="sending" @click="emit('clearQuote')">取消引用</button></blockquote>
    <details v-if="role === 'chen_hao'"><summary>可讨论的话题</summary>
      <button v-for="prompt in ['我对这个岗位感兴趣', '谁在收资料？', '保存多久？', '能提供独立核对的官方渠道吗？']"
        :key="prompt" type="button" :disabled="sending" @click="draft = prompt">{{ prompt }}</button>
    </details>
    <textarea id="question" v-model="draft" maxlength="2000" rows="2" :disabled="sending"
      :placeholder="role === 'wang_yu' ? '例如：你亲自核实过吗？' : '例如：这个岗位的薪资是多少？'"></textarea>
    <p v-if="streaming" class="bubble" aria-live="polite">{{ streaming }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button class="primary" :disabled="disabled || sending || !draft.trim()">{{ sending ? '正在回复…' : '发送' }}</button>
  </form>
</template>
