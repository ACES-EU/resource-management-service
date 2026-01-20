#!/bin/bash

KUBECONFIG="/home/peter/data/codes/aces/lake-aces.yaml"

while true
	do kubectl get pods -n lake --kubeconfig $KUBECONFIG | awk '
		BEGIN {c=0}
		NR == 1 {
			system("clear");
			print;
		}
		/Pending/ {
			c++;
			print;
		}
		END {
			print "Total Pending pods:", c;
		}'
done

