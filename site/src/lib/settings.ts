export const SECRET_NAMES = ['UPSTAGE_API_KEY', 'CONTRACT_AGENT_ID', 'CONTRACT_CONFIG_ID', 'CRITERIA_AGENT_ID', 'CRITERIA_CONFIG_ID', 'REVIEW_AGENT_ID', 'REVIEW_CONFIG_ID'] as const;
export type Settings = Record<(typeof SECRET_NAMES)[number], string> & { FORCE_DEMO?: string };
export function settings(source: Record<string, unknown>): Settings {
  return {...Object.fromEntries(SECRET_NAMES.map(key => [key, typeof source[key] === 'string' ? source[key].trim() : ''])), FORCE_DEMO: source.FORCE_DEMO === '1' ? '1' : '0'} as Settings;
}
export function is_live_ready(config: Settings): boolean { return config.FORCE_DEMO !== '1' && SECRET_NAMES.every(key => Boolean(config[key])); }
