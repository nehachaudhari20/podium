const DATA_MODE = (import.meta.env.VITE_DATA_MODE || 'api').toLowerCase()
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export function isApiMode(): boolean {
  return DATA_MODE !== 'mock'
}

export function apiBaseUrl(): string {
  return API_BASE
}

export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(body || `Request failed (${status})`)
    this.status = status
    this.body = body
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(0, `Unable to reach Podium API at ${API_BASE}`)
  }

  if (!response.ok) {
    const body = await response.text()
    throw new ApiError(response.status, body || response.statusText)
  }

  return (await response.json()) as T
}
