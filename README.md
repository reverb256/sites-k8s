# sites-k8s

GitOps (ArgoCD + Helm) deployment for **sites.reverb256.dev** — the publishing surface of the
[site-agency](https://github.com/reverb256/site-agency) pipeline (consent-first local-business
site upgrades).

- **Content source:** [reverb256/sites](https://github.com/reverb256/sites) — the pipeline pushes
  there; git-sync pulls it into the nginx pod every 60s (no rebuild, no redeploy).
- **Serving:** nginx + git-sync sidecar in namespace `sites` on the homelab k3s cluster.
- **Ingress path:** Cloudflare tunnel (`sites.reverb256.dev` → `sites-static` ClusterIP) → nginx.
- `/preview/<token>/` responses carry `X-Robots-Tag: noindex` (private, consent-gated previews).
- Responses carry `X-Served-By: sites-k8s` (serving-path marker).

Layout mirrors the other `*-k8s` repos (media-k8s, mining-k8s, trading-k8s):
root app-of-apps + child Application + local chart.

## content.lan (`content-site`)

Second site in this repo, added 2026-09-23: the **content.lan showcase + team
dashboard + approval API**, moved off the zephyr workstation (standing directive:
nothing is hosted on zephyr).

| | |
|---|---|
| Chart | `helm/charts/content-site` (release/app `content-site`, ns `sites`) |
| Content source | [reverb256/content-lan](https://github.com/reverb256/content-lan) |
| Storage | `content-site-data` PVC (longhorn — replicated on cluster nodes only; zephyr is not a longhorn node) |
| Edge | `*.lan` vhosts in `media-k8s/cluster/addons/media-reverse-proxy/` → `content-site.sites.svc.cluster.local` |
| Approval API | `content.lan:8791` (nginx-rp listener → container port 8791) |

Unlike `sites-static` (git-sync, read-only), this one serves a **seeded volume**:
the approval API rewrites each asset's sidecar `.md` in place, so the tree is
runtime state. The `seed` init container only populates an EMPTY volume; set
`seed.force=true` (or delete the PVC) to adopt content changes from git.
Deliberately no PDB: the RWO volume pins it to one pod, so blocking drains
would only deadlock upgrades.

Bootstrap (one-time): `kubectl -n argocd apply -f helm/sites-helm.yaml`
