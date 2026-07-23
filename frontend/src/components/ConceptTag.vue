<script setup>
defineProps({ term: { type: String, default: '' } })
</script>

<template>
  <span v-if="term" class="concept-tag"><span class="dot"></span>{{ term }}</span>
  <span v-else class="faint">—</span>
</template>
