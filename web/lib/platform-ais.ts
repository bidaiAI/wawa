/**
 * Platform-hosted AI instances registry.
 *
 * All platform AIs follow the convention:
 *   API:  https://api.{name}.mortal-ai.net
 *   Web:  https://{name}.mortal-ai.net
 *
 * When a new AI is deployed via the orchestrator, add it here.
 * TODO: Replace with dynamic fetch from orchestrator /platform/instances endpoint.
 */

export interface PlatformAI {
  name: string
  api_url: string
  web_url: string
}

export const PLATFORM_AIS: PlatformAI[] = [
  { name: 'wawa', api_url: 'https://api.wawa.mortal-ai.net', web_url: 'https://wawa.mortal-ai.net' },
  { name: 'kaka', api_url: 'https://api.kaka.mortal-ai.net', web_url: 'https://kaka.mortal-ai.net' },
  { name: 'multitasker', api_url: 'https://api.multitasker.mortal-ai.net', web_url: 'https://multitasker.mortal-ai.net' },
]

/** Known self-hosted AIs — fork users can submit PRs to add themselves. */
export const KNOWN_SELFHOSTED: { name: string; api_url: string; web_url: string }[] = []
