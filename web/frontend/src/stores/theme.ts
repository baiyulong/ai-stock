import { ref } from 'vue';

const STORAGE_KEY = 'vela-theme';

export type Theme = 'dark' | 'light';

function loadTheme(): Theme {
  return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
}

export const theme = ref<Theme>(loadTheme());

export function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  localStorage.setItem(STORAGE_KEY, theme.value);
}

export function setTheme(t: Theme) {
  theme.value = t;
  localStorage.setItem(STORAGE_KEY, t);
}
