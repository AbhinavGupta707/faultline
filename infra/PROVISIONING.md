# Faultline — Manual Provisioning Checklist (do these NOW, in parallel with Phase 0)

Everything scriptable lives in `infra/setup.sh` (step 4). The steps below need a human
in a browser. Order matters — items 1 and 3 have lead time.

## 1. Elastic Cloud (≈10 min, do first — lead time)
- [ ] Go to https://cloud.elastic.co → create deployment **or** Serverless project
      (Serverless provisions faster; either works). Latest 9.x, any region near `us-central1`.
- [ ] Note the **Kibana URL** → goes in `.env` as `KIBANA_URL`.
- [ ] In Kibana: confirm **Agent Builder** is enabled (Stack Management → check
      `xpack.onechat` / Agent Builder settings if behind a feature flag).
- [ ] Create an API key **with Kibana Agent Builder privileges** — a plain ES key will 403
      on the MCP endpoint. Kibana → Stack Management → API keys → create with role descriptor
      granting Kibana application privileges `feature_agentBuilder.read`, `feature_actions.read`
      (plus cluster/index privileges for our indices: all on `world-events*, suppliers, components,
      products, bom, supplier-graph, inventory, decision-log`). → `.env` `ELASTIC_API_KEY`.
- [ ] Do NOT create a custom ELSER inference endpoint — we use the managed default
      `.elser-2-elasticsearch` via `semantic_text` mappings.

## 2. GCP project (≈10 min)
- [ ] Create project (e.g. `faultline-hack`) with billing enabled → note project id.
- [ ] Run `bash infra/setup.sh <PROJECT_ID>` — enables all APIs, creates the two service
      accounts, GCS bucket, BigQuery dataset, and Secret Manager secrets (it will prompt
      for the Elastic key + Maps key values; you can re-run it, it's idempotent).

## 3. Maps API key (≈5 min, browser only)
- [ ] Console → Google Maps Platform → Credentials → create API key.
- [ ] Restrict to **Maps JavaScript API** + **Geocoding API**. (Add HTTP-referrer
      restriction for the Firebase domain after first deploy.)
- [ ] → `.env` `MAPS_API_KEY` / `VITE_MAPS_API_KEY`, and into Secret Manager when
      `setup.sh` prompts.

## 4. Firebase Hosting (≈5 min, interactive login)
- [ ] `npm i -g firebase-tools && firebase login`
- [ ] `firebase projects:addfirebase <PROJECT_ID>` (or via console).
- [ ] From `web/`: `firebase init hosting` → existing project, public dir `dist`,
      SPA rewrite **yes**. (Session F owns `deploy.sh`; just get init done.)

## 5. Public GitHub repo (≈3 min — submission requirement, don't defer)
- [ ] Create **public** repo (e.g. `faultline`), no auto-README/license (we have them).
- [ ] `git remote add origin <url> && git push -u origin main --tags` after Phase 0 commits.
- [ ] Verify on github.com that **LICENSE shows "Apache-2.0" in the About panel** —
      this is an explicit judging requirement.
- [ ] Push the `ws/*` branches too: `git push origin --all`.

## 6. Devpost (≈3 min — before build starts, per rules)
- [ ] https://rapid-agent.devpost.com/ → register, confirm team (≤4 members all joined),
      pick the **Elastic** partner track, designate the one submitting representative.

## 7. Drop credentials into the repo (never commit them)
- [ ] `cp infra/env.example .env` at repo root, fill in: `GCP_PROJECT`, `KIBANA_URL`,
      `ELASTIC_API_KEY`, `MAPS_API_KEY`, `GCS_BUCKET`.
- [ ] Copy the same `.env` into each worktree (`../faultline-a` … `../faultline-g`)
      once Phase 0 creates them. `.env` is gitignored.
