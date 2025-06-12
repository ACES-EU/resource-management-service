import json

import requests
from kubernetes import client, config, watch
from loguru import logger

from app.schemas import NodeDetail
from app.swarm.SwarmScheduler import SwarmScheduler

try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()
    except config.config_exception.ConfigException:
        logger.error("No Kubernetes config found — running without cluster access")


def find_wam():
    v1 = client.CoreV1Api()
    namespace = "default"
    label_selector = "app.kubernetes.io/name=wam"
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)

    wam = None
    if pods.items:
        for pod in pods.items:
            wam = pod
            logger.debug(f"Pod Name: {wam.metadata.name}")
            if wam is not None:
                break
    else:
        logger.error(
            f"No pods found with label {label_selector} in namespace {namespace}"
        )

    return wam


def send_scheduling_request(pod, node_name, id=1):
    """Send the scheduling request to the external service."""
    wam = find_wam()
    if wam is None:
        return

    # Add the URL of the wam
    url = f"http://{wam.status.pod_ip}:3030/rpc"
    logger.debug(f"Found 'wam': {url}")
    payload = {
        "method": "action.Bind",
        "params": [
            {
                "pod": {
                    "namespace": pod.metadata.namespace,
                    "name": pod.metadata.name,
                },
                "node": {"name": node_name},
            }
        ],
        "id": str(id),
    }

    logger.debug(f"Payload:\n{json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info(
                f"Successfully scheduled Pod {pod.metadata.name} on {node_name}"
            )
        else:
            logger.error(
                f"Failed to schedule Pod {pod.metadata.name}: "
                f"{response.status_code} - {response.text}"
            )
    except Exception:
        logger.exception("Error sending scheduling request.")


def get_node_details() -> dict[str, NodeDetail]:
    # TODO get node details from Orchestrator API
    metrics_client = client.CustomObjectsApi()
    v1 = client.CoreV1Api()

    node_metrics = metrics_client.list_cluster_custom_object(
        group="metrics.k8s.io", version="v1beta1", plural="nodes"
    )
    nodes = v1.list_node().items

    node_details = {}
    for node in node_metrics["items"]:
        node_details[node["metadata"]["name"]] = {"usage": node["usage"]}
    for node in nodes:
        node_details[node.metadata.name]["capacity"] = node.status.capacity
        node_details[node.metadata.name]["allocatable"] = node.status.allocatable

    return {
        node: NodeDetail.model_validate_json(json.dumps(node_details[node]))
        for node in node_details
    }


def start_scheduler():
    v1 = client.CoreV1Api()
    w = watch.Watch()

    swarm_model = SwarmScheduler()

    logger.info("Starting custom scheduler...")
    for event in w.stream(v1.list_pod_for_all_namespaces):
        logger.debug(
            "Found Pod. Checking if it needs to be scheduled by SI-based scheduler..."
        )
        pod = event["object"]
        if (
            pod.spec.scheduler_name == "resource-management-service"
            and not pod.spec.node_name
        ):
            logger.info(f"Found Pod to schedule: {pod.metadata.name}")

            # Custom scheduling logic
            nodes = get_node_details()
            if len(nodes) > 0:
                swarm_model.set_workers(nodes)
                selected_node = swarm_model.select_node(pod)
                send_scheduling_request(pod, selected_node)
            else:
                logger.info("No available nodes to schedule the Pod.")


if __name__ == "__main__":
    start_scheduler()
