#!/bin/bash

COUNT=30
SLEEP_TIME_SECONDS=5
CHART="./charts/si-test"
NAMESPACE="lake"
SCHEDULER="resource-management-service"

# Bucket distribution (change weights by repeating entries)
BUCKETS=("small" "small" "small" "small" "small" "medium" "medium" "medium" "medium" "large" "xl")

# Requests per bucket
CPU_REQ_SMALL="50m";   MEM_REQ_SMALL="64Mi"
CPU_REQ_MEDIUM="200m"; MEM_REQ_MEDIUM="256Mi"
CPU_REQ_LARGE="500m";  MEM_REQ_LARGE="512Mi"
CPU_REQ_XL="750m";    MEM_REQ_XL="724Mi"

# Chance (0–100) that ANY bucket gets limits
LIMIT_PROB=30   # 30%

random_range() {
    min=$1
    max=$2
    echo $((RANDOM % (max - min + 1) + min))
}

for i in $(seq 1 $COUNT); do
    # pick bucket
    idx=$(random_range 0 $((${#BUCKETS[@]} - 1)))
    BUCKET="${BUCKETS[$idx]}"

    case $BUCKET in
        small)
            CPU_REQ=$CPU_REQ_SMALL
            MEM_REQ=$MEM_REQ_SMALL
            ;;
        medium)
            CPU_REQ=$CPU_REQ_MEDIUM
            MEM_REQ=$MEM_REQ_MEDIUM
            ;;
        large)
            CPU_REQ=$CPU_REQ_LARGE
            MEM_REQ=$MEM_REQ_LARGE
            ;;
        xl)
            CPU_REQ=$CPU_REQ_XL
            MEM_REQ=$MEM_REQ_XL
            ;;
    esac

    # limits or not?
    roll=$(random_range 1 100)
    if (( roll <= LIMIT_PROB )); then
        # CPU limit >= request
        CPU_LIMIT="`random_range ${CPU_REQ%m} 1500`m"

        # Memory limit >= request
        MEM_LIMIT="`random_range ${MEM_REQ%Mi} 1448`Mi"

        LIMITS="--set resources.limits.cpu=${CPU_LIMIT} --set resources.limits.memory=${MEM_LIMIT}"
    else
        unset CPU_LIMIT
        unset MEM_LIMIT
        LIMITS=""
    fi

    RELEASE="si-test-$i"

    helm upgrade --install "$RELEASE" "$CHART" \
        -n "$NAMESPACE" \
        --set schedulerName="$SCHEDULER" \
        --set workload="$BUCKET" \
        --set resources.requests.cpu="$CPU_REQ" \
        --set resources.requests.memory="$MEM_REQ" \
        $LIMITS >/dev/null &

    echo "[INFO] Created $RELEASE in bucket $BUCKET (req=${CPU_REQ}/${MEM_REQ}, limits=${CPU_LIMIT:-none}/${MEM_LIMIT:-none})"
    sleep $SLEEP_TIME_SECONDS
done


