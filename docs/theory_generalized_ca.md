# Generalized Cellular Automata: Continuous and Tensor-Valued Extensions

## Why this note exists
This repository implements a CA-inspired simulation + cloud experiment pipeline for benchmarking controller profiles under uncertainty and faults.

## Classical CA (baseline)
A classical cellular automaton (CA) evolves a grid of cells in discrete steps.
Each cell is updated by a fixed local rule based on its neighborhood.

## Generalized CA (continuous + tensorial states)
Recent generalized CA work extends the CA concept to:
- Continuous or continuous-approximating evolution (reducing the strict discrete limitation)
- Multilayer and tensor-valued cell states (each cell can hold a vector/tensor of quantities)

Reference:
- Pau Fonseca i Casas, "The Multi-n-Dimensional Cellular Automaton: A Unified Framework for Tensorial, Discrete, and Continuous Simulations—A Computational Definition of Time," Complexity, 2025, Article ID 3088010.

## How this repo relates
This repo uses CA-inspired *local update* ideas as a lightweight, scalable testbed for reproducible benchmarking.
It is not a high-fidelity UAV physics model, and it does not claim to fully implement the generalized CA framework above.

## Extension path (future work)
A direct next step is to make the simulator more explicitly "generalized CA-ready":
- Represent state as a tensor per cell (e.g., stacking multiple channels: disturbances, faults, outputs)
- Add multilayer coupling if modeling multiple interacting fields
