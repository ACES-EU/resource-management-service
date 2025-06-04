from typing import TYPE_CHECKING

from app.schemas import NodeDetail
from app.swarm import algorithms

if TYPE_CHECKING:
    from app.swarm.SwarmScheduler import SwarmScheduler


class Worker:
    def __init__(self, model: "SwarmScheduler", unique_id: str, details: NodeDetail):
        self.unique_id = unique_id
        self.details = details
        self.model = model

        # vector of resource capacities, for now (cpu_cap, mem_cap)
        self.resource_capacity = (details.allocatable.cpu, details.allocatable.memory)

        self.current_cpu_assignment = details.usage.cpu
        self.current_mem_assignment = details.usage.memory
        self.current_cpu_utilization = details.usage.cpu
        self.current_mem_utilization = details.usage.memory

        # track the utilization of worker over time
        # self.cpu_utilization = []
        # self.mem_utilization = []

    def get_cpu_utilization(self):
        return self.current_cpu_utilization / self.resource_capacity[0]

    def get_mem_utilization(self):
        return self.current_mem_utilization / self.resource_capacity[1]

    def accept_as_rigid(self, pod):
        """
        asign worker, update parameters, and return True if pod is accepted,
        otherwise return False
        """

        if (
            self.current_cpu_assignment + pod.demand[0] <= self.resource_capacity[0]
            and self.current_mem_assignment + pod.demand[1] <= self.resource_capacity[1]
        ):
            pod.assigned_worker = self  # set the worker for this pod
            pod.assigned_cpu = pod.demand[0]
            pod.assigned_mem = pod.demand[1]

            # update resource assignment and utilization
            self.current_cpu_assignment += pod.demand[0]
            self.current_mem_assignment += pod.demand[1]
            self.current_cpu_utilization += pod.demand[0] - pod.demand_slack[0]
            self.current_mem_utilization += pod.demand[1] - pod.demand_slack[1]

            # placement in grid
            # xpos = round(pod.demand_steps * pod.demand_slack[0])
            # ypos = round(pod.demand_steps * pod.demand_slack[1])
            # while self.model.grid.is_cell_empty((xpos, ypos)) is False:
            #     xpos += random.randint(-5, 5)
            #     ypos += random.randint(-5, 5)
            # self.model.grid.place_agent(pod, (xpos, ypos))

            return True
        else:
            return False

    def accept_as_elastic(self, pod):
        """
        Try to find a proper rigid pod as a host of this elastic pod
        If the selected rigid pod has sufficient slack resources to meet
        the elastic pod's demand return True otherwise return False
        """

        # see algorithms for implemented methods
        if self.model.method == "RND":
            peer_id, peer_pod = algorithms.random_peer_selection(self.model)
        elif self.model.method == "BEST":
            peer_id, peer_pod = algorithms.best_peer_selection(
                self.model, pod, ticks=True
            )
        elif self.model.method == "SWARM":
            peer_id, peer_pod, best_key = algorithms.bottom_up_peer_seletion(
                self.model, pod
            )

        else:
            print("Method is not implemented")
            return False

        if peer_id is None:
            # algorithm does not find any peer
            return False

        peer_cpu_slack = peer_pod.demand_slack[0]
        peer_mem_slack = peer_pod.demand_slack[1]
        if pod.demand[0] <= peer_cpu_slack and pod.demand[1] <= peer_mem_slack:
            pod.assigned_worker = self
            pod.assigned_cpu = pod.demand[0]  # peer_cpu_slack
            pod.assigned_mem = pod.demand[1]  # peer_mem_slack

            # update parameters: increase utilization
            self.current_cpu_utilization += pod.demand[0]  # peer_cpu
            self.current_mem_utilization += pod.demand[1]  # peer_mem

            # For visualization: placement in grid
            # xpos = round(peer_pod.demand_steps * peer_pod.demand_slack[0])
            # ypos = round(peer_pod.demand_steps * peer_pod.demand_slack[1])
            # while self.model.grid.is_cell_empty((xpos, ypos)) is False:
            #     xpos += random.randint(-5, 5)
            #     ypos += random.randint(-5, 5)
            # self.model.grid.place_agent(pod, (xpos, ypos))

            peer_pod.assigned_cpu -= pod.demand[0]  # peer_cpu_slack
            peer_pod.assigned_mem -= pod.demand[1]  # peer_mem_slack
            peer_pod.demand_slack[0] -= pod.demand[0]
            peer_pod.demand_slack[1] -= pod.demand[1]

            # no more elastic pod can exploit this
            # self.model.master.current_deployed_pods[peer_id] = (0, 0)

            return True
        else:
            return False

    def release_resources(self, pod):
        # release the assigned cpu/mem resources
        self.current_cpu_assignment -= pod.assigned_cpu
        self.current_mem_assignment -= pod.assigned_mem

        if not pod.is_elastic:
            self.current_cpu_utilization -= pod.assigned_cpu - pod.demand_slack[0]
            self.current_mem_utilization -= pod.assigned_mem - pod.demand_slack[1]
        else:
            self.current_cpu_utilization -= pod.demand[0]
            self.current_mem_utilization -= pod.demand[1]
