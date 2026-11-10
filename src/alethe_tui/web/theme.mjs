const key='alethe-monitor-theme';
export const themeId=value=>['current','aura','light'].includes(value)?value:'current';
export function loadTheme(storage){try{return themeId(storage.getItem(key))}catch{return 'current'}}
export function saveTheme(value,storage){try{storage.setItem(key,themeId(value))}catch{/* Preference remains usable without storage. */}}
