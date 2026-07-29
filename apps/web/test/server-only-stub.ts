/**
 * Stands in for the `server-only` package under vitest.
 *
 * `server-only` throws on import from a client module — that guard is
 * what stops server code leaking into the browser bundle, and it should
 * stay. But a jsdom test importing a module that *transitively* touches
 * it (a client component importing a query module that imports the API
 * client) trips the guard even though nothing server-side is executed.
 *
 * Aliasing it to this empty module keeps the production guard intact
 * while letting tests exercise the real modules instead of stubbing out
 * the logic they mean to cover. Next's own build is unaffected — this
 * alias exists only in vitest.config.ts.
 */

export {};
