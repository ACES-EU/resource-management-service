import re

from pydantic import BaseModel, ConfigDict, field_validator


class NodeResources(BaseModel):
    cpu: float
    memory: float

    model_config = ConfigDict(extra="allow")

    @field_validator("cpu", mode="before")
    @classmethod
    def convert_cpu_usage(cls, cpu_usage: str) -> float:
        """Convert CPU usage string to cores."""
        match = re.match(r"(\d+)([a-zA-Z]*)", cpu_usage)
        if match:
            value, unit = int(match[1]), match[2]
            if unit == "n":  # Nanocores
                return value / 1_000_000_000
            elif unit == "m":  # Millicores
                return value / 1000
            else:  # No suffix = cores
                return float(value)
        return 0.0

    @field_validator("memory", mode="before")
    @classmethod
    def convert_memory_usage(cls, memory_usage: str) -> float:
        """Convert memory usage string to MiB."""
        match = re.match(r"(\d+)([a-zA-Z]*)", memory_usage)
        if match:
            value, unit = int(match[1]), match[2]
            if unit == "Ki":  # Kibibytes
                return value / 1024
            elif unit == "Mi":  # Mebibytes
                return value
            elif unit == "Gi":  # Gibibytes
                return value * 1024
            elif unit == "Ti":  # Tebibytes
                return value * 1024 * 1024
            else:  # No suffix = bytes
                return value / (1024 * 1024)
        return 0.0


class NodeDetail(BaseModel):
    usage: NodeResources
    capacity: NodeResources
    allocatable: NodeResources

    model_config = ConfigDict(extra="allow")
