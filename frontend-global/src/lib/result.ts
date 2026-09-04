// src/lib/result.ts — a query outcome the page can render honestly: the rows, or what failed.

export type Result<T> = { ok: true; value: T } | { ok: false; error: string }

export async function attempt<T>(p: Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, value: await p }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}
