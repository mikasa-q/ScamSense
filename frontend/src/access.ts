import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Saved } from './api'

const key = 'scamsense.training.v1'
export const useAccess = defineStore('training-access', () => {
  const saved = ref<Saved | null>(null)
  function restore() {
    const value = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (value && (typeof value !== 'object' || !(typeof value.key === 'string' ||
        (typeof value.id === 'string' && typeof value.token === 'string')))) throw Error('无效的训练凭证')
    saved.value = value
  }
  function remember(value: Saved) {
    sessionStorage.setItem(key, JSON.stringify(value))
    saved.value = value
  }
  function clear() {
    sessionStorage.removeItem(key)
    saved.value = null
  }
  return { saved, restore, remember, clear }
})
