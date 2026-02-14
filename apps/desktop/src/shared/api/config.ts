type EnvMap = Record<string, string | undefined>;

const env = ((import.meta as ImportMeta & { env?: EnvMap }).env ?? {}) as EnvMap;

const DEFAULT_PORT = env.VITE_API_PORT || "8055";
const LEGACY_BASE = env.VITE_API_BASE || `http://127.0.0.1:${DEFAULT_PORT}/api/v1`;

export const API_BASE = env.VITE_ASTRA_API_BASE_URL || LEGACY_BASE;
export const ASTRA_DATA_DIR = env.VITE_ASTRA_DATA_DIR;
export const ASTRA_BASE_DIR = env.VITE_ASTRA_BASE_DIR;
