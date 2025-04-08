import random


class Master:
    def __init__(
        self,
        thresholds=(5, 5),
        Gamma=0.2,
        slack_estimation_error=0.2,
        worker_list=[],
    ):
        self.worker_list = worker_list
        self.rigid_queue = []
        self.elastic_queue = []

        # track the queue status and current deployde pods
        self.rigid_queue_status = []
        self.elastic_queue_status = []

        self.current_deployed_pods = {}

        self.lookup_table = {}
        # thresholds used to cluster current deployed rigid pods based on their slacks
        self.thresholds = thresholds
        # probability that an elastic pod is served as a rigid one
        self.Gamma = Gamma
        self.slack_estimation_error = slack_estimation_error

    def add_to_queue(self, pod_agent):
        if not pod_agent.is_elastic:
            self.rigid_queue.append(pod_agent)
        else:
            self.elastic_queue.append(pod_agent)

    def next_rigidPod_please(self):
        # fetch next pod from queue
        next_pod = self.rigid_queue[0]

        # select worker
        selected_worker = self.worker_list[0]

        if selected_worker.accept_as_rigid(next_pod):
            # remove from queue, add to deployed
            del self.rigid_queue[0]
            self.current_deployed_pods[next_pod.unique_id] = next_pod.demand_slack

            # update short lookup table
            self.add_lookup_table(next_pod)

            return True  # rigid pod accepted/resource assigned
        else:
            # avoid locking by considering the next one in queue
            if len(self.rigid_queue) > 1:
                tmp = self.rigid_queue.pop(0)
                self.rigid_queue.insert(1, tmp)  # try next one first

            return False  # rigid pod rejected, perhaps next step

    def next_elasticPod_please(self):
        # fetch next pod from queue
        next_pod = self.elastic_queue[0]

        # select worker
        selected_worker = self.worker_list[0]

        if selected_worker.accept_as_elastic(next_pod):
            # accepted by a peer pod
            del self.elastic_queue[0]
            # should we add to state table with zeros slack
            self.current_deployed_pods[next_pod.unique_id] = next_pod.demand_slack
            self.add_lookup_table(next_pod)
            return True

        if random.random() < self.Gamma:
            if selected_worker.accept_as_rigid(next_pod):
                # accepted as rigid pod
                del self.elastic_queue[0]
                self.current_deployed_pods[next_pod.unique_id] = next_pod.demand_slack
                self.add_lookup_table(next_pod)
                return True
            else:
                # avoid locking by considering the next one in queue
                if len(self.elastic_queue) > 1:
                    tmp = self.elastic_queue.pop(0)
                    self.elastic_queue.insert(1, tmp)  # try next one first
                    return False
        else:
            return False

    def get_rigid_queue_status(self):
        return len(self.rigid_queue)

    def get_elastic_queue_status(self):
        return len(self.elastic_queue)

    def generate_key(self, slack_values):
        key = []
        for value, threshold in zip(slack_values, self.thresholds):
            if value < threshold:
                key.append("L")
            else:
                key.append("H")

        # Robustness: randomly assign the bucket for a specific
        # percentage of rigid pods' slacks
        if random.random() < self.slack_estimation_error:
            key = random.choices([["L", "L"], ["L", "H"], ["H", "L"], ["H", "H"]], k=1)[
                0
            ]

        return tuple(key)

    def generate_3key(self, slack_values):
        # same as above, in finer granularity
        key = []
        for value, threshold in zip(slack_values, self.thresholds):
            if value < threshold[0]:
                key.append("L")
            elif value < threshold[1]:
                key.append("M")
            else:
                key.append("H")
        return tuple(key)

    def add_lookup_table(self, new_pod):
        key = self.generate_key(new_pod.demand_slack)
        if key not in self.lookup_table:
            self.lookup_table[key] = []
        self.lookup_table[key].append(new_pod)

    def del_lookup_table(self, pod):
        for key, lst in self.lookup_table.items():
            if pod in lst:
                self.lookup_table[key].remove(pod)

    def step(self):
        self.rigid_queue_status.append(self.get_rigid_queue_status())
        self.elastic_queue_status.append(self.get_elastic_queue_status())

        """
        next pods please: serve as far as there are pods in queue
        and we have enough capacity; either as rigid pod or hosting
        by peer using slack
        """
        while len(self.rigid_queue) > 0 and self.next_rigidPod_please():
            pass

        while len(self.elastic_queue) > 0 and self.next_elasticPod_please():
            # print(len(self.elastic_queue), len(self.current_deployed_pods))
            pass
