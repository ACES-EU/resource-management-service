from typing import Any

from datetime import datetime, timezone
from os import getenv

WAM_URL = getenv("WAM_URL", "http://wam-app.ul.svc.cluster.local:3030/rpc")

# Annotation keys
ANNOT_SCHEDULING_ATTEMPTED = "resource-management-service/scheduling-attempted"
ANNOT_SCHEDULING_SUCCESS = "resource-management-service/scheduling-success"
ANNOT_RETRIES = "resource-management-service/scheduling-retries"
ANNOT_LAST_ATTEMPT = "resource-management-service/last-scheduling-attempt"


def patch_success() -> dict[str, Any]:
    return {
        "metadata": {
            "annotations": {
                ANNOT_SCHEDULING_ATTEMPTED: "true",
                ANNOT_SCHEDULING_SUCCESS: "true",
                ANNOT_LAST_ATTEMPT: datetime.now(timezone.utc).isoformat(),
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
                ANNOT_LAST_ATTEMPT: datetime.now(timezone.utc).isoformat(),
            }
        }
    }
