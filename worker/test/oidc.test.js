import { test } from "node:test";
import assert from "node:assert/strict";
import { checkClaims, AUDIENCE, REPOSITORY } from "../src/oidc.js";

const valid = {
  iss: "https://token.actions.githubusercontent.com", aud: AUDIENCE, repository: REPOSITORY,
  ref: "refs/heads/main", exp: 2000,
};

test("accepts the trading repo on main before expiry", () => {
  assert.equal(checkClaims(valid, 1000), true);
});

test("rejects another repository, branch, audience, issuer or expired token", () => {
  assert.equal(checkClaims({ ...valid, repository: "otro/repo" }, 1000), false);
  assert.equal(checkClaims({ ...valid, ref: "refs/heads/dev" }, 1000), false);
  assert.equal(checkClaims({ ...valid, aud: "otro" }, 1000), false);
  assert.equal(checkClaims({ ...valid, iss: "https://evil.example" }, 1000), false);
  assert.equal(checkClaims(valid, 3000), false);
});
