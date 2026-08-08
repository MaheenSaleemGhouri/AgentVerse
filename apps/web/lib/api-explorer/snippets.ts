/**
 * Copy-pasteable code for the request currently in the form.
 *
 * Every snippet reads the key from the environment rather than embedding
 * one. A snippet with a real key in it is a snippet that ends up pasted
 * into a chat thread, a gist, or a commit — and the explorer is exactly
 * the surface where someone would copy without thinking about it.
 */

export function curlSnippet(baseUrl: string, path: string): string {
  return [
    `curl "${baseUrl}${path}" \\`,
    `  -H "Authorization: Bearer $AGENTVERSE_API_KEY"`,
  ].join("\n");
}

export function pythonSnippet(baseUrl: string, path: string): string {
  return [
    "import os",
    "",
    "import httpx",
    "",
    'response = httpx.get(',
    `    "${baseUrl}${path}",`,
    '    headers={"Authorization": f"Bearer {os.environ[\'AGENTVERSE_API_KEY\']}"},',
    ")",
    "response.raise_for_status()",
    "print(response.json())",
  ].join("\n");
}

export function typescriptSnippet(baseUrl: string, path: string): string {
  return [
    `const response = await fetch("${baseUrl}${path}", {`,
    "  headers: { Authorization: `Bearer ${process.env.AGENTVERSE_API_KEY}` },",
    "});",
    "if (!response.ok) throw new Error(await response.text());",
    "console.log(await response.json());",
  ].join("\n");
}
