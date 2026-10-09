import { ref, watch } from 'vue';
import { DEFAULT_WATCHLIST } from '@/constants';

const STORAGE_KEY = 'vela-watchlist';

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return DEFAULT_WATCHLIST;
}

export const watchlist = ref<{ code: string; name: string }[]>(loadWatchlist());

watch(
  watchlist,
  (val) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
  },
  { deep: true }
);

export function addToWatchlist(code: string, name: string) {
  if (watchlist.value.some((s) => s.code === code)) return;
  watchlist.value.push({ code, name });
}

export function removeFromWatchlist(code: string) {
  const idx = watchlist.value.findIndex((s) => s.code === code);
  if (idx >= 0) watchlist.value.splice(idx, 1);
}

export function isInWatchlist(code: string): boolean {
  return watchlist.value.some((s) => s.code === code);
}
