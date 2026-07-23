<script setup>
defineProps({ error: { type: [Error, Object, null], default: null } })
defineEmits(['retry'])
</script>

<template>
  <div v-if="error" class="card offline-banner" style="padding:14px 16px;border-color:#f0cfc6;background:#fdf1ee;margin-bottom:16px;">
    <div class="row" style="gap:10px;">
      <span style="font-size:20px;">⚠️</span>
      <div class="col" style="gap:2px;">
        <strong style="color:var(--danger);">{{ $t('offline.title') }}</strong>
        <span class="muted" style="font-size:13px;">{{ $t('offline.body') }}</span>
      </div>
      <span class="spacer"></span>
      <button class="primary" @click="$emit('retry')">{{ $t('offline.retry') }}</button>
    </div>
  </div>
</template>
