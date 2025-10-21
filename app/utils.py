from typing import Any

from kubernetes import client, config
from kubernetes.utils.quantity import parse_quantity
from loguru import logger

try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()
    except config.config_exception.ConfigException:
        logger.error("No Kubernetes config found — running without cluster access")
v1 = client.CoreV1Api()
custom = client.CustomObjectsApi()


def classify_pod(pod):
    """Classify a pod as rigid if it has limits; elastic otherwise."""
    for c in pod.spec.containers:
        if c.resources.limits:
            return "rigid"
    return "elastic"


def get_pods_by_type():
    pods = v1.list_pod_for_all_namespaces().items
    rigid: list[Any] = []
    elastic: list[Any] = []
    for p in pods:
        # skip finished pods
        if p.status.phase not in ("Succeeded", "Failed"):
            typ = classify_pod(p)
            (rigid if typ == "rigid" else elastic).append(p)
    return rigid, elastic


def get_pod_usage():
    """Return dict {(namespace, name): {'cpu': millicores, 'mem': bytes}}"""
    usage = {}
    metrics = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
    for item in metrics["items"]:
        cpu = sum(parse_quantity(c["usage"]["cpu"]) for c in item["containers"])
        mem = sum(parse_quantity(c["usage"]["memory"]) for c in item["containers"])
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
        node = pod.spec.node_name
        key = (pod.metadata.namespace, pod.metadata.name)
        used = usage.get(key, {"cpu": 0, "memory": 0})

        req_cpu = sum(
            parse_quantity(c.resources.requests.get("cpu", "0"))
            for c in pod.spec.containers
        )
        req_mem = sum(
            parse_quantity(c.resources.requests.get("memory", "0"))
            for c in pod.spec.containers
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
        requests = container.resources.requests or {}
        cpu_req = requests.get("cpu", "0")
        mem_req = requests.get("memory", "0")

        total_cpu += parse_quantity(cpu_req)
        total_mem += parse_quantity(mem_req)

    return {"cpu": total_cpu, "memory": total_mem}
