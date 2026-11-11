// Verifica el token OIDC que GitHub Actions emite al job: firma con las claves publicas de GitHub y quien lo pide.
const GITHUB_ISSUER = "https://token.actions.githubusercontent.com";
const JWKS_URL = `${GITHUB_ISSUER}/.well-known/jwks`;
export const AUDIENCE = "trading-bot-worker";
export const REPOSITORY = "mcelimenia-create/trading";
export const BRANCH_REF = "refs/heads/main";

function base64UrlToBytes(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(text.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

function decodeJson(part) {
  return JSON.parse(new TextDecoder().decode(base64UrlToBytes(part)));
}

// Comprobaciones de quien pide: emisor, audiencia, repositorio, rama y ventana de validez.
export function checkClaims(claims, now = Date.now() / 1000) {
  return claims.iss === GITHUB_ISSUER
    && claims.aud === AUDIENCE
    && claims.repository === REPOSITORY
    && claims.ref === BRANCH_REF
    && typeof claims.exp === "number" && claims.exp > now
    && (claims.nbf === undefined || claims.nbf <= now);
}

async function signingKey(kid) {
  const { keys } = await fetch(JWKS_URL).then((r) => r.json());
  const jwk = keys.find((k) => k.kid === kid);
  if (!jwk) throw new Error("clave desconocida");
  return crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
}

export async function verifyActionsToken(token) {
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const header = decodeJson(parts[0]);
  const key = await signingKey(header.kid);
  const data = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const valid = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, base64UrlToBytes(parts[2]), data);
  const claims = decodeJson(parts[1]);
  return valid && checkClaims(claims);
}
