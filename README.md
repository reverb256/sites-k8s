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

Bootstrap (one-time): `kubectl -n argocd apply -f helm/sites-helm.yaml`
