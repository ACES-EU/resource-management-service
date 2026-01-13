from typing import Any

from datetime import datetime

import requests
from kubernetes import client, config
from kubernetes.utils.quantity import parse_quantity as pq
from loguru import logger

from app.consts import ORCHESTRATION_API_URL

try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()
    except config.config_exception.ConfigException:
        logger.error("No Kubernetes config found — running without cluster access")
v1 = client.CoreV1Api()
custom = client.CustomObjectsApi()


def parse_quantity(quantity):
    return float(pq(quantity))


def diff_timestamps(t1: str, t2: str) -> float:
    dt1 = datetime.fromisoformat(t1.replace("Z", "+00:00"))
    dt2 = datetime.fromisoformat(t2.replace("Z", "+00:00"))
    return (dt2 - dt1).total_seconds()


def classify_pod(pod):
    """Classify a pod as rigid if it has limits; elastic otherwise."""
    for c in pod.spec.containers:
        if c.resources.limits:
            return "rigid"
    return "elastic"


def get_pods_in_k8s():
    try:
        response = requests.get(f"{ORCHESTRATION_API_URL}/k8s_pod")
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Status code {response.status_code}: {response.text}")
    except Exception:
        logger.exception("Failed to get node details.")


def get_parameters(limit=1):
    logger.debug("Reading latest parameter(s).")
    try:
        response = requests.get(
            f"{ORCHESTRATION_API_URL}/tuning_parameters/latest/{limit}"
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Status code {response.status_code}: {response.text}")
    except Exception:
        logger.exception("Failed to get parameters.")


def classify_pod_dict(pod):
    containers = pod.get("containers", [])
    for c in containers:
        if c.get("cpu_limit") or c.get("memory_limit"):
            return "rigid"
    return "elastic"


def get_pods_by_type():
    pods = get_pods_in_k8s()
    rigid: list[Any] = []
    elastic: list[Any] = []
    for p in pods:
        # skip finished pods
        if p.get("status") not in ("Succeeded", "Failed"):
            typ = classify_pod_dict(p)
            (rigid if typ == "rigid" else elastic).append(p)
    return rigid, elastic


def get_pod_usage():
    """Return dict {(namespace, name): {'cpu': millicores, 'mem': bytes}}"""
    usage = {}
    metrics = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
    for item in metrics["items"]:
        cpu = sum(parse_quantity(c["usage"]["cpu"]) for c in item["containers"])
        mem = sum(
            parse_quantity(c["usage"]["memory"]) / (1024**2)
            for c in item["containers"]
        )
        usage[(item["metadata"]["namespace"], item["metadata"]["name"])] = {
            "cpu": cpu,
            "memory": mem,
        }
    return usage


def compute_node_slack():
    rigid, _ = get_pods_by_type()
    usage = get_pod_usage()
    slack_per_node: dict[str, dict[Any, Any]] = {}

    for pod in rigid:
        node = pod.get("node_name")
        key = f"{pod.get('namespace')};{pod.get('name')}"
        used = usage.get(key, {"cpu": 0, "memory": 0})

        req_cpu = sum(
            parse_quantity(c.get("cpu_request") if c.get("cpu_request") else "0")
            for c in pod.get("containers", [])
        )
        req_mem = sum(
            parse_quantity(c.get("memory_request") if c.get("memory_request") else "0")
            / (1024**2)
            for c in pod.get("containers", [])
        )

        slack_cpu = max(req_cpu - used["cpu"], 0)
        slack_mem = max(req_mem - used["memory"], 0)

        try:
            slack_per_node[node][key] = {"cpu": slack_cpu, "memory": slack_mem}
        except KeyError:
            slack_per_node[node] = {key: {"cpu": slack_cpu, "memory": slack_mem}}

    return slack_per_node


def get_pod_requested_resources(pod):
    """Return total requested CPU (millicores) and memory (bytes) for a pod."""
    total_cpu = 0
    total_mem = 0

    for container in pod.spec.containers:
        requests = container.resources.limits or container.resources.requests or {}
        cpu_req = requests.get("cpu", "0")
        mem_req = requests.get("memory", "0")

        total_cpu += parse_quantity(cpu_req)
        total_mem += parse_quantity(mem_req) / (1024**2)

    return {"cpu": total_cpu, "memory": total_mem}
