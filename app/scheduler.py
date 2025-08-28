from typing import Any

import json
import threading
import time

import requests
from kubernetes import client, config, watch
from loguru import logger

from app.consts import (
    ANNOT_RETRIES,
    ANNOT_SCHEDULING_ATTEMPTED,
    ANNOT_SCHEDULING_SUCCESS,
    WAM_URL,
    patch_fail,
    patch_success,
)
from app.schemas import NodeDetail
from app.swarm.SwarmScheduler import SwarmScheduler

try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    try:
        config.load_kube_config()
    except config.config_exception.ConfigException:
        logger.error("No Kubernetes config found — running without cluster access")


def find_pod(label_selector, namespace):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)

    found_pod = None
    if pods.items:
        for pod in pods.items:
            found_pod = pod
            logger.debug(f"Pod Name: {found_pod.metadata.name}")
            if found_pod is not None:
                break
    else:
        logger.error(
            f"No pods found with label {label_selector} in namespace {namespace}"
        )

    return found_pod


def send_scheduling_request(pod, node_name, id=1):
    """Send the scheduling request to the external service."""
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

    response = requests.post(WAM_URL, json=payload)
    if response.status_code == 200:
        logger.info(f"Successfully scheduled Pod {pod.metadata.name} on {node_name}")
    else:
        logger.error(
            f"Failed to schedule Pod {pod.metadata.name}: "
            f"{response.status_code} - {response.text}"
        )
        raise Exception(
            f"Failed to schedule Pod {pod.metadata.name}: "
            f"{response.status_code} - {response.text}"
        )


def send_workload_request_decision(pod: Any, node: NodeDetail) -> None:
    orchestration_api = find_pod("app=aces-orchestration-api", "hiros")
    if orchestration_api is None:
        return

    try:
        response = requests.post(
            f"http://{orchestration_api.status.pod_ip}:8000"
            "/workload_request_decision",
            json={
                "pod_id": pod.metadata.uid,
                "pod_name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "node_id": node.id,
                "is_elastic": True,
                # "queue_name": "string",
                # "demand_cpu": 0,
                # "demand_memory": 0,
                # "demand_slack_cpu": 0,
                # "demand_slack_memory": 0,
                "is_decision_status": True,
                # "pod_parent_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                # "pod_parent_kind": "string",
            },
        )
        if response.status_code == 200:
            logger.info(
                f"Sent workload request decision about pod {pod.metadata.name}."
            )
        else:
            logger.error(f"Status code {response.status_code}: {response.text}")
    except Exception:
        logger.exception("Failed to send workload request decision.")


def get_node_details() -> dict[str, NodeDetail]:
    orchestration_api = find_pod("app=aces-orchestration-api", "hiros")
    if orchestration_api is None:
        return {}

    try:
        response = requests.get(
            f"http://{orchestration_api.status.pod_ip}:8000/k8s_node"
        )
        if response.status_code == 200:
            return {
                node["name"]: NodeDetail.model_validate_json(json.dumps(node))
                for node in response.json()
            }
        else:
            logger.error(f"Status code {response.status_code}: {response.text}")
    except Exception:
        logger.exception("Failed to get node details.")

    return {}


def perform_scheduling(pod: Any, swarm_model: SwarmScheduler) -> None:
    """
    Custom scheduling logic
    """
    v1 = client.CoreV1Api()
    annotations = pod.metadata.annotations or {}

    attempted = annotations.get(ANNOT_SCHEDULING_ATTEMPTED) == "true"
    success = annotations.get(ANNOT_SCHEDULING_SUCCESS) == "true"

    if attempted and success:
        logger.debug(
            f"Pod {pod.metadata.name} already successfully scheduled. Skipping."
        )
        return

    retries = int(annotations.get(ANNOT_RETRIES, "0"))
    # if retries >= 3:
    #     logger.warning(
    #         f"Pod {pod.metadata.name} reached max retries ({retries}). Skipping."
    #     )
    #     return

    logger.info(f"Scheduling Pod {pod.metadata.name} (retry={retries})")

    try:
        nodes = get_node_details()
        if not nodes:
            logger.info("No available nodes to schedule the Pod.")
            raise Exception("No available nodes to schedule the Pod.")

        swarm_model.set_workers(nodes)
        selected_node = swarm_model.select_node(pod)
        send_scheduling_request(pod, selected_node)
        send_workload_request_decision(pod, nodes[selected_node])

        v1.patch_namespaced_pod(
            pod.metadata.name, pod.metadata.namespace, patch_success()
        )
        logger.info(f"Successfully scheduled pod {pod.metadata.name}")
    except Exception:
        logger.exception(
            f"Scheduling failed for pod {pod.metadata.name}. Marking as failed."
        )
        try:
            v1.patch_namespaced_pod(
                pod.metadata.name, pod.metadata.namespace, patch_fail(retries + 1)
            )
        except Exception:
            logger.exception(
                f"Failed to patch pod {pod.metadata.name} with failure status."
            )


def start_scheduler():
    v1 = client.CoreV1Api()
    w = watch.Watch()

    swarm_model = SwarmScheduler()

    def retry_unscheduled():
        while True:
            try:
                pods = v1.list_pod_for_all_namespaces(
                    field_selector="spec.schedulerName=resource-management-service"
                ).items
                for pod in pods:
                    if not pod.spec.node_name and pod.status.phase == "Pending":
                        logger.info(
                            f"[RETRY] Unscheduled pod found: {pod.metadata.name}"
                        )
                        perform_scheduling(pod, swarm_model)
            except Exception:
                logger.exception("[RETRY] Error during retry logic.")
            time.sleep(30)

    threading.Thread(target=retry_unscheduled, daemon=True).start()

    logger.info("Starting custom scheduler...")

    try:
        for event in w.stream(v1.list_pod_for_all_namespaces):
            logger.debug(
                "Found Pod. Checking if it needs to be "
                "scheduled by SI-based scheduler..."
            )
            pod = event["object"]
            if (
                pod.spec.scheduler_name == "resource-management-service"
                and not pod.spec.node_name
            ):
                logger.info(f"Found Pod to schedule: {pod.metadata.name}")
                perform_scheduling(pod, swarm_model)
    except Exception:
        logger.exception("Scheduler crashed.")


if __name__ == "__main__":
    start_scheduler()
