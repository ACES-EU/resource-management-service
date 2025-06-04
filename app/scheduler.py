import json
from os import environ

import requests
from kubernetes import client, config, watch
from loguru import logger

from app.schemas import NodeDetail
from app.swarm.SwarmScheduler import SwarmScheduler

# Load kubeconfig
if "KUBERNETES_SERVICE_HOST" in environ:
    config.load_incluster_config()
else:
    config.load_kube_config()


def find_owner_of_pod(pod):
    apps_v1 = client.AppsV1Api()
    reader = {
        "ReplicaSet": apps_v1.read_namespaced_replica_set,
        "StatefulSet": apps_v1.read_namespaced_stateful_set,
        "DaemonSet": apps_v1.read_namespaced_daemon_set,
    }

    actual_owner = None
    if pod.metadata.owner_references:
        for owner in pod.metadata.owner_references:
            if owner.controller:  # The actual managing controller
                actual_owner = owner
                logger.debug(f"{pod.metadata.name} owner: {actual_owner.name}")
                break  # Found the primary owner, exit loop
    if actual_owner:
        k8s_set = reader[actual_owner.kind](
            name=actual_owner.name, namespace=pod.metadata.namespace
        )
        if k8s_set.metadata.owner_references:
            for owner in k8s_set.metadata.owner_references:
                if owner.controller:
                    return owner
    return None


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
    # FIXME fix the integration with WAM
    wam = find_wam()
    if wam is None:
        return

    owner = find_owner_of_pod(pod)
    if owner is None:
        logger.error(f"Couldn't retrieve the owner of {pod.metadata}.")
        return

    # Add the URL of the wam
    url = f"http://{wam.status.pod_ip}:3030/rpc"
    logger.debug(f"Found 'wam': {url}")
    headers = {"Content-Type": "application/json"}
    payload = {
        "method": "action.Create",
        "params": [
            {
                "workload": {
                    "namespace": pod.metadata.namespace,
                    "apiVersion": "apps/v1",
                    "kind": owner.kind,
                    "name": owner.name,
                },
                "node": {"name": node_name},
            }
        ],
        "id": str(id),
    }

    logger.debug(f"Payload:\n{json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            logger.info(
                f"Successfully scheduled Pod {pod.metadata.name} on {node_name}"
            )
        else:
            logger.error(
                f"Failed to schedule Pod {pod.metadata.name}: "
                f"{response.status_code} - {response.text}"
            )
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error sending scheduling request: {e}")


def bind_pod_to_node(pod_name: str, pod_namespace: str, node_name: str) -> None:
    v1 = client.CoreV1Api()

    target = client.V1ObjectReference(api_version="v1", kind="Node", name=node_name)

    metadata = client.V1ObjectMeta(name=pod_name)

    binding = client.V1Binding(
        api_version="v1", kind="Binding", target=target, metadata=metadata
    )

    try:
        v1.create_namespaced_binding(namespace=pod_namespace, body=binding)
    except Exception:
        # logger.exception(f"Failed to bind pod: '{e}'.")
        pass

    logger.info(f"Bound pod '{pod_name}' to node '{node_name}'.")


def get_node_details() -> dict[str, NodeDetail]:
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
                # send_scheduling_request(pod, selected_node)
                bind_pod_to_node(
                    pod.metadata.name, pod.metadata.namespace, selected_node
                )
            else:
                logger.info("No available nodes to schedule the Pod.")


if __name__ == "__main__":
    start_scheduler()
