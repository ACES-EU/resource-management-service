from typing import Any

import random

from loguru import logger

from app.schemas import NodeDetail
from app.swarm.Worker import Worker
from app.utils import classify_pod, get_parameters, get_pod_requested_resources


class SwarmScheduler:
    workers: list[Worker]
    lookup_table: dict[tuple[str], list[dict[str, Any]]]
    params: dict[str, float]

    def __init__(
        self,
        method="SWARM",
    ):
        self.method = method

        self.satisfied_elastic = []
        self.un_satisfied_elastic = []
        self.satisfied_rigid = []
        self.un_satisfied_rigid = []

    def set_workers(self, workers: dict[str, NodeDetail]) -> None:
        logger.debug(f"Setting up the model workers with {len(workers)} nodes:")
        for worker in workers:
            logger.debug(f"{worker}: {workers[worker]}")

        self.workers = [
            Worker(self, unique_id, workers[unique_id]) for unique_id in workers
        ]

    def set_parameters(self):
        params = get_parameters()
        if params and len(params) > 0:
            self.params = params[0]

    def generate_key(self, slack_values, thresholds, slack_estimation_error):
        key = []
        for value, threshold in zip(slack_values, thresholds):
            if value < threshold:
                key.append("L")
            else:
                key.append("H")

        # Robustness: randomly assign the bucket for a specific
        # percentage of rigid pods' slacks
        if random.random() < slack_estimation_error:
            key = random.choice([["L", "L"], ["L", "H"], ["H", "L"], ["H", "H"]])

        return tuple(key)

    def create_lookup_table(self, thresholds, slack_estimation_error):
        self.lookup_table = {}
        for worker in self.workers:
            if worker.details.slack:
                for pod_key in worker.details.slack:
                    cpu_slack = worker.details.slack[pod_key].cpu
                    mem_slack = worker.details.slack[pod_key].memory
                    lookup_key = self.generate_key(
                        (cpu_slack, mem_slack), thresholds, slack_estimation_error
                    )

                    lookup_value = {
                        "pod": pod_key,
                        "node": worker.unique_id,
                        "slack": (cpu_slack, mem_slack),
                    }
                    try:
                        self.lookup_table[lookup_key].append(lookup_value)
                    except KeyError:
                        self.lookup_table[lookup_key] = [lookup_value]

    def schedule_elastic(self, pod, thresholds, slack_estimation_error):
        self.create_lookup_table(thresholds, slack_estimation_error)
        pod_demand = get_pod_requested_resources(pod)

        lookup_key = self.generate_key(
            (pod_demand["cpu"], pod_demand["memory"]),
            thresholds,
            slack_estimation_error,
        )

        logger.debug(f"lookup_key = {lookup_key}")

        if lookup_key in self.lookup_table:
            choice = random.choice(self.lookup_table[lookup_key])
            logger.debug(f"Choice: '{choice}'.")
            if (
                pod_demand["cpu"] <= choice["slack"][0]
                and pod_demand["memory"] <= choice["slack"][1]
            ):
                return str(choice["node"])
            elif random.random() < self.params["gamma"]:
                logger.info(
                    f"Couldn't schedule pod '{pod.metadata.name}', "
                    "trying to schedule as rigid."
                )
                return self.schedule_rigid(pod)
            else:
                error_msg = (
                    f"The resource requests of pod '{pod.metadata.name}' are "
                    "higher than the slack of the chosen rigid pod."
                )
                logger.error(error_msg)
                raise Exception(error_msg)
        return None

    def schedule_rigid(self, pod):
        pod_demand = get_pod_requested_resources(pod)
        choice = random.choice(self.workers)
        logger.debug(f"Choice: '{choice}'.")

        cpu_available = choice.resource_capacity[0] - choice.current_cpu_utilization
        mem_available = choice.resource_capacity[1] - choice.current_mem_utilization

        if pod_demand["cpu"] <= cpu_available and pod_demand["memory"] <= mem_available:
            return choice.unique_id
        else:
            error_msg = (
                f"The resource requests of pod '{pod.metadata.name}' are "
                "higher than the available resources on chosen node."
            )
            logger.error(error_msg)
            raise Exception(error_msg)

    def select_node(self, new_pod, slack_estimation_error=0.2):
        if self.method == "RND":
            mock_choice = random.choice(self.workers)
            logger.debug(f"Mock choice: '{mock_choice.unique_id}'.")
            return mock_choice.unique_id

        elif self.method == "SWARM":
            if classify_pod(new_pod) == "elastic":
                logger.info(f"Scheduling pod {new_pod.metadata.name} as elastic.")
                self.set_parameters()
                return self.schedule_elastic(
                    new_pod,
                    (self.params["alpha"], self.params["beta"]),
                    slack_estimation_error,
                )
            else:
                logger.info(f"Scheduling pod {new_pod.metadata.name} as rigid.")
                return self.schedule_rigid(new_pod)
