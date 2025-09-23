from typing import Any

import json
import threading
import time

import requests
from kubernetes import client, config, watch
from loguru import logger

from app.consts import (
    ANNOT_DECISION_START_TIME,
    ANNOT_RETRIES,
    ANNOT_SCHEDULING_ATTEMPTED,
    ANNOT_SCHEDULING_SUCCESS,
    ORCHESTRATION_API_URL,
    WAM_URL,
    get_timestamp,
    patch_decision_start,
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


def get_pod_parent_details(namespace, pod_name=None, pod_id=None):
    params = {"namespace": namespace}
    if pod_name:
        params["name"] = pod_name
    elif pod_id:
        params["pod_id"] = pod_id
    else:
        logger.error("Either pod_name or pod_id must be provided.")
        return {}

    try:
        response = requests.get(
            f"{ORCHESTRATION_API_URL}/k8s_pod_parent", params=params
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Status code {response.status_code}: {response.text}")
    except Exception:
        logger.exception("Failed to get node details.")

    return {}


def send_workload_request_decision(
    pod: Any, node: NodeDetail, decision_start_time: str, decision_end_time: str
) -> None:
    pod_parent_details = {
        "pod_parent_id": "",
        "pod_parent_name": "",
        "pod_parent_kind": "",
    }
    try:
        if pod.metadata.owner_references:
            for owner in pod.metadata.owner_references:
                pod_parent_details["pod_parent_id"] = owner.uid
                pod_parent_details["pod_parent_name"] = owner.name
                pod_parent_details["pod_parent_kind"] = owner.kind
        else:
            pod_parent = get_pod_parent_details(
                pod.metadata.namespace, pod.metadata.name
            )
            pod_parent_details["pod_parent_name"] = pod_parent["name"]
            pod_parent_details["pod_parent_kind"] = pod_parent["kind"]

        response = requests.post(
            f"{ORCHESTRATION_API_URL}/workload_request_decision",
            json={
                "is_elastic": True,
                "queue_name": "",  # TODO find out what this could be
                "demand_cpu": 0,
                "demand_memory": 0,
                "demand_slack_cpu": 0,
                "demand_slack_memory": 0,
                "pod_id": pod.metadata.uid,
                "pod_name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "node_id": node.id,
                "node_name": node.name,
                "action_type": "bind",
                "decision_status": "pending",
                "pod_parent_id": pod_parent_details["pod_parent_id"],
                "pod_parent_name": pod_parent_details["pod_parent_name"],
                "pod_parent_kind": pod_parent_details["pod_parent_kind"].lower(),
                "decision_start_time": decision_start_time,
                "decision_end_time": decision_end_time,
                # "created_at": "2025-09-22T17:44:50.831257Z",
                # "deleted_at": "2025-09-23T08:38:53.751Z"
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
    try:
        response = requests.get(f"{ORCHESTRATION_API_URL}/k8s_node")
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


def perform_scheduling(
    pod: Any, swarm_model: SwarmScheduler, decision_start_time: str | None = None
) -> None:
    """
    Custom scheduling logic
    """
    v1 = client.CoreV1Api()
    annotations = pod.metadata.annotations or {}

    start_time_annot = annotations.get(ANNOT_DECISION_START_TIME)
    attempted = annotations.get(ANNOT_SCHEDULING_ATTEMPTED) == "true"
    success = annotations.get(ANNOT_SCHEDULING_SUCCESS) == "true"

    logger.debug(
        f"Annotations for pod {pod.metadata.name}:\n"
        f"\t{ANNOT_DECISION_START_TIME}: {start_time_annot}\n"
        f"\t{ANNOT_SCHEDULING_ATTEMPTED}: {attempted}\n"
        f"\t{ANNOT_SCHEDULING_SUCCESS}: {success}"
    )

    if start_time_annot:
        decision_start_time = str(start_time_annot)
    else:
        if decision_start_time is None:
            if attempted:
                logger.error(
                    f"There was a scheduling attempt for pod {pod.metadata.name}"
                    ", but 'decision_start_time' doesn't exist."
                )
                return
            decision_start_time = get_timestamp()
        try:
            v1.patch_namespaced_pod(
                pod.metadata.name,
                pod.metadata.namespace,
                patch_decision_start(decision_start_time),
            )
        except Exception:
            logger.exception(
                f"Failed to patch pod {pod.metadata.name} with decision start time."
            )
    logger.debug(f"Scheduling pod {pod.metadata.name} started at {decision_start_time}")

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
        send_workload_request_decision(
            pod, nodes[selected_node], decision_start_time, get_timestamp()
        )
        v1.patch_namespaced_pod(
            pod.metadata.name, pod.metadata.namespace, patch_success()
        )

        send_scheduling_request(pod, selected_node)
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
            pod = event["object"]
            if (
                pod.spec.scheduler_name == "resource-management-service"
                and not pod.spec.node_name
            ):
                logger.info(f"Found Pod to schedule: {pod.metadata.name}")
                perform_scheduling(pod, swarm_model, get_timestamp())
    except Exception:
        logger.exception("Scheduler crashed.")


if __name__ == "__main__":
    start_scheduler()
