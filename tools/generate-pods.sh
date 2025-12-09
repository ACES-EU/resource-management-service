#!/bin/bash

COUNT=5
SLEEP_TIME_SECONDS=5
CHART="./charts/si-test"
NAMESPACE="lake"
SCHEDULER="resource-management-service"

# Bucket distribution (change weights by repeating entries)
BUCKETS=("small" "small" "medium" "medium" "large" "large" "xl")

CPU_REQS=(
  ["small"]="50m"
  ["medium"]="200m"
  ["large"]="500m"
  ["xl"]="1000m"
)

MEM_REQS=(
  ["small"]="64Mi"
  ["medium"]="256Mi"
  ["large"]="512Mi"
  ["xl"]="1024Mi"
)

# Chance (0–10) that ANY bucket gets limits
LIMIT_PROB=3   # 30%

random_range() {
    min=$1
    max=$2
    echo $((RANDOM % (max - min + 1) + min))
}

for i in $(seq 1 $COUNT); do
    # pick bucket
    idx=$(random_range 0 $((${#BUCKETS[@]} - 1)))
    BUCKET="${BUCKETS[$idx]}"

    CPU_REQ="${CPU_REQS[$BUCKET]}"
    MEM_REQ="${MEM_REQS[$BUCKET]}"

    # limits or not?
    roll=$(random_range 1 10)
    if (( roll <= LIMIT_PROB )); then
        # CPU limit >= request
        CPU_LIMIT="`random_range ${CPU_REQ%m} 2000`m"

        # Memory limit >= request
        MEM_LIMIT="`random_range ${MEM_REQ%Mi} 4096`Mi"

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
        $LIMITS

    echo "[INFO] Created $RELEASE in bucket $BUCKET (req=${CPU_REQ}/${MEM_REQ}, limits=${CPU_LIMIT:-none}/${MEM_LIMIT:-none})"
    sleep $SLEEP_TIME_SECONDS
done


