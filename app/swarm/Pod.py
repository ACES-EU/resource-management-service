class Pod:
    def __init__(
        self,
        unique_id,
        model,
        demand,
        demand_steps=1,
        is_elastic=False,
        demand_tolerate_steps=2,
        demand_slack=[0, 0],
    ):
        self.unique_id = unique_id
        self.model = model

        self.demand = demand
        self.demand_steps = demand_steps
        self.demand_tolerate_steps = demand_tolerate_steps
        self.demand_slack = demand_slack
        self.is_elastic = is_elastic

        self.remain_steps = demand_steps
        self.assigned_cpu = 0
        self.assigned_mem = 0
        self.assigned_worker = None
        self.arrival_step = None

    def step(self):
        if self.assigned_worker is None:
            # nothing to do in this step, wait in the corresponding master queue
            pass

        elif self.remain_steps > 0:
            # pod is deployed, needs more steps
            self.remain_steps -= 1

        else:
            # pod completed, track some metrics
            expected_departure = (
                self.arrival_step + self.demand_steps + self.demand_tolerate_steps
            )

            if self.model.schedule.steps <= expected_departure:
                if self.is_elastic:
                    self.model.satisfied_elastic.append(
                        (self.demand, self.demand_steps)
                    )
                else:
                    self.model.satisfied_rigid.append((self.demand, self.demand_steps))

            else:
                if self.is_elastic:
                    self.model.un_satisfied_elastic.append(
                        (self.demand, self.demand_steps)
                    )
                else:
                    self.model.un_satisfied_rigid.append(
                        (self.demand, self.demand_steps)
                    )

            # delete from the current_deployed_pods and release resources
            del self.model.master.current_deployed_pods[self.unique_id]
            self.model.master.del_lookup_table(self)
            self.model.master.release_resources(self)
