# Swarm Modules

The code  inside `swarm` was extracted from the [emergent-scheduler](https://github.com/ACES-EU/emergent-scheduler) GitHub repository.

## Description in the original repository

ACES Project: swarm inspired bottom-up resource allocation 

The edge computing system is modeled as multiagent system consists of
one master agent, one worker agent, and sequentially arriving
pod agents.

Each agent has its own attributes and behave accordingly in each consecutive step.

The system model first creates the master and worker agents and adds them. 
The scheduler calls the step function of all agents and creates and adds a new pod
to the system for a specific number of steps.
The inter-arrival time steps are generated using an exponential random variable with parameter $\lambda$.
The model scheduler tracks the satisfied and unsatisfied pods and removes the completed pods from the system.

Abdorasoul Ghasemi, arghasemi@gmail.com
