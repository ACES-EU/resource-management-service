import random

from loguru import logger
from schemas import NodeDetail

# from swarm.Master import Master
from app.swarm.Worker import Worker


class SwarmScheduler:
    workers: list[Worker]

    def __init__(
        self,
        method="RND",
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

    def select_node(self, new_pod):
        # TODO complete the swarm scheduler
        mock_choice = random.choice(self.workers)
        logger.debug(f"Mock choice: '{mock_choice.unique_id}'.")
        return mock_choice.unique_id
