<script setup lang="ts">
import { ref } from 'vue'
import { auth, request, type Credentials } from './api'
const props = defineProps<{ credentials: Credentials; version: number; disabled: boolean; refresh: () => Promise<void> }>()
const mode = ref<'end' | 'decisions' | ''>('')
const choice = ref(''), reason = ref(''), busy = ref(false), error = ref('')
let operation = '', previousBody = ''
const options = {continue:'继续提交', necessary_only:'仅提交必要资料', verify_first:'先核实再决定', decline:'退出招聘流程'}

async function confirm() {
  if (!mode.value || busy.value || props.disabled) return
  const body = JSON.stringify({expected_version: props.version, ...(mode.value === 'decisions' ? {choice:choice.value,reason:reason.value} : {})})
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
