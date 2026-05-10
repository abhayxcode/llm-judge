# judge-eval-bench

Internal package: ships the canonical built-in metric YAMLs (`metrics/`) and
the golden datasets used to compute Bias Reports (`datasets/`). The CI Bias
Report job (M5) reads this directory.

For M2, the `metrics/faithfulness.v1.yaml` definition is the only metric
loaded by `judge run` out of the box.
