#!/usr/bin/env python3
"""Static checks for the sites namespace network policies.

Renders each chart with helm, then checks. Encodes two live failures
(2026-09-26):
  - policy ports must match the POD-side (containerPort/targetPort) ports:
    a `port: 80` rule against a containerPort 8080 silently blocks the
    tunnel while looking correct;
  - every allow must be scoped: a bare podSelector:{} peer leaks to the
    other app's pods in the shared namespace.
"""
import glob
import subprocess
import sys

import yaml

fails = []
docs_all = []

for ch in sorted(glob.glob("helm/charts/*")):
    r = subprocess.run(
        ["helm", "template", "check", ch, "--namespace", "sites"],
        capture_output=True, text=True, timeout=90,
    )
    if r.returncode != 0:
        fails.append(f"{ch}: helm template failed: {r.stderr.strip()[:200]}")
        continue
    docs_all += [d for d in yaml.safe_load_all(r.stdout) if d]

denies = 0
ingress_ports = set()
pod_ports = set()

for d in docs_all:
    kind = d.get("kind")
    if kind == "NetworkPolicy":
        spec = d.get("spec", {})
        if spec.get("podSelector") == {} and set(spec.get("policyTypes") or []) == {"Ingress", "Egress"}:
            denies += 1
        for rule in spec.get("ingress") or []:
            for p in (rule.get("from") or []):
                if "namespaceSelector" not in p and "ipBlock" not in p and p.get("podSelector") == {}:
                    fails.append(f"{d['metadata']['name']}: bare podSelector:{{}} peer (ns-wide leak class)")
            for prt in rule.get("ports") or []:
                if prt.get("protocol", "TCP") == "TCP":
                    ingress_ports.add(int(prt["port"]))
        for rule in spec.get("egress") or []:
            for p in (rule.get("to") or []):
                if "namespaceSelector" not in p and "ipBlock" not in p and p.get("podSelector") == {}:
                    fails.append(f"{d['metadata']['name']}: bare podSelector:{{}} peer (ns-wide leak class)")
    elif kind == "Deployment":
        for c in d["spec"]["template"]["spec"]["containers"]:
            for p in c.get("ports") or []:
                pod_ports.add(int(p["containerPort"]))

if denies != 1:
    fails.append(f"expected exactly ONE ns-wide default-deny across the charts, found {denies}")

# Every ingress rule for these pods must name a pod-side port (the 2026-09-26
# regression: svc 80 -> pod 8080 but the policy said port: 80).
bad_port = ingress_ports - pod_ports
if bad_port:
    fails.append(f"ingress rules use non-pod-side ports: {sorted(bad_port)} (targetPort-mismatch class; pod ports are {sorted(pod_ports)})")
if pod_ports - ingress_ports:
    fails.append(f"pod-side ports with no ingress allow: {sorted(pod_ports - ingress_ports)}")

if fails:
    print("netpol check FAILED:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print(f"netpol check OK (deny={denies}, pod ports {sorted(pod_ports)} all covered)")
