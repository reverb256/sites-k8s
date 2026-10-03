#!/usr/bin/env python3
"""Static checks for the network policies of the k3s apps in this repo.

Renders each chart with helm, then checks. Encodes two live failures
(2026-09-26):
  - policy ports must match the POD-side (containerPort/targetPort) ports:
    a `port: 80` rule against a containerPort 8080 silently blocks the
    tunnel while looking correct;
  - every allow must be scoped: a bare podSelector:{} peer leaks to the
    other app's pods in the shared namespace.

Checks are PER NAMESPACE. Each chart is rendered into the namespace its
ArgoCD Application declares (helm/apps/<app>.yaml -> destination.namespace),
and each namespace must carry exactly ONE ns-wide default-deny for its own
containment. Before 2026-10-03 the script rendered every chart into `sites`
and demanded one global deny, so a second app living in its own namespace
(site-agency-pipeline) failed the gate for having correct isolation.
"""
import glob
import subprocess
import sys

import yaml

fails = []


def app_manifest_for(chart_path):
    """Return (app_name, namespace) for the Application that deploys chart."""
    for app_file in sorted(glob.glob("helm/apps/*.yaml")):
        docs = [d for d in yaml.safe_load_all(open(app_file)) if d]
        for d in docs:
            if d.get("kind") != "Application":
                continue
            src = (d.get("spec") or {}).get("source") or {}
            if src.get("path") == chart_path:
                ns = ((d.get("spec") or {}).get("destination") or {}).get("namespace")
                return d["metadata"]["name"], ns
    return None, None


per_ns = {}
for ch in sorted(glob.glob("helm/charts/*")):
    app, ns = app_manifest_for(ch)
    if not ns:
        fails.append(f"{ch}: no Application in helm/apps/*.yaml declares this chart path")
        continue
    r = subprocess.run(
        ["helm", "template", "check", ch, "--namespace", ns],
        capture_output=True, text=True, timeout=90,
    )
    if r.returncode != 0:
        fails.append(f"{ch}: helm template failed: {r.stderr.strip()[:200]}")
        continue
    per_ns.setdefault(ns, []).extend(d for d in yaml.safe_load_all(r.stdout) if d)

summary = []
for ns, docs in sorted(per_ns.items()):
    denies = 0
    ingress_ports = set()
    pod_ports = set()

    for d in docs:
        kind = d.get("kind")
        if kind == "NetworkPolicy":
            spec = d.get("spec", {})
            if spec.get("podSelector") == {} and set(spec.get("policyTypes") or []) == {"Ingress", "Egress"}:
                denies += 1
            for rule in spec.get("ingress") or []:
                for p in (rule.get("from") or []):
                    if "namespaceSelector" not in p and "ipBlock" not in p and p.get("podSelector") == {}:
                        fails.append(f"{ns}/{d['metadata']['name']}: bare podSelector:{{}} peer (ns-wide leak class)")
                for prt in rule.get("ports") or []:
                    if prt.get("protocol", "TCP") == "TCP":
                        ingress_ports.add(int(prt["port"]))
            for rule in spec.get("egress") or []:
                for p in (rule.get("to") or []):
                    if "namespaceSelector" not in p and "ipBlock" not in p and p.get("podSelector") == {}:
                        fails.append(f"{ns}/{d['metadata']['name']}: bare podSelector:{{}} peer (ns-wide leak class)")
        elif kind == "Deployment":
            for c in d["spec"]["template"]["spec"]["containers"]:
                for p in c.get("ports") or []:
                    pod_ports.add(int(p["containerPort"]))

    if denies != 1:
        fails.append(f"namespace {ns}: expected exactly ONE ns-wide default-deny, found {denies}")

    # Every ingress rule for these pods must name a pod-side port (the
    # 2026-09-26 regression: svc 80 -> pod 8080 but the policy said port: 80).
    bad_port = ingress_ports - pod_ports
    if bad_port:
        fails.append(
            f"namespace {ns}: ingress rules use non-pod-side ports: {sorted(bad_port)} "
            f"(targetPort-mismatch class; pod ports are {sorted(pod_ports)})"
        )
    if pod_ports - ingress_ports:
        fails.append(f"namespace {ns}: pod-side ports with no ingress allow: {sorted(pod_ports - ingress_ports)}")

    summary.append(f"{ns}: deny={denies} pod_ports={sorted(pod_ports)}")

if fails:
    print("netpol check FAILED:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("netpol check OK (" + "; ".join(summary) + ")")
