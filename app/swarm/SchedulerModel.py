import random

import numpy as np
from mesa import Model
from mesa.time import RandomActivation

from app.schemas import NodeDetail
from app.swarm import pod_profiles
from app.swarm.Master import Master
from app.swarm.Pod import Pod
from app.swarm.Worker import Worker


class SchedulerModel(Model):
    def __init__(
        self,
        method="RND",
        worker_capacity=(512, 512),
        inter_arrival_mu=0.1,
        prob_pod_profiles=(0.4, 0.4, 0.2),
        prob_elastisity=0.0,
        seed=100,
    ):
        super().__init__()

        self.inter_arrival_mu = inter_arrival_mu
        self.prob_elastisity = prob_elastisity
        self.method = method

        self.prob_pod_profiles = prob_pod_profiles

        self.schedule = RandomActivation(self)

        random.seed(seed)
        np.random.seed(seed)

        self.satisfied_elastic = []
        self.un_satisfied_elastic = []
        self.satisfied_rigid = []
        self.un_satisfied_rigid = []

        # create one worker
        self.agent_id = 0
        worker = Worker(
            self,
            str(self.agent_id),
            NodeDetail.model_validate_json(
                '{"usage": {"cpu": 0, "memory": 0}, '
                '"capacity": {"cpu": 0, "memory": 0}, '
                '"allocatable": {"cpu": 0, "memory": 0}}'
            ),
        )  # , resource_capacity=worker_capacity)
        self.schedule.add(worker)
        self.worker = worker
        self.agent_id += 1

        # create the master agent with one worker
        master = Master(self.agent_id, self, worker_list=[worker])
        self.schedule.add(master)
        self.agent_id += 1

        self.master = master

        self.next_pod_time = random.randint(1, 2)  # Random time for the first task

    def get_new_pod(self, prob_elastisity=0.0):
        (
            next_demand,
            next_demand_step,
            next_slack,
            next_is_elastic,
            next_demand_tolerance,
        ) = pod_profiles.get_pod_profile(
            categories_prob=self.prob_pod_profiles, prob_elastisity=prob_elastisity
        )

        next_pod = Pod(
            self.agent_id,
            self,
            next_demand,
            demand_steps=next_demand_step,
            is_elastic=next_is_elastic,
            demand_tolerate_steps=next_demand_tolerance,
            demand_slack=list(next_slack),
        )

        self.agent_id += 1

        return next_pod

    def step(self):
        self.schedule.step()

        if self.schedule.steps == self.next_pod_time:
            new_pod = self.get_new_pod(self.prob_elastisity)

            # xpos = round(new_pod.demand_steps*new_pod.demand_slack[0])
            # ypos = round(new_pod.demand_steps*new_pod.demand_slack[1])
            # while self.grid.is_cell_empty((xpos, ypos)) is False:
            #     xpos += random.randint(-20,20)
            #     ypos += random.randint(-20,20)

            # self.grid.place_agent(new_pod, (xpos, ypos))

            new_pod.arrival_step = self.schedule.steps
            self.schedule.add(new_pod)
            self.master.add_to_queue(new_pod)

            # Set next task creation time
            # self.next_pod_time += random.randint(1, int(1./self.inter_arrival_mu))
            self.next_pod_time += max(
                1, round(np.random.exponential(scale=1.0 / self.inter_arrival_mu))
            )
