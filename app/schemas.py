from typing import Optional

from kubernetes.utils.quantity import parse_quantity
from pydantic import BaseModel, ConfigDict, field_validator


class NodeResources(BaseModel):
    cpu: float
    memory: float

    model_config = ConfigDict(extra="allow")

    @field_validator("cpu", mode="before")
    @classmethod
    def convert_cpu_usage(cls, cpu_usage):
        """Convert CPU usage string to millicores."""
        if isinstance(cpu_usage, (int, float)):
            return float(cpu_usage)
        return float(parse_quantity(cpu_usage))

    @field_validator("memory", mode="before")
    @classmethod
    def convert_memory_usage(cls, memory_usage):
        """Convert memory usage string to bytes."""
        if isinstance(memory_usage, (int, float)):
            return float(memory_usage)
        return float(parse_quantity(memory_usage))


class NodeDetail(BaseModel):
    name: str
    id: str

    usage: NodeResources
    capacity: NodeResources
    allocatable: NodeResources

    slack: Optional[dict[tuple[str], NodeResources]] = None

    model_config = ConfigDict(extra="allow")
