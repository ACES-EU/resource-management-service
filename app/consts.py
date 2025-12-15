from typing import Any

from datetime import datetime, timezone
from os import getenv

WAM_URL = getenv("WAM_URL", "http://wam-app.ul.svc.cluster.local:3030/rpc")
ORCHESTRATION_API_URL = getenv(
    "ORCHESTRATION_API_URL", "http://aces-orchestration-api.hiros.svc.cluster.local"
)
RETRY_EVERY_SECONDS = float(getenv("RETRY_EVERY_SECONDS", "5"))

# Annotation keys
ANNOT_DECISION_START_TIME = "resource-management-service/decision-start-time"
ANNOT_SCHEDULING_ATTEMPTED = "resource-management-service/scheduling-attempted"
ANNOT_SCHEDULING_SUCCESS = "resource-management-service/scheduling-success"
ANNOT_RETRIES = "resource-management-service/scheduling-retries"
ANNOT_LAST_ATTEMPT = "resource-management-service/last-scheduling-attempt"


def get_timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def patch_decision_start(timestamp):
    return {"metadata": {"annotations": {ANNOT_DECISION_START_TIME: timestamp}}}


def patch_success() -> dict[str, Any]:
    return {
        "metadata": {
            "annotations": {
                ANNOT_SCHEDULING_ATTEMPTED: "true",
                ANNOT_SCHEDULING_SUCCESS: "true",
                ANNOT_LAST_ATTEMPT: get_timestamp(),
            }
        }
    }


def patch_fail(retries: int = 0) -> dict[str, Any]:
    return {
        "metadata": {
            "annotations": {
                ANNOT_SCHEDULING_ATTEMPTED: "true",
                ANNOT_SCHEDULING_SUCCESS: "false",
                ANNOT_RETRIES: str(retries),
                ANNOT_LAST_ATTEMPT: get_timestamp(),
            }
        }
    }
